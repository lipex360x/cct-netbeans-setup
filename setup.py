# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13", "requests>=2", "questionary>=2", "pyyaml>=6"]
# ///

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import questionary
import requests
import yaml
from rich.console import Console
from rich.panel import Panel

MARKER_BEGIN = "<!-- cct-netbeans-setup:begin -->"
MARKER_END = "<!-- cct-netbeans-setup:end -->"
GITIGNORE_MARKER = "# cct-netbeans-setup"

GITHUB_REPO = "lipex360x/cct-netbeans-setup"
GITHUB_BRANCH = "main"
GITHUB_JARS_PATH = "libs/tests/junit5/jar"
GITHUB_SETUP_ZIP_PATH = "templates/Template.zip"
GITHUB_MYSQL_JAR_PATH = "libs/database/mysql/mysql-connector-j.jar"
GITHUB_GITIGNORE_PATH = "templates/gitignore"
GITHUB_DOCKER_COMPOSE_PATH = "libs/docker/docker-compose.yml"
GITHUB_DESCRIPTIONS_PATH = "templates/descriptions.yaml"
MYSQL_JAR_NAME = "mysql-connector-j.jar"

_GITHUB_API = "https://api.github.com/repos"
_GITHUB_RAW = "https://raw.githubusercontent.com"

_JUNIT5_CLASSPATH_KEYS = ("javac.test.classpath=", "run.test.classpath=")
_MYSQL_CLASSPATH_KEYS = ("javac.classpath=", "run.classpath=")

_STYLE = questionary.Style(
    [
        ("qmark", "fg:#00d7ff bold"),
        ("question", "bold"),
        ("answer", "fg:#00d7ff bold"),
        ("pointer", "fg:#00d7ff bold"),
        ("highlighted", "fg:#00d7ff bold"),
        ("selected", "fg:#00d7ff"),
    ]
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


def is_mysql_configured(path: Path) -> bool:
    if not (path / "lib" / "mysql" / MYSQL_JAR_NAME).is_file():
        return False
    properties = path / "nbproject" / "project.properties"
    return f"file.reference.{MYSQL_JAR_NAME}=" in properties.read_text()


def set_compile_on_save_false(properties: Path) -> None:
    private = properties.parent / "private" / "private.properties"
    for target in [properties, private]:
        if not target.is_file():
            continue
        content = target.read_text()
        if "compile.on.save=false" in content:
            continue
        if "compile.on.save=true" in content:
            target.write_text(content.replace("compile.on.save=true", "compile.on.save=false"))
        else:
            target.write_text(content.rstrip("\n") + "\ncompile.on.save=false\n")


def add_file_references(properties: Path, jar_names: list[str], lib_dir: str = "lib/junit5") -> None:
    content = properties.read_text()
    additions = []
    for name in jar_names:
        key = f"file.reference.{name}"
        if f"{key}=" not in content:
            additions.append(f"{key}={lib_dir}/{name}")
    if additions:
        properties.write_text(content.rstrip("\n") + "\n" + "\n".join(additions) + "\n")


def modify_classpath(
    properties: Path,
    jar_names: list[str],
    keys: tuple[str, ...] = _JUNIT5_CLASSPATH_KEYS,
) -> None:
    lines = properties.read_text().splitlines(keepends=True)
    result: list[str] = []
    in_block = False
    block_has_refs = False

    for line in lines:
        stripped = line.rstrip("\n")
        if any(stripped.startswith(key) for key in keys):
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

    properties.write_text("".join(result))


def inject_build_xml(build_xml: Path, override_content: str) -> None:
    content = build_xml.read_text()
    if MARKER_BEGIN in content:
        return
    marker = '<import file="nbproject/build-impl.xml"/>'
    injection = f"{MARKER_BEGIN}\n{override_content.rstrip()}\n{MARKER_END}"
    content = content.replace(marker, f"{marker}\n\n    {injection}")
    build_xml.write_text(content)


def remove_file_references(properties: Path, lib_dir: str = "lib/junit5") -> None:
    lines = properties.read_text().splitlines(keepends=True)
    filtered = [line for line in lines if not (line.startswith("file.reference.") and f"{lib_dir}/" in line)]
    properties.write_text("".join(filtered))


def revert_classpath(properties: Path, keys: tuple[str, ...] = _JUNIT5_CLASSPATH_KEYS) -> None:
    def flush(buffer: list[str]) -> list[str]:
        filtered = [line for line in buffer if "${file.reference." not in line]
        if len(filtered) < len(buffer) and filtered:
            last = filtered[-1].rstrip("\n")
            if last.endswith(":\\"):
                filtered[-1] = last[:-2] + "\n"
        return filtered

    lines = properties.read_text().splitlines(keepends=True)
    result: list[str] = []
    in_block = False
    buffer: list[str] = []

    for line in lines:
        stripped = line.rstrip("\n")
        if any(stripped.startswith(key) for key in keys):
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

    properties.write_text("".join(result))


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
    api_url = f"{_GITHUB_API}/{GITHUB_REPO}/contents/{GITHUB_JARS_PATH}?ref={GITHUB_BRANCH}"
    response = requests.get(api_url, timeout=10)
    response.raise_for_status()
    entries = response.json()
    return [entry["name"] for entry in entries if entry["type"] == "file" and entry["name"].endswith(".jar")]


def download_jars(destination: Path, jar_names: list[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in jar_names:
        target = destination / name
        if target.exists():
            continue
        jar_url = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_JARS_PATH}/{name}"
        response = requests.get(jar_url, timeout=30)
        response.raise_for_status()
        target.write_bytes(response.content)


def download_mysql_jar(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / MYSQL_JAR_NAME
    if target.exists():
        return
    jar_url = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_MYSQL_JAR_PATH}"
    response = requests.get(jar_url, timeout=30)
    response.raise_for_status()
    target.write_bytes(response.content)


def download_template_zip(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    zip_url = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_SETUP_ZIP_PATH}"
    response = requests.get(zip_url, timeout=30)
    response.raise_for_status()
    out = destination / "Template.zip"
    out.write_bytes(response.content)
    return out


_DEPENDS_SINGLE = "init,compile-test-single,-pre-test-run-single"

_JUNITLAUNCHER_CLASS = "org.apache.tools.ant.taskdefs.optional.junitlauncher.confined.JUnitLauncherTask"

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


def fetch_descriptions() -> dict[str, dict[str, str]]:
    try:
        endpoint = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_DESCRIPTIONS_PATH}"
        response = requests.get(endpoint, timeout=5)
        response.raise_for_status()
        return dict(yaml.safe_load(response.text) or {})
    except Exception:
        return {}


def download_gitignore_template() -> str:
    endpoint = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_GITIGNORE_PATH}"
    response = requests.get(endpoint, timeout=10)
    response.raise_for_status()
    return str(response.text)


