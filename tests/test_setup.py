from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from setup import (
    _BUILD_OVERRIDE,
    _MYSQL_CLASSPATH_KEYS,
    GITIGNORE_MARKER,
    MARKER_BEGIN,
    MARKER_END,
    MYSQL_JAR_NAME,
    add_file_references,
    clean_path,
    download_jars,
    download_mysql_jar,
    fetch_jar_names,
    generate_gitignore,
    inject_build_xml,
    is_gitignore_configured,
    is_junit5_configured,
    is_mysql_configured,
    main,
    modify_classpath,
    remove_build_xml_override,
    remove_file_references,
    remove_gitignore,
    remove_jar_directory,
    revert_classpath,
    run_install,
    run_install_mysql,
    run_uninstall,
    run_uninstall_mysql,
    set_compile_on_save_false,
    validate_netbeans_project,
)

JAR_NAMES = ["junit-jupiter-api-5.10.3.jar", "opentest4j-1.3.0.jar"]

PROPS_ORIGINAL = (
    "compile.on.save=true\n"
    "javac.classpath=\n"
    "javac.test.classpath=\\\n"
    "    ${javac.classpath}:\\\n"
    "    ${build.classes.dir}\n"
    "run.test.classpath=\\\n"
    "    ${javac.test.classpath}:\\\n"
    "    ${build.test.classes.dir}\n"
)

PROPS_WITH_MAIN_CLASSPATH = (
    "compile.on.save=false\n"
    "javac.classpath=\n"
    "run.classpath=\\\n"
    "    ${javac.classpath}:\\\n"
    "    ${build.classes.dir}\n"
    "javac.test.classpath=\\\n"
    "    ${javac.classpath}:\\\n"
    "    ${build.test.classes.dir}\n"
    "run.test.classpath=\\\n"
    "    ${javac.test.classpath}:\\\n"
    "    ${build.test.classes.dir}\n"
)

BUILD_XML_ORIGINAL = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<project name="TestProject" default="default" basedir=".">\n'
    '    <import file="nbproject/build-impl.xml"/>\n'
    "</project>\n"
)

OVERRIDE_CONTENT = '<target name="-do-test-run">\n    <junitlauncher/>\n</target>\n'

MYSQL_JAR_BYTES = b"fake-mysql-jar"


@pytest.fixture()  # type: ignore[untyped-decorator]
def project(tmp_path: Path) -> Path:
    (tmp_path / "nbproject").mkdir()
    (tmp_path / "build.xml").write_text(BUILD_XML_ORIGINAL)
    (tmp_path / "nbproject" / "project.properties").write_text(PROPS_ORIGINAL)
    return tmp_path


@pytest.fixture()  # type: ignore[untyped-decorator]
def mysql_project(tmp_path: Path) -> Path:
    (tmp_path / "nbproject").mkdir()
    (tmp_path / "build.xml").write_text(BUILD_XML_ORIGINAL)
    (tmp_path / "nbproject" / "project.properties").write_text(PROPS_WITH_MAIN_CLASSPATH)
    return tmp_path


@pytest.fixture()  # type: ignore[untyped-decorator]
def properties(project: Path) -> Path:
    return project / "nbproject" / "project.properties"


@pytest.fixture()  # type: ignore[untyped-decorator]
def build_xml(project: Path) -> Path:
    return project / "build.xml"


