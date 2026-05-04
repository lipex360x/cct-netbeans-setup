# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13", "requests>=2"]
# ///

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import requests
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

MARKER_BEGIN = "<!-- cct-netbeans-setup:begin -->"
MARKER_END = "<!-- cct-netbeans-setup:end -->"

GITHUB_REPO = "lipex360x/cct-netbeans-setup"
GITHUB_BRANCH = "main"
GITHUB_JARS_PATH = "libs/tests/junit5/jar"
GITHUB_SETUP_ZIP_PATH = "templates/Template.zip"

_GITHUB_API = "https://api.github.com/repos"
_GITHUB_RAW = "https://raw.githubusercontent.com"

_TEMPLATE_PATHS = (
    "config/Templates/Classes/Class.java",
    "config/Templates/Classes/Main.java",
    "config/Templates/UnitTests/JUnit5TestClass.java",
)

_SAFE_PREFERENCES: frozenset[str] = frozenset(
    {
        "config/Preferences/org/apache/tools/ant/module.properties",
        "config/Preferences/org/netbeans/core/multitabs/multi-tabs.properties",
    }
)


def validate_netbeans_project(path: Path) -> None:
    if not path.is_dir():
        raise ValueError(f"Directory not found: {path}")
    if not (path / "build.xml").is_file():
        raise ValueError(f"Missing build.xml in: {path}")
    if not (path / "nbproject" / "project.properties").is_file():
        raise ValueError(f"Missing project.properties in: {path}")


def is_junit5_configured(path: Path) -> bool:
    jar_dir = path / "lib" / "junit5"
    if not jar_dir.is_dir():
        return False
    build_xml = path / "build.xml"
    return MARKER_BEGIN in build_xml.read_text()


def set_compile_on_save_false(props: Path) -> None:
    private = props.parent / "private" / "private.properties"
    for target in [props, private]:
        if not target.is_file():
            continue
        content = target.read_text()
        if "compile.on.save=false" in content:
            continue
        if "compile.on.save=true" in content:
            target.write_text(content.replace("compile.on.save=true", "compile.on.save=false"))
        else:
            target.write_text(content.rstrip("\n") + "\ncompile.on.save=false\n")


def add_file_references(props: Path, jar_names: list[str]) -> None:
    content = props.read_text()
    additions = []
    for name in jar_names:
        key = f"file.reference.{name}"
        if f"{key}=" not in content:
            additions.append(f"{key}=lib/junit5/{name}")
    if additions:
        props.write_text(content.rstrip("\n") + "\n" + "\n".join(additions) + "\n")


def modify_classpath(props: Path, jar_names: list[str]) -> None:
    lines = props.read_text().splitlines(keepends=True)
    result: list[str] = []
    in_block = False
    block_has_refs = False

    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("javac.test.classpath=") or stripped.startswith(
            "run.test.classpath="
        ):
            in_block = True
            block_has_refs = False

        if in_block:
            if "${file.reference." in stripped:
                block_has_refs = True
            if stripped.endswith("\\"):
                result.append(line)
            else:
                if block_has_refs:
                    result.append(line)
                else:
                    result.append(stripped + ":\\\n")
                    for i, name in enumerate(jar_names):
                        reference = f"    ${{file.reference.{name}}}"
                        result.append(reference + (":\\\n" if i < len(jar_names) - 1 else "\n"))
                in_block = False
                block_has_refs = False
        else:
            result.append(line)

    props.write_text("".join(result))


def inject_build_xml(build_xml: Path, override_content: str) -> None:
    content = build_xml.read_text()
    if MARKER_BEGIN in content:
        return
    marker = '<import file="nbproject/build-impl.xml"/>'
    injection = f"{MARKER_BEGIN}\n{override_content.rstrip()}\n{MARKER_END}"
    content = content.replace(marker, f"{marker}\n\n    {injection}")
    build_xml.write_text(content)