def is_docker_running() -> bool:
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_docker_compose_configured(project: Path) -> bool:
    return (project / "docker-compose.yml").is_file()


def download_docker_compose(project: Path) -> None:
    endpoint = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_DOCKER_COMPOSE_PATH}"
    response = requests.get(endpoint, timeout=10)
    response.raise_for_status()
    (project / "docker-compose.yml").write_text(response.text)


def remove_docker_compose(project: Path) -> None:
    target = project / "docker-compose.yml"
    if target.is_file():
        target.unlink()


def _gitignore_file(project: Path) -> Path:
    return project / ".gitignore"


def _properties_file(project: Path) -> Path:
    return project / "nbproject" / "project.properties"


def is_gitignore_configured(project: Path) -> bool:
    gitignore = _gitignore_file(project)
    return gitignore.is_file() and GITIGNORE_MARKER in gitignore.read_text()


def generate_gitignore(project: Path) -> None:
    gitignore = _gitignore_file(project)
    if gitignore.is_file() and GITIGNORE_MARKER in gitignore.read_text():
        return
    gitignore.write_text(download_gitignore_template())


def remove_gitignore(project: Path) -> None:
    gitignore = _gitignore_file(project)
    if gitignore.is_file() and GITIGNORE_MARKER in gitignore.read_text():
        gitignore.unlink()


def run_install(project: Path) -> None:
    validate_netbeans_project(project)
    jar_names = fetch_jar_names()
    download_jars(project / "lib" / "junit5", jar_names)
    properties = _properties_file(project)
    set_compile_on_save_false(properties)
    add_file_references(properties, jar_names)
    modify_classpath(properties, jar_names)
    inject_build_xml(project / "build.xml", _BUILD_OVERRIDE)


def run_uninstall(project: Path) -> None:
    properties = _properties_file(project)
    remove_jar_directory(project)
    remove_file_references(properties)
    revert_classpath(properties)
    remove_build_xml_override(project / "build.xml")


def run_install_mysql(project: Path) -> None:
    validate_netbeans_project(project)
    download_mysql_jar(project / "lib" / "mysql")
    properties = _properties_file(project)
    add_file_references(properties, [MYSQL_JAR_NAME], lib_dir="lib/mysql")
    modify_classpath(properties, [MYSQL_JAR_NAME], keys=_MYSQL_CLASSPATH_KEYS)


def run_uninstall_mysql(project: Path) -> None:
    jar_dir = project / "lib" / "mysql"
    if jar_dir.is_dir():
        shutil.rmtree(jar_dir)
    properties = _properties_file(project)
    remove_file_references(properties, lib_dir="lib/mysql")
    revert_classpath(properties, keys=_MYSQL_CLASSPATH_KEYS)