class TestValidateNetbeansProject:
    def test_raises_when_dir_missing(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            validate_netbeans_project(tmp_path / "nonexistent")

    def test_raises_when_build_xml_missing(self, tmp_path: Path) -> None:
        (tmp_path / "nbproject").mkdir()
        (tmp_path / "nbproject" / "project.properties").write_text("")
        with pytest.raises(ValueError, match="build.xml"):
            validate_netbeans_project(tmp_path)

    def test_raises_when_properties_missing(self, tmp_path: Path) -> None:
        (tmp_path / "build.xml").write_text("")
        with pytest.raises(ValueError, match="project.properties"):
            validate_netbeans_project(tmp_path)

    def test_passes_for_valid_project(self, project: Path) -> None:
        validate_netbeans_project(project)


class TestIsJunit5Configured:
    def test_false_when_jar_dir_missing(self, project: Path) -> None:
        assert is_junit5_configured(project) is False

    def test_false_when_jar_dir_exists_but_no_markers(self, project: Path, build_xml: Path) -> None:
        (project / "lib" / "junit5").mkdir(parents=True)
        assert is_junit5_configured(project) is False

    def test_true_when_jar_dir_and_markers_present(self, project: Path, build_xml: Path) -> None:
        (project / "lib" / "junit5").mkdir(parents=True)
        build_xml.write_text(
            BUILD_XML_ORIGINAL.replace(
                '    <import file="nbproject/build-impl.xml"/>',
                f'    <import file="nbproject/build-impl.xml"/>\n    {MARKER_BEGIN}\n    {MARKER_END}',
            )
        )
        assert is_junit5_configured(project) is True


class TestIsMysqlConfigured:
    def test_false_when_jar_missing(self, mysql_project: Path) -> None:
        assert is_mysql_configured(mysql_project) is False

    def test_false_when_jar_exists_but_no_reference(self, mysql_project: Path) -> None:
        jar_dir = mysql_project / "lib" / "mysql"
        jar_dir.mkdir(parents=True)
        (jar_dir / MYSQL_JAR_NAME).write_bytes(b"fake")
        assert is_mysql_configured(mysql_project) is False

    def test_true_when_jar_and_reference_present(self, mysql_project: Path) -> None:
        jar_dir = mysql_project / "lib" / "mysql"
        jar_dir.mkdir(parents=True)
        (jar_dir / MYSQL_JAR_NAME).write_bytes(b"fake")
        properties = mysql_project / "nbproject" / "project.properties"
        properties.write_text(properties.read_text() + f"file.reference.{MYSQL_JAR_NAME}=lib/mysql/{MYSQL_JAR_NAME}\n")
        assert is_mysql_configured(mysql_project) is True


class TestSetCompileOnSaveFalse:
    def test_changes_true_to_false(self, properties: Path) -> None:
        set_compile_on_save_false(properties)
        assert "compile.on.save=false" in properties.read_text()

    def test_removes_true_value(self, properties: Path) -> None:
        set_compile_on_save_false(properties)
        assert "compile.on.save=true" not in properties.read_text()

    def test_idempotent(self, properties: Path) -> None:
        set_compile_on_save_false(properties)
        set_compile_on_save_false(properties)
        assert properties.read_text().count("compile.on.save=false") == 1

    def test_leaves_other_properties_unchanged(self, properties: Path) -> None:
        set_compile_on_save_false(properties)
        content = properties.read_text()
        assert "javac.classpath=" in content
        assert "javac.test.classpath=\\" in content

    def test_adds_property_when_absent(self, tmp_path: Path) -> None:
        properties = tmp_path / "project.properties"
        properties.write_text("javac.classpath=\n")
        set_compile_on_save_false(properties)
        assert "compile.on.save=false" in properties.read_text()

    def test_also_updates_private_properties_when_present(self, properties: Path) -> None:
        private_dir = properties.parent / "private"
        private_dir.mkdir()
        private = private_dir / "private.properties"
        private.write_text("compile.on.save=true\nuser.properties.file=/some/path\n")
        set_compile_on_save_false(properties)
        assert "compile.on.save=false" in private.read_text()
        assert "compile.on.save=true" not in private.read_text()

    def test_skips_private_properties_when_absent(self, properties: Path) -> None:
        set_compile_on_save_false(properties)
        assert "compile.on.save=false" in properties.read_text()


class TestAddFileReferences:
    def test_adds_reference_for_each_jar(self, properties: Path) -> None:
        add_file_references(properties, JAR_NAMES)
        content = properties.read_text()
        assert "file.reference.junit-jupiter-api-5.10.3.jar=lib/junit5/junit-jupiter-api-5.10.3.jar" in content
        assert "file.reference.opentest4j-1.3.0.jar=lib/junit5/opentest4j-1.3.0.jar" in content

    def test_idempotent(self, properties: Path) -> None:
        add_file_references(properties, JAR_NAMES)
        add_file_references(properties, JAR_NAMES)
        content = properties.read_text()
        assert content.count("file.reference.junit-jupiter-api-5.10.3.jar") == 1

    def test_leaves_original_properties_intact(self, properties: Path) -> None:
        add_file_references(properties, JAR_NAMES)
        content = properties.read_text()
        assert "compile.on.save=true" in content
        assert "javac.test.classpath=\\" in content

    def test_uses_custom_lib_dir(self, properties: Path) -> None:
        add_file_references(properties, [MYSQL_JAR_NAME], lib_dir="lib/mysql")
        assert f"file.reference.{MYSQL_JAR_NAME}=lib/mysql/{MYSQL_JAR_NAME}" in properties.read_text()


class TestModifyClasspath:
    def test_appends_jar_refs_to_javac_test_classpath(self, properties: Path) -> None:
        modify_classpath(properties, JAR_NAMES)
        content = properties.read_text()
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" in content
        assert "${file.reference.opentest4j-1.3.0.jar}" in content

    def test_appends_jar_refs_to_run_test_classpath(self, properties: Path) -> None:
        modify_classpath(properties, JAR_NAMES)
        lines = properties.read_text().splitlines()
        in_run_block = False
        found = False
        for line in lines:
            if line.startswith("run.test.classpath="):
                in_run_block = True
            if in_run_block and "file.reference.junit-jupiter-api-5.10.3.jar" in line:
                found = True
                break
            if in_run_block and not line.endswith("\\") and not line.startswith("run.test.classpath"):
                in_run_block = False
        assert found

    def test_last_jar_has_no_continuation(self, properties: Path) -> None:
        modify_classpath(properties, JAR_NAMES)
        lines = properties.read_text().splitlines()
        last_jar_line = next(line for line in reversed(lines) if "file.reference.opentest4j" in line)
        assert not last_jar_line.rstrip().endswith("\\")

    def test_idempotent(self, properties: Path) -> None:
        modify_classpath(properties, JAR_NAMES)
        modify_classpath(properties, JAR_NAMES)
        content = properties.read_text()
        assert content.count("file.reference.junit-jupiter-api-5.10.3.jar") == 2

    def test_custom_keys_target_correct_blocks(self, mysql_project: Path) -> None:
        properties = mysql_project / "nbproject" / "project.properties"
        modify_classpath(properties, [MYSQL_JAR_NAME], keys=_MYSQL_CLASSPATH_KEYS)
        content = properties.read_text()
        assert f"${{file.reference.{MYSQL_JAR_NAME}}}" in content


class TestInjectBuildXml:
    def test_inserts_override_after_import(self, build_xml: Path) -> None:
        inject_build_xml(build_xml, OVERRIDE_CONTENT)
        content = build_xml.read_text()
        assert MARKER_BEGIN in content
        assert MARKER_END in content
        assert "junitlauncher" in content

    def test_markers_appear_after_import_line(self, build_xml: Path) -> None:
        inject_build_xml(build_xml, OVERRIDE_CONTENT)
        content = build_xml.read_text()
        import_pos = content.index('<import file="nbproject/build-impl.xml"/>')
        marker_pos = content.index(MARKER_BEGIN)
        assert marker_pos > import_pos

    def test_preserves_project_tags(self, build_xml: Path) -> None:
        inject_build_xml(build_xml, OVERRIDE_CONTENT)
        content = build_xml.read_text()
        assert content.startswith('<?xml version="1.0"')
        assert content.rstrip().endswith("</project>")

    def test_idempotent(self, build_xml: Path) -> None:
        inject_build_xml(build_xml, OVERRIDE_CONTENT)
        before = build_xml.read_text()
        inject_build_xml(build_xml, OVERRIDE_CONTENT)
        assert build_xml.read_text() == before


class TestBuildOverride:
    def test_contains_junitlauncher_taskdef(self) -> None:
        assert "junitlauncher.confined.JUnitLauncherTask" in _BUILD_OVERRIDE

    def test_taskdef_has_no_unless_attribute(self) -> None:
        assert 'unless="' not in _BUILD_OVERRIDE

    def test_taskdef_has_no_available_element(self) -> None:
        assert "<available" not in _BUILD_OVERRIDE

    def test_contains_ant_junitlauncher_jar_pattern(self) -> None:
        assert "ant-junitlauncher-*.jar" in _BUILD_OVERRIDE

    def test_taskdef_appears_before_targets(self) -> None:
        taskdef_pos = _BUILD_OVERRIDE.index("<taskdef")
        target_pos = _BUILD_OVERRIDE.index("<target")
        assert taskdef_pos < target_pos


class TestRemoveFileReferences:
    def test_removes_junit5_references(self, properties: Path) -> None:
        add_file_references(properties, JAR_NAMES)
        remove_file_references(properties)
        content = properties.read_text()
        assert "file.reference.junit-jupiter-api-5.10.3.jar" not in content
        assert "file.reference.opentest4j-1.3.0.jar" not in content

    def test_leaves_other_references_intact(self, properties: Path) -> None:
        properties.write_text(
            PROPS_ORIGINAL
            + "file.reference.other-lib.jar=some/other/path/other-lib.jar\n"
            + "file.reference.junit-jupiter-api-5.10.3.jar"
            "=lib/junit5/junit-jupiter-api-5.10.3.jar\n"
        )
        remove_file_references(properties)
        content = properties.read_text()
        assert "file.reference.other-lib.jar" in content

    def test_noop_when_no_references(self, properties: Path) -> None:
        original = properties.read_text()
        remove_file_references(properties)
        assert properties.read_text() == original

    def test_custom_lib_dir_removes_only_matching(self, properties: Path) -> None:
        add_file_references(properties, JAR_NAMES)
        add_file_references(properties, [MYSQL_JAR_NAME], lib_dir="lib/mysql")
        remove_file_references(properties, lib_dir="lib/mysql")
        content = properties.read_text()
        assert f"file.reference.{MYSQL_JAR_NAME}" not in content
        assert "file.reference.junit-jupiter-api-5.10.3.jar" in content


class TestRevertClasspath:
    def test_removes_jar_refs_from_classpath(self, properties: Path) -> None:
        modify_classpath(properties, JAR_NAMES)
        revert_classpath(properties)
        content = properties.read_text()
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" not in content
        assert "${file.reference.opentest4j-1.3.0.jar}" not in content

    def test_restores_original_last_line_without_continuation(self, properties: Path) -> None:
        modify_classpath(properties, JAR_NAMES)
        revert_classpath(properties)
        lines = properties.read_text().splitlines()
        build_classes_line = next(line for line in lines if "${build.classes.dir}" in line)
        assert not build_classes_line.rstrip().endswith("\\")

    def test_noop_when_no_jar_refs(self, properties: Path) -> None:
        original = properties.read_text()
        revert_classpath(properties)
        assert properties.read_text() == original


class TestRemoveBuildXmlOverride:
    def test_removes_content_between_markers(self, build_xml: Path) -> None:
        inject_build_xml(build_xml, OVERRIDE_CONTENT)
        remove_build_xml_override(build_xml)
        content = build_xml.read_text()
        assert MARKER_BEGIN not in content
        assert MARKER_END not in content
        assert "junitlauncher" not in content

    def test_preserves_surrounding_xml(self, build_xml: Path) -> None:
        inject_build_xml(build_xml, OVERRIDE_CONTENT)
        remove_build_xml_override(build_xml)
        content = build_xml.read_text()
        assert '<import file="nbproject/build-impl.xml"/>' in content
        assert "</project>" in content

    def test_noop_when_markers_absent(self, build_xml: Path) -> None:
        original = build_xml.read_text()
        remove_build_xml_override(build_xml)
        assert build_xml.read_text() == original


class TestRemoveJarDirectory:
    def test_removes_lib_junit5_directory(self, project: Path) -> None:
        jar_dir = project / "lib" / "junit5"
        jar_dir.mkdir(parents=True)
        (jar_dir / "some.jar").touch()
        remove_jar_directory(project)
        assert not jar_dir.exists()

    def test_noop_when_directory_missing(self, project: Path) -> None:
        remove_jar_directory(project)

    def test_leaves_other_lib_dirs_intact(self, project: Path) -> None:
        (project / "lib" / "junit5").mkdir(parents=True)
        (project / "lib" / "mysql").mkdir(parents=True)
        remove_jar_directory(project)
        assert (project / "lib" / "mysql").exists()


class TestFetchJarNames:
    def test_returns_list_of_jar_filenames(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "junit-jupiter-api-5.10.3.jar", "type": "file"},
            {"name": "opentest4j-1.3.0.jar", "type": "file"},
            {"name": "some-dir", "type": "dir"},
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            names = fetch_jar_names()

        assert "junit-jupiter-api-5.10.3.jar" in names
        assert "opentest4j-1.3.0.jar" in names
        assert "some-dir" not in names

    def test_excludes_non_jar_entries(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "readme.txt", "type": "file"},
            {"name": "junit-platform-engine-1.10.3.jar", "type": "file"},
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            names = fetch_jar_names()

        assert "readme.txt" not in names
        assert "junit-platform-engine-1.10.3.jar" in names


class TestDownloadJars:
    def test_creates_dest_directory(self, tmp_path: Path) -> None:
        destination = tmp_path / "lib" / "junit5"
        mock_response = MagicMock()
        mock_response.content = b"fake-jar-bytes"
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            download_jars(destination, JAR_NAMES)

        assert destination.exists()

    def test_writes_jar_files(self, tmp_path: Path) -> None:
        destination = tmp_path / "lib" / "junit5"
        mock_response = MagicMock()
        mock_response.content = b"fake-jar-bytes"
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            download_jars(destination, JAR_NAMES)

        for name in JAR_NAMES:
            assert (destination / name).exists()

    def test_skips_existing_jars(self, tmp_path: Path) -> None:
        destination = tmp_path / "lib" / "junit5"
        destination.mkdir(parents=True)
        existing = destination / JAR_NAMES[0]
        existing.write_bytes(b"already-here")

        mock_response = MagicMock()
        mock_response.content = b"new-bytes"
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            download_jars(destination, JAR_NAMES)

        called_urls = [call.args[0] for call in mock_get.call_args_list]
        assert not any(JAR_NAMES[0] in request_url for request_url in called_urls)


class TestDownloadMysqlJar:
    @patch("requests.get")
    def test_creates_dest_and_writes_jar(self, mock_get: MagicMock, tmp_path: Path) -> None:
        destination = tmp_path / "lib" / "mysql"
        mock_get.return_value.content = MYSQL_JAR_BYTES
        mock_get.return_value.raise_for_status = MagicMock()
        download_mysql_jar(destination)
        assert (destination / MYSQL_JAR_NAME).read_bytes() == MYSQL_JAR_BYTES

    @patch("requests.get")
    def test_skips_existing_jar(self, mock_get: MagicMock, tmp_path: Path) -> None:
        destination = tmp_path / "lib" / "mysql"
        destination.mkdir(parents=True)
        (destination / MYSQL_JAR_NAME).write_bytes(b"existing")
        mock_get.return_value.content = MYSQL_JAR_BYTES
        mock_get.return_value.raise_for_status = MagicMock()
        download_mysql_jar(destination)
        mock_get.assert_not_called()
        assert (destination / MYSQL_JAR_NAME).read_bytes() == b"existing"


class TestRunInstallMysql:
    def test_raises_for_invalid_project(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            run_install_mysql(tmp_path)

    def test_downloads_jar_to_lib_mysql(self, mysql_project: Path) -> None:
        with patch("setup.download_mysql_jar") as mock_download:
            run_install_mysql(mysql_project)
        mock_download.assert_called_once_with(mysql_project / "lib" / "mysql")

    def test_adds_file_reference(self, mysql_project: Path) -> None:
        with patch("setup.download_mysql_jar"):
            run_install_mysql(mysql_project)
        content = (mysql_project / "nbproject" / "project.properties").read_text()
        assert f"file.reference.{MYSQL_JAR_NAME}=lib/mysql/{MYSQL_JAR_NAME}" in content

    def test_adds_to_javac_classpath(self, mysql_project: Path) -> None:
        with patch("setup.download_mysql_jar"):
            run_install_mysql(mysql_project)
        content = (mysql_project / "nbproject" / "project.properties").read_text()
        assert f"${{file.reference.{MYSQL_JAR_NAME}}}" in content

    def test_idempotent(self, mysql_project: Path) -> None:
        with patch("setup.download_mysql_jar"):
            run_install_mysql(mysql_project)
            run_install_mysql(mysql_project)
        content = (mysql_project / "nbproject" / "project.properties").read_text()
        assert content.count(f"file.reference.{MYSQL_JAR_NAME}=lib/mysql/") == 1


class TestRunUninstallMysql:
    def test_removes_lib_mysql_directory(self, mysql_project: Path) -> None:
        jar_dir = mysql_project / "lib" / "mysql"
        jar_dir.mkdir(parents=True)
        (jar_dir / MYSQL_JAR_NAME).write_bytes(b"fake")
        run_uninstall_mysql(mysql_project)
        assert not jar_dir.exists()

    def test_removes_file_references(self, mysql_project: Path) -> None:
        properties = mysql_project / "nbproject" / "project.properties"
        add_file_references(properties, [MYSQL_JAR_NAME], lib_dir="lib/mysql")
        run_uninstall_mysql(mysql_project)
        assert f"file.reference.{MYSQL_JAR_NAME}" not in properties.read_text()

    def test_reverts_classpath(self, mysql_project: Path) -> None:
        properties = mysql_project / "nbproject" / "project.properties"
        modify_classpath(properties, [MYSQL_JAR_NAME], keys=_MYSQL_CLASSPATH_KEYS)
        run_uninstall_mysql(mysql_project)
        assert f"${{file.reference.{MYSQL_JAR_NAME}}}" not in properties.read_text()

    def test_noop_when_lib_dir_missing(self, mysql_project: Path) -> None:
        run_uninstall_mysql(mysql_project)

    def test_full_install_uninstall_cycle(self, mysql_project: Path) -> None:
        with patch("setup.download_mysql_jar"):
            run_install_mysql(mysql_project)
        run_uninstall_mysql(mysql_project)
        properties = (mysql_project / "nbproject" / "project.properties").read_text()
        assert f"file.reference.{MYSQL_JAR_NAME}" not in properties


class TestMain:
    def test_handles_keyboard_interrupt_gracefully(self) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
        ):
            mock_q.select.return_value.ask.side_effect = KeyboardInterrupt
            main()

    def test_quits_on_top_level_quit(self) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_install") as mock_install,
        ):
            mock_q.select.return_value.ask.return_value = "quit"
            main()
        mock_install.assert_not_called()

    def test_calls_run_install_for_junit5(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_install") as mock_install,
            patch("setup.is_junit5_configured", return_value=False),
        ):
            mock_q.select.return_value.ask.side_effect = [
                "junit5",
                "install",
                "back",
                "quit",
            ]
            mock_q.text.return_value.ask.return_value = str(project)
            main()
        mock_install.assert_called_once_with(project)

    def test_calls_run_uninstall_for_junit5(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_uninstall") as mock_uninstall,
            patch("setup.is_junit5_configured", return_value=True),
        ):
            mock_q.select.return_value.ask.side_effect = [
                "junit5",
                "uninstall",
                "back",
                "quit",
            ]
            mock_q.text.return_value.ask.return_value = str(project)
            main()
        mock_uninstall.assert_called_once_with(project)

    def test_calls_run_install_mysql(self, mysql_project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_install_mysql") as mock_install,
            patch("setup.is_mysql_configured", return_value=False),
        ):
            mock_q.select.return_value.ask.side_effect = [
                "database",
                "install",
                "back",
                "quit",
            ]
            mock_q.text.return_value.ask.return_value = str(mysql_project)
            main()
        mock_install.assert_called_once_with(mysql_project)

    def test_calls_run_uninstall_mysql(self, mysql_project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_uninstall_mysql") as mock_uninstall,
            patch("setup.is_mysql_configured", return_value=True),
        ):
            mock_q.select.return_value.ask.side_effect = [
                "database",
                "uninstall",
                "back",
                "quit",
            ]
            mock_q.text.return_value.ask.return_value = str(mysql_project)
            main()
        mock_uninstall.assert_called_once_with(mysql_project)

    def test_calls_download_template_zip(self, tmp_path: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.download_template_zip", return_value=tmp_path / "Template.zip") as mock_dl,
        ):
            mock_q.select.return_value.ask.side_effect = ["templates", "back", "quit"]
            mock_q.text.return_value.ask.return_value = str(tmp_path)
            main()
        mock_dl.assert_called_once_with(tmp_path)

    def test_handles_invalid_project_gracefully(self, tmp_path: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
        ):
            mock_q.select.return_value.ask.side_effect = ["junit5", "back", "quit"]
            mock_q.text.return_value.ask.return_value = str(tmp_path)
            main()

    def test_handles_permission_error_gracefully(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_install", side_effect=PermissionError("file in use")),
            patch("setup.is_junit5_configured", return_value=False),
        ):
            mock_q.select.return_value.ask.side_effect = ["junit5", "install"]
            mock_q.text.return_value.ask.return_value = str(project)
            main()

    def test_back_returns_to_main_menu(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_install") as mock_install,
            patch("setup.is_junit5_configured", return_value=False),
        ):
            mock_q.select.return_value.ask.side_effect = ["junit5", "back", "quit"]
            mock_q.text.return_value.ask.return_value = str(project)
            main()
        mock_install.assert_not_called()

    def test_quits_after_nav_quit(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.run_install") as mock_install,
            patch("setup.is_junit5_configured", return_value=False),
        ):
            mock_q.select.return_value.ask.side_effect = ["junit5", "install", "quit"]
            mock_q.text.return_value.ask.return_value = str(project)
            main()
        mock_install.assert_called_once_with(project)