def remove_file_references(props: Path) -> None:
    lines = props.read_text().splitlines(keepends=True)
    filtered = [
        line for line in lines if not (line.startswith("file.reference.") and "lib/junit5/" in line)
    ]
    props.write_text("".join(filtered))


def revert_classpath(props: Path) -> None:
    def flush(buffer: list[str]) -> list[str]:
        filtered = [line for line in buffer if "${file.reference." not in line]
        if len(filtered) < len(buffer) and filtered:
            last = filtered[-1].rstrip("\n")
            if last.endswith(":\\"):
                filtered[-1] = last[:-2] + "\n"
        return filtered

    lines = props.read_text().splitlines(keepends=True)
    result: list[str] = []
    in_block = False
    buffer: list[str] = []

    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("javac.test.classpath=") or stripped.startswith(
            "run.test.classpath="
        ):
            in_block = True

        if in_block:
            buffer.append(line)
            if not stripped.endswith("\\"):
                result.extend(flush(buffer))
                buffer = []
                in_block = False
        else:
            result.append(line)

    if buffer:
        result.extend(flush(buffer))

    props.write_text("".join(result))


def remove_build_xml_override(build_xml: Path) -> None:
    content = build_xml.read_text()
    if MARKER_BEGIN not in content:
        return
    start = content.find(MARKER_BEGIN)
    end = content.find(MARKER_END) + len(MARKER_END)
    content = content[:start].rstrip() + "\n" + content[end:].lstrip("\n")
    build_xml.write_text(content)


def remove_jar_directory(project: Path) -> None:
    jar_dir = project / "lib" / "junit5"
    if jar_dir.is_dir():
        shutil.rmtree(jar_dir)


def fetch_jar_names() -> list[str]:
    url = f"{_GITHUB_API}/{GITHUB_REPO}/contents/{GITHUB_JARS_PATH}?ref={GITHUB_BRANCH}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    entries = response.json()
    return [
        entry["name"]
        for entry in entries
        if entry["type"] == "file" and entry["name"].endswith(".jar")
    ]