def _print_section(console: Console, heading: str = "", description: str = "") -> None:
    if heading:
        body = f"[bold]>> {heading}[/bold]"
        if description:
            body += f"\n{description.strip()}"
    else:
        body = "Select an option to install"
    console.print(
        Panel(
            body,
            title="[bold cyan]NetBeans — CCT Setup[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )


def _nav_choice() -> str:
    result = questionary.select(
        "",
        choices=[
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ],
        style=_STYLE,
    ).ask()
    return result or "quit"


def _database_flow(console: Console, title: str = "", description: str = "") -> str:
    _print_section(console, title, description)
    project = Path.cwd()
    try:
        validate_netbeans_project(project)
    except ValueError as error:
        console.print(f"\n  [red]✗[/red]  {error}\n")
        return _nav_choice()
    configured = is_mysql_configured(project)
    status_text = "[green]● installed[/green]" if configured else "[yellow]○ not installed[/yellow]"
    console.print(
        Panel(
            f"  [dim]{project}[/dim]\n  [bold]MySQL Connector[/bold]   {status_text}",
            title=f"[bold cyan]{project.name}[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )
    if configured:
        choices = [
            questionary.Choice("Uninstall MySQL Connector", value="uninstall"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    else:
        choices = [
            questionary.Choice("Install MySQL Connector", value="install"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    action = questionary.select("", choices=choices, style=_STYLE).ask()
    if action in (None, "back"):
        return "back"
    if action == "quit":
        return "quit"
    if action == "install":
        with console.status("[cyan]Downloading MySQL Connector...[/cyan]"):
            run_install_mysql(project)
        console.print("\n  [green]✓[/green]  MySQL Connector installed.\n")
    else:
        with console.status("[cyan]Uninstalling MySQL Connector...[/cyan]"):
            run_uninstall_mysql(project)
        console.print("\n  [green]✓[/green]  MySQL Connector uninstalled.\n")
    return _nav_choice()


def _junit5_flow(console: Console, title: str = "", description: str = "") -> str:
    _print_section(console, title, description)
    project = Path.cwd()
    try:
        validate_netbeans_project(project)
    except ValueError as error:
        console.print(f"\n  [red]✗[/red]  {error}\n")
        return _nav_choice()
    configured = is_junit5_configured(project)
    status_text = "[green]● installed[/green]" if configured else "[yellow]○ not installed[/yellow]"
    console.print(
        Panel(
            f"  [dim]{project}[/dim]\n  [bold]JUnit 5[/bold]   {status_text}",
            title=f"[bold cyan]{project.name}[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )
    if configured:
        choices = [
            questionary.Choice("Uninstall JUnit 5", value="uninstall"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    else:
        choices = [
            questionary.Choice("Install JUnit 5", value="install"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    action = questionary.select("", choices=choices, style=_STYLE).ask()
    if action in (None, "back"):
        return "back"
    if action == "quit":
        return "quit"
    if action == "install":
        with console.status("[cyan]Installing JUnit 5...[/cyan]"):
            run_install(project)
        console.print("\n  [green]✓[/green]  JUnit 5 installed.\n")
    else:
        with console.status("[cyan]Uninstalling JUnit 5...[/cyan]"):
            run_uninstall(project)
        console.print("\n  [green]✓[/green]  JUnit 5 uninstalled.\n")
    return _nav_choice()


def _gitignore_flow(console: Console, title: str = "", description: str = "") -> str:
    _print_section(console, title, description)
    project = Path.cwd()
    configured = is_gitignore_configured(project)
    status_text = "[green]● generated[/green]" if configured else "[yellow]○ not generated[/yellow]"
    console.print(
        Panel(
            f"  [dim]{project}[/dim]\n  [bold].gitignore[/bold]   {status_text}",
            title=f"[bold cyan]{project.name}[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )
    if configured:
        choices = [
            questionary.Choice("Remove .gitignore", value="remove"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    else:
        choices = [
            questionary.Choice("Generate .gitignore", value="generate"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    action = questionary.select("", choices=choices, style=_STYLE).ask()
    if action in (None, "back"):
        return "back"
    if action == "quit":
        return "quit"
    if action == "generate":
        generate_gitignore(project)
        console.print("\n  [green]✓[/green]  .gitignore generated.\n")
    else:
        remove_gitignore(project)
        console.print("\n  [green]✓[/green]  .gitignore removed.\n")
    return _nav_choice()


def _docker_compose_flow(console: Console, title: str = "", description: str = "") -> str:
    _print_section(console, title, description)
    project = Path.cwd()
    docker_running = is_docker_running()
    configured = is_docker_compose_configured(project)
    daemon_text = "[green]● running[/green]" if docker_running else "[red]● not running[/red]"
    compose_text = "[green]● configured[/green]" if configured else "[yellow]○ not configured[/yellow]"
    body = (
        f"  [dim]{project}[/dim]\n"
        f"  [bold]Docker daemon[/bold]      {daemon_text}\n"
        f"  [bold]Docker Compose[/bold]     {compose_text}"
    )
    console.print(
        Panel(
            body,
            title=f"[bold cyan]{project.name}[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )
    if not docker_running:
        console.print("  [dim]Start Docker Desktop and try again.[/dim]\n")
        return _nav_choice()
    if configured:
        choices = [
            questionary.Choice("Remove docker-compose.yml", value="remove"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    else:
        choices = [
            questionary.Choice("Add docker-compose.yml", value="add"),
            questionary.Choice("Back to menu", value="back"),
            questionary.Choice("Quit", value="quit"),
        ]
    action = questionary.select("", choices=choices, style=_STYLE).ask()
    if action in (None, "back"):
        return "back"
    if action == "quit":
        return "quit"
    if action == "add":
        with console.status("[cyan]Downloading docker-compose.yml...[/cyan]"):
            download_docker_compose(project)
        console.print("\n  [green]✓[/green]  docker-compose.yml added.\n")
    else:
        remove_docker_compose(project)
        console.print("\n  [green]✓[/green]  docker-compose.yml removed.\n")
    return _nav_choice()


def _templates_flow(console: Console, title: str = "", description: str = "") -> str:
    _print_section(console, title, description)
    destination = Path.cwd()
    with console.status("[cyan]Downloading Template.zip...[/cyan]"):
        saved = download_template_zip(destination)
    console.print(
        Panel(
            f"\n  [green]✓[/green]  Saved to [bold]{saved}[/bold]\n\n"
            "  [bold]To apply in NetBeans:[/bold]\n"
            "  1. Open NetBeans\n"
            "  2. Go to [bold cyan]Tools → Options → Import[/bold cyan]\n"
            "  3. Select the downloaded [bold]Template.zip[/bold]\n"
            "  4. Restart NetBeans\n",
            title="[bold cyan]NetBeans Templates[/bold cyan]",
            border_style="cyan",
            title_align="left",
        )
    )
    return _nav_choice()


def _dot(configured: bool) -> str:
    return "●" if configured else "○"


def _feature_dots(project: Path) -> dict[str, str]:
    try:
        validate_netbeans_project(project)
    except ValueError:
        return {}
    return {
        "database": _dot(is_mysql_configured(project)),
        "junit5": _dot(is_junit5_configured(project)),
        "docker": _dot(is_docker_compose_configured(project)),
        "gitignore": _dot(is_gitignore_configured(project)),
    }


def _menu_label(indicators: dict[str, str], key: str, label: str) -> str:
    if not indicators:
        return label
    return f"{indicators.get(key, ' ')} {label}"


def _run_flow(console: Console, choice: str, descriptions: dict[str, dict[str, str]]) -> str:
    entry = descriptions.get(choice, {})
    title = entry.get("title", "")
    description = entry.get("description", "")
    if choice == "database":
        return _database_flow(console, title, description)
    if choice == "junit5":
        return _junit5_flow(console, title, description)
    if choice == "docker":
        return _docker_compose_flow(console, title, description)
    if choice == "gitignore":
        return _gitignore_flow(console, title, description)
    return _templates_flow(console, title, description)


def main() -> None:
    console = Console()
    descriptions = fetch_descriptions()
    project = Path.cwd()
    try:
        try:
            validate_netbeans_project(project)
        except ValueError:
            _print_section(console)
            console.print("\n  [red]✗[/red]  Not a valid Java project directory.\n")
            questionary.select("", choices=[questionary.Choice("Quit", value="quit")], style=_STYLE).ask()
            return
        while True:
            _print_section(console)
            indicators = _feature_dots(project)
            choice = questionary.select(
                "Select an option:",
                choices=[
                    questionary.Choice(
                        _menu_label(indicators, "database", "[1] MySQL Database"),
                        value="database",
                    ),
                    questionary.Choice(_menu_label(indicators, "junit5", "[2] JUnit 5"), value="junit5"),
                    questionary.Choice(
                        _menu_label(indicators, "docker", "[3] Docker Compose"),
                        value="docker",
                    ),
                    questionary.Choice(
                        _menu_label(indicators, "gitignore", "[4] .gitignore"),
                        value="gitignore",
                    ),
                    questionary.Choice(
                        _menu_label(indicators, "templates", "[5] NetBeans Templates"),
                        value="templates",
                    ),
                    questionary.Choice("Quit", value="quit"),
                ],
                style=_STYLE,
            ).ask()
            if choice in (None, "quit"):
                break
            if _run_flow(console, choice, descriptions) == "quit":
                break
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
    except PermissionError:
        console.print("\n  [red]✗[/red]  Close NetBeans before running this operation.\n")


if __name__ == "__main__":
    main()