class TestCleanPath:
    def test_strips_single_quotes(self) -> None:
        assert clean_path("'/some/path'") == Path("/some/path")

    def test_strips_double_quotes(self) -> None:
        assert clean_path('"/some/path"') == Path("/some/path")

    def test_strips_trailing_slash(self) -> None:
        assert clean_path("/some/path/") == Path("/some/path")

    def test_strips_whitespace(self) -> None:
        assert clean_path("  /some/path  ") == Path("/some/path")

    def test_returns_path_object(self) -> None:
        assert isinstance(clean_path("/some/path"), Path)

    def test_plain_path_unchanged(self) -> None:
        assert clean_path("/some/path") == Path("/some/path")

    def test_dot_resolves_to_cwd(self) -> None:
        assert clean_path(".") == Path.cwd()

    def test_tilde_expands_home(self) -> None:
        assert clean_path("~") == Path.home()


class TestRunInstall:
    def test_raises_for_invalid_project(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            run_install(tmp_path)

    def test_sets_compile_on_save_false(self, project: Path) -> None:
        with (
            patch("setup.fetch_jar_names", return_value=JAR_NAMES),
            patch("setup.download_jars"),
        ):
            run_install(project)
        assert "compile.on.save=false" in (project / "nbproject" / "project.properties").read_text()

    def test_adds_file_references(self, project: Path) -> None:
        with (
            patch("setup.fetch_jar_names", return_value=JAR_NAMES),
            patch("setup.download_jars"),
        ):
            run_install(project)
        content = (project / "nbproject" / "project.properties").read_text()
        assert "file.reference.junit-jupiter-api-5.10.3.jar" in content

    def test_modifies_classpath(self, project: Path) -> None:
        with (
            patch("setup.fetch_jar_names", return_value=JAR_NAMES),
            patch("setup.download_jars"),
        ):
            run_install(project)
        content = (project / "nbproject" / "project.properties").read_text()
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" in content

    def test_injects_build_xml(self, project: Path) -> None:
        with (
            patch("setup.fetch_jar_names", return_value=JAR_NAMES),
            patch("setup.download_jars"),
        ):
            run_install(project)
        assert MARKER_BEGIN in (project / "build.xml").read_text()

    def test_downloads_jars_to_correct_path(self, project: Path) -> None:
        with (
            patch("setup.fetch_jar_names", return_value=JAR_NAMES),
            patch("setup.download_jars") as mock_download,
        ):
            run_install(project)
        mock_download.assert_called_once_with(project / "lib" / "junit5", JAR_NAMES)

    def test_idempotent(self, project: Path) -> None:
        with (
            patch("setup.fetch_jar_names", return_value=JAR_NAMES),
            patch("setup.download_jars"),
        ):
            run_install(project)
            run_install(project)
        content = (project / "nbproject" / "project.properties").read_text()
        assert content.count("file.reference.junit-jupiter-api-5.10.3.jar=lib/junit5/") == 1


class TestRunUninstall:
    def test_removes_jar_directory(self, project: Path) -> None:
        (project / "lib" / "junit5").mkdir(parents=True)
        run_uninstall(project)
        assert not (project / "lib" / "junit5").exists()

    def test_removes_file_references(self, project: Path) -> None:
        properties = project / "nbproject" / "project.properties"
        add_file_references(properties, JAR_NAMES)
        run_uninstall(project)
        assert "file.reference.junit-jupiter-api-5.10.3.jar" not in properties.read_text()

    def test_reverts_classpath(self, project: Path) -> None:
        properties = project / "nbproject" / "project.properties"
        modify_classpath(properties, JAR_NAMES)
        run_uninstall(project)
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" not in properties.read_text()

    def test_removes_build_xml_markers(self, project: Path) -> None:
        inject_build_xml(project / "build.xml", OVERRIDE_CONTENT)
        run_uninstall(project)
        assert MARKER_BEGIN not in (project / "build.xml").read_text()

    def test_full_install_uninstall_cycle(self, project: Path) -> None:
        with (
            patch("setup.fetch_jar_names", return_value=JAR_NAMES),
            patch("setup.download_jars"),
        ):
            run_install(project)
        run_uninstall(project)
        properties = (project / "nbproject" / "project.properties").read_text()
        assert "file.reference.junit-jupiter-api-5.10.3.jar" not in properties
        assert MARKER_BEGIN not in (project / "build.xml").read_text()


class TestIsGitignoreConfigured:
    def test_returns_false_when_no_gitignore(self, project: Path) -> None:
        assert not is_gitignore_configured(project)

    def test_returns_false_when_gitignore_has_no_marker(self, project: Path) -> None:
        (project / ".gitignore").write_text("*.class\n")
        assert not is_gitignore_configured(project)

    def test_returns_true_when_marker_present(self, project: Path) -> None:
        (project / ".gitignore").write_text(f"{GITIGNORE_MARKER}\n*.class\n")
        assert is_gitignore_configured(project)


class TestGenerateGitignore:
    def test_creates_gitignore_file(self, project: Path) -> None:
        generate_gitignore(project)
        assert (project / ".gitignore").is_file()

    def test_file_contains_marker(self, project: Path) -> None:
        generate_gitignore(project)
        assert GITIGNORE_MARKER in (project / ".gitignore").read_text()

    def test_file_contains_java_patterns(self, project: Path) -> None:
        generate_gitignore(project)
        content = (project / ".gitignore").read_text()
        assert "*.class" in content
        assert "/build/" in content

    def test_file_contains_netbeans_patterns(self, project: Path) -> None:
        generate_gitignore(project)
        content = (project / ".gitignore").read_text()
        assert "nbproject/private/" in content

    def test_idempotent(self, project: Path) -> None:
        generate_gitignore(project)
        generate_gitignore(project)
        content = (project / ".gitignore").read_text()
        assert content.count(GITIGNORE_MARKER) == 1


class TestRemoveGitignore:
    def test_removes_gitignore_when_marker_present(self, project: Path) -> None:
        generate_gitignore(project)
        remove_gitignore(project)
        assert not (project / ".gitignore").exists()

    def test_noop_when_no_gitignore(self, project: Path) -> None:
        remove_gitignore(project)

    def test_does_not_remove_gitignore_without_marker(self, project: Path) -> None:
        (project / ".gitignore").write_text("*.class\n")
        remove_gitignore(project)
        assert (project / ".gitignore").exists()


class TestMainGitignore:
    def test_calls_generate_gitignore(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.generate_gitignore") as mock_gen,
            patch("setup.is_gitignore_configured", return_value=False),
        ):
            mock_q.select.return_value.ask.side_effect = [
                "gitignore",
                "generate",
                "back",
                "quit",
            ]
            mock_q.text.return_value.ask.return_value = str(project)
            main()
        mock_gen.assert_called_once_with(project)

    def test_calls_remove_gitignore(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.questionary") as mock_q,
            patch("setup.remove_gitignore") as mock_remove,
            patch("setup.is_gitignore_configured", return_value=True),
        ):
            mock_q.select.return_value.ask.side_effect = [
                "gitignore",
                "remove",
                "back",
                "quit",
            ]
            mock_q.text.return_value.ask.return_value = str(project)
            main()
        mock_remove.assert_called_once_with(project)