def download_jars(destination: Path, jar_names: list[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in jar_names:
        target = destination / name
        if target.exists():
            continue
        url = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_JARS_PATH}/{name}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        target.write_bytes(response.content)


_DEPENDS_SINGLE = "init,compile-test-single,-pre-test-run-single"

_JUNITLAUNCHER_CLASS = (
    "org.apache.tools.ant.taskdefs.optional.junitlauncher.confined.JUnitLauncherTask"
)

_TASKDEF_BLOCK = (
    '<taskdef name="junitlauncher"\n'
    f'         classname="{_JUNITLAUNCHER_CLASS}">\n'
    "    <classpath>\n"
    '        <fileset dir="${basedir}/lib/junit5">\n'
    '            <include name="ant-junitlauncher-*.jar"/>\n'
    "        </fileset>\n"
    "    </classpath>\n"
    "</taskdef>\n\n"
)

_BUILD_OVERRIDE = (
    _TASKDEF_BLOCK
    + """\
<target depends="init,compile-test,-pre-test-run" if="have.tests" name="-do-test-run">
    <junitlauncher haltOnFailure="false" failureProperty="tests.failed" printSummary="true">
        <classpath>
            <pathelement path="${run.test.classpath}:${build.test.classes.dir}"/>
        </classpath>
        <testclasses outputdir="${build.test.results.dir}">
            <fileset dir="${build.test.classes.dir}">
                <include name="**/*Test.class"/>
            </fileset>
            <listener type="legacy-xml"/>
            <listener type="legacy-plain" sendSysOut="true" sendSysErr="true"/>
        </testclasses>
    </junitlauncher>
</target>

"""
    + f'<target depends="{_DEPENDS_SINGLE}" if="have.tests" name="-do-test-run-single">\n'
    + """\
    <junitlauncher haltOnFailure="false" failureProperty="tests.failed" printSummary="true">
        <classpath>
            <pathelement path="${run.test.classpath}:${build.test.classes.dir}"/>
        </classpath>
        <test name="${test.class}" outputdir="${build.test.results.dir}">
            <listener type="legacy-xml"/>
            <listener type="legacy-plain" sendSysOut="true" sendSysErr="true"/>
        </test>
    </junitlauncher>
</target>

"""
    + f'<target depends="{_DEPENDS_SINGLE}" if="have.tests" name="-do-test-run-single-method">\n'
    + """\
    <junitlauncher haltOnFailure="false" failureProperty="tests.failed" printSummary="true">
        <classpath>
            <pathelement path="${run.test.classpath}:${build.test.classes.dir}"/>
        </classpath>
        <test name="${test.class}" methods="${test.method}" outputdir="${build.test.results.dir}">
            <listener type="legacy-xml"/>
            <listener type="legacy-plain" sendSysOut="true" sendSysErr="true"/>
        </test>
    </junitlauncher>
</target>"""
)


def clean_path(raw: str) -> Path:
    return Path(raw.strip().strip("'\"").rstrip("/\\")).expanduser().resolve()


def run_install(project: Path) -> None:
    validate_netbeans_project(project)
    jar_names = fetch_jar_names()
    download_jars(project / "lib" / "junit5", jar_names)
    props = project / "nbproject" / "project.properties"
    set_compile_on_save_false(props)
    add_file_references(props, jar_names)
    modify_classpath(props, jar_names)
    inject_build_xml(project / "build.xml", _BUILD_OVERRIDE)


def run_uninstall(project: Path) -> None:
    props = project / "nbproject" / "project.properties"
    remove_jar_directory(project)
    remove_file_references(props)
    revert_classpath(props)
    remove_build_xml_override(project / "build.xml")


def _netbeans_base() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "NetBeans"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        return (Path(appdata) if appdata else Path.home()) / "NetBeans"
    return Path.home() / ".netbeans"


def find_netbeans_user_dir(base: Path | None = None) -> Path | None:
    root = base if base is not None else _netbeans_base()
    if not root.is_dir():
        return None
    candidates = [d for d in root.iterdir() if d.is_dir()]
    return max(candidates, key=lambda d: d.name) if candidates else None


def are_templates_installed(netbeans_dir: Path) -> bool:
    return all((netbeans_dir / path).is_file() for path in _TEMPLATE_PATHS)


def _backup_dir(netbeans_dir: Path) -> Path:
    return netbeans_dir / "cct-setup-backup"


def is_setup_backup_present(netbeans_dir: Path) -> bool:
    return (_backup_dir(netbeans_dir) / "new-files.txt").is_file()


def _setup_entry_allowed(name: str) -> bool:
    if Path(name).name in {".DS_Store", ".nbattrs"}:
        return False
    if name.startswith("config/Editors/") or name.startswith("config/Templates/"):
        return True
    if name == "config/Preferences/laf.properties":
        return sys.platform == "darwin"
    return name in _SAFE_PREFERENCES


def download_and_apply_setup(netbeans_dir: Path) -> None:
    url = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_SETUP_ZIP_PATH}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    new_files: list[str] = []
    with tempfile.TemporaryDirectory() as temporary_dir:
        archive_path = Path(temporary_dir) / "setup.zip"
        archive_path.write_bytes(response.content)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                if member.endswith("/") or not _setup_entry_allowed(member):
                    continue
                target = netbeans_dir / member
                if target.is_file():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
                new_files.append(member)
    if new_files:
        backup = _backup_dir(netbeans_dir)
        backup.mkdir(parents=True, exist_ok=True)
        (backup / "new-files.txt").write_text("\n".join(new_files) + "\n")


def rollback_setup(netbeans_dir: Path) -> None:
    backup = _backup_dir(netbeans_dir)
    record = backup / "new-files.txt"
    if not record.is_file():
        return
    for path in record.read_text().splitlines():
        target = netbeans_dir / path
        if target.is_file():
            target.unlink()
    shutil.rmtree(backup)


def run_install_templates(netbeans_dir: Path) -> None:
    download_and_apply_setup(netbeans_dir)


def _templates_flow(console: Console) -> None:
    netbeans_dir = find_netbeans_user_dir()
    if netbeans_dir is None:
        console.print("\n  [red]✗[/red]  NetBeans user directory not found.\n")
        return
    installed = are_templates_installed(netbeans_dir)
    status_text = "[green]● installed[/green]" if installed else "[yellow]○ not installed[/yellow]"
    console.print(
        Panel(
            f"\n  [bold]Templates[/bold]   {status_text}\n  [dim]{netbeans_dir}[/dim]\n",
            title="[bold cyan]NetBeans Templates[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )
    if installed:
        if not is_setup_backup_present(netbeans_dir):
            console.print("\n  [green]✓[/green]  Templates already installed.\n")
            return
        console.print("  [bold cyan][3][/bold cyan] Rollback Templates   [dim]q  Quit[/dim]\n")
        choice = Prompt.ask("  Choice", choices=["3", "q"])
        if choice == "q":
            return
        with console.status("[cyan]Rolling back templates...[/cyan]"):
            rollback_setup(netbeans_dir)
        console.print("\n  [green]✓[/green]  Templates rolled back.\n")
        return
    console.print("  [bold cyan][3][/bold cyan] Install Templates   [dim]q  Quit[/dim]\n")
    choice = Prompt.ask("  Choice", choices=["3", "q"])
    if choice == "q":
        return
    with console.status("[cyan]Installing templates...[/cyan]"):
        run_install_templates(netbeans_dir)
    console.print("\n  [green]✓[/green]  Templates installed.\n")


def _junit5_flow(console: Console) -> None:
    cwd = Path.cwd()
    raw = Prompt.ask(f"\nNetBeans project path [dim](. = {cwd})[/dim]")
    project = clean_path(raw)
    try:
        validate_netbeans_project(project)
    except ValueError as error:
        console.print(f"\n  [red]✗[/red]  {error}\n")
        return
    configured = is_junit5_configured(project)
    status_text = "[green]● installed[/green]" if configured else "[yellow]○ not installed[/yellow]"
    console.print(
        Panel(
            f"\n  [bold]JUnit 5[/bold]   {status_text}\n",
            title=f"[bold cyan]{project.name}[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )
    if configured:
        console.print("  [bold cyan][2][/bold cyan] Uninstall JUnit 5   [dim]q  Quit[/dim]\n")
        choice = Prompt.ask("  Choice", choices=["2", "q"])
        if choice == "q":
            return
        with console.status("[cyan]Uninstalling JUnit 5...[/cyan]"):
            run_uninstall(project)
        console.print("\n  [green]✓[/green]  JUnit 5 uninstalled.\n")
    else:
        console.print("  [bold cyan][1][/bold cyan] Install JUnit 5   [dim]q  Quit[/dim]\n")
        choice = Prompt.ask("  Choice", choices=["1", "q"])
        if choice == "q":
            return
        with console.status("[cyan]Installing JUnit 5...[/cyan]"):
            run_install(project)
        console.print("\n  [green]✓[/green]  JUnit 5 installed.\n")


def main() -> None:
    console = Console()
    console.print(
        Panel(
            "[bold cyan]NetBeans — CCT Setup[/bold cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    try:
        console.print(
            "  [bold cyan][1][/bold cyan] JUnit 5"
            "   [bold cyan][2][/bold cyan] NetBeans Templates"
            "   [dim]q  Quit[/dim]\n"
        )
        top = Prompt.ask("  Choice", choices=["1", "2", "q"])
        if top == "q":
            return
        if top == "2":
            _templates_flow(console)
        else:
            _junit5_flow(console)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
    except PermissionError:
        console.print("\n  [red]✗[/red]  Close NetBeans before running this operation.\n")


if __name__ == "__main__":
    main()
