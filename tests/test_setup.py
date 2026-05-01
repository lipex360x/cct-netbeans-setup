from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from setup import (
    MARKER_BEGIN,
    MARKER_END,
    add_file_references,
    clean_path,
    download_jars,
    fetch_jar_names,
    inject_build_xml,
    is_junit5_configured,
    main,
    modify_classpath,
    remove_build_xml_override,
    remove_file_references,
    remove_jar_directory,
    revert_classpath,
    run_install,
    run_uninstall,
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

BUILD_XML_ORIGINAL = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<project name="TestProject" default="default" basedir=".">\n'
    '    <import file="nbproject/build-impl.xml"/>\n'
    "</project>\n"
)

OVERRIDE_CONTENT = '<target name="-do-test-run">\n    <junitlauncher/>\n</target>\n'


@pytest.fixture()  # type: ignore[untyped-decorator]
def project(tmp_path: Path) -> Path:
    (tmp_path / "nbproject").mkdir()
    (tmp_path / "build.xml").write_text(BUILD_XML_ORIGINAL)
    (tmp_path / "nbproject" / "project.properties").write_text(PROPS_ORIGINAL)
    return tmp_path


@pytest.fixture()  # type: ignore[untyped-decorator]
def props(project: Path) -> Path:
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

    def test_raises_when_props_missing(self, tmp_path: Path) -> None:
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
                '    <import file="nbproject/build-impl.xml"/>\n'
                f"    {MARKER_BEGIN}\n"
                f"    {MARKER_END}",
            )
        )
        assert is_junit5_configured(project) is True


class TestSetCompileOnSaveFalse:
    def test_changes_true_to_false(self, props: Path) -> None:
        set_compile_on_save_false(props)
        assert "compile.on.save=false" in props.read_text()

    def test_removes_true_value(self, props: Path) -> None:
        set_compile_on_save_false(props)
        assert "compile.on.save=true" not in props.read_text()

    def test_idempotent(self, props: Path) -> None:
        set_compile_on_save_false(props)
        set_compile_on_save_false(props)
        assert props.read_text().count("compile.on.save=false") == 1

    def test_leaves_other_properties_unchanged(self, props: Path) -> None:
        set_compile_on_save_false(props)
        content = props.read_text()
        assert "javac.classpath=" in content
        assert "javac.test.classpath=\\" in content

    def test_adds_property_when_absent(self, tmp_path: Path) -> None:
        props = tmp_path / "project.properties"
        props.write_text("javac.classpath=\n")
        set_compile_on_save_false(props)
        assert "compile.on.save=false" in props.read_text()


class TestAddFileReferences:
    def test_adds_reference_for_each_jar(self, props: Path) -> None:
        add_file_references(props, JAR_NAMES)
        content = props.read_text()
        assert (
            "file.reference.junit-jupiter-api-5.10.3.jar=lib/junit5/junit-jupiter-api-5.10.3.jar"
            in content
        )
        assert "file.reference.opentest4j-1.3.0.jar=lib/junit5/opentest4j-1.3.0.jar" in content

    def test_idempotent(self, props: Path) -> None:
        add_file_references(props, JAR_NAMES)
        add_file_references(props, JAR_NAMES)
        content = props.read_text()
        assert content.count("file.reference.junit-jupiter-api-5.10.3.jar") == 1

    def test_leaves_original_properties_intact(self, props: Path) -> None:
        add_file_references(props, JAR_NAMES)
        content = props.read_text()
        assert "compile.on.save=true" in content
        assert "javac.test.classpath=\\" in content


class TestModifyClasspath:
    def test_appends_jar_refs_to_javac_test_classpath(self, props: Path) -> None:
        modify_classpath(props, JAR_NAMES)
        content = props.read_text()
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" in content
        assert "${file.reference.opentest4j-1.3.0.jar}" in content

    def test_appends_jar_refs_to_run_test_classpath(self, props: Path) -> None:
        modify_classpath(props, JAR_NAMES)
        lines = props.read_text().splitlines()
        in_run_block = False
        found = False
        for line in lines:
            if line.startswith("run.test.classpath="):
                in_run_block = True
            if in_run_block and "file.reference.junit-jupiter-api-5.10.3.jar" in line:
                found = True
                break
            if (
                in_run_block
                and not line.endswith("\\")
                and not line.startswith("run.test.classpath")
            ):
                in_run_block = False
        assert found

    def test_last_jar_has_no_continuation(self, props: Path) -> None:
        modify_classpath(props, JAR_NAMES)
        lines = props.read_text().splitlines()
        last_jar_line = next(
            line for line in reversed(lines) if "file.reference.opentest4j" in line
        )
        assert not last_jar_line.rstrip().endswith("\\")

    def test_idempotent(self, props: Path) -> None:
        modify_classpath(props, JAR_NAMES)
        modify_classpath(props, JAR_NAMES)
        content = props.read_text()
        assert content.count("file.reference.junit-jupiter-api-5.10.3.jar") == 2


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


class TestRemoveFileReferences:
    def test_removes_junit5_references(self, props: Path) -> None:
        add_file_references(props, JAR_NAMES)
        remove_file_references(props)
        content = props.read_text()
        assert "file.reference.junit-jupiter-api-5.10.3.jar" not in content
        assert "file.reference.opentest4j-1.3.0.jar" not in content

    def test_leaves_other_references_intact(self, props: Path) -> None:
        props.write_text(
            PROPS_ORIGINAL
            + "file.reference.other-lib.jar=some/other/path/other-lib.jar\n"
            + "file.reference.junit-jupiter-api-5.10.3.jar"
            "=lib/junit5/junit-jupiter-api-5.10.3.jar\n"
        )
        remove_file_references(props)
        content = props.read_text()
        assert "file.reference.other-lib.jar" in content

    def test_noop_when_no_references(self, props: Path) -> None:
        original = props.read_text()
        remove_file_references(props)
        assert props.read_text() == original


class TestRevertClasspath:
    def test_removes_jar_refs_from_classpath(self, props: Path) -> None:
        modify_classpath(props, JAR_NAMES)
        revert_classpath(props)
        content = props.read_text()
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" not in content
        assert "${file.reference.opentest4j-1.3.0.jar}" not in content

    def test_restores_original_last_line_without_continuation(self, props: Path) -> None:
        modify_classpath(props, JAR_NAMES)
        revert_classpath(props)
        lines = props.read_text().splitlines()
        build_classes_line = next(line for line in lines if "${build.classes.dir}" in line)
        assert not build_classes_line.rstrip().endswith("\\")

    def test_noop_when_no_jar_refs(self, props: Path) -> None:
        original = props.read_text()
        revert_classpath(props)
        assert props.read_text() == original


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
        assert not any(JAR_NAMES[0] in url for url in called_urls)


class TestMain:
    def test_handles_invalid_project_gracefully(self, tmp_path: Path) -> None:
        with (
            patch("setup.Console") as mock_console_class,
            patch("setup.Panel"),
            patch("setup.Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = str(tmp_path)
            main()
        mock_console_class.return_value.print.assert_called()

    def test_calls_run_install_for_option_1(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.Prompt") as mock_prompt,
            patch("setup.run_install") as mock_install,
            patch("setup.is_junit5_configured", return_value=False),
        ):
            mock_prompt.ask.side_effect = [str(project), "1"]
            main()
        mock_install.assert_called_once_with(project)

    def test_calls_run_uninstall_for_option_2(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.Prompt") as mock_prompt,
            patch("setup.run_uninstall") as mock_uninstall,
            patch("setup.is_junit5_configured", return_value=True),
        ):
            mock_prompt.ask.side_effect = [str(project), "2"]
            main()
        mock_uninstall.assert_called_once_with(project)

    def test_quits_without_install_on_q(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.Prompt") as mock_prompt,
            patch("setup.run_install") as mock_install,
            patch("setup.is_junit5_configured", return_value=False),
        ):
            mock_prompt.ask.side_effect = [str(project), "q"]
            main()
        mock_install.assert_not_called()

    def test_quits_without_uninstall_on_q(self, project: Path) -> None:
        with (
            patch("setup.Console"),
            patch("setup.Panel"),
            patch("setup.Prompt") as mock_prompt,
            patch("setup.run_uninstall") as mock_uninstall,
            patch("setup.is_junit5_configured", return_value=True),
        ):
            mock_prompt.ask.side_effect = [str(project), "q"]
            main()
        mock_uninstall.assert_not_called()


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


class TestRunInstall:
    def test_raises_for_invalid_project(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            run_install(tmp_path)

    def test_sets_compile_on_save_false(self, project: Path) -> None:
        with patch("setup.fetch_jar_names", return_value=JAR_NAMES), patch("setup.download_jars"):
            run_install(project)
        assert "compile.on.save=false" in (project / "nbproject" / "project.properties").read_text()

    def test_adds_file_references(self, project: Path) -> None:
        with patch("setup.fetch_jar_names", return_value=JAR_NAMES), patch("setup.download_jars"):
            run_install(project)
        content = (project / "nbproject" / "project.properties").read_text()
        assert "file.reference.junit-jupiter-api-5.10.3.jar" in content

    def test_modifies_classpath(self, project: Path) -> None:
        with patch("setup.fetch_jar_names", return_value=JAR_NAMES), patch("setup.download_jars"):
            run_install(project)
        content = (project / "nbproject" / "project.properties").read_text()
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" in content

    def test_injects_build_xml(self, project: Path) -> None:
        with patch("setup.fetch_jar_names", return_value=JAR_NAMES), patch("setup.download_jars"):
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
        with patch("setup.fetch_jar_names", return_value=JAR_NAMES), patch("setup.download_jars"):
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
        props = project / "nbproject" / "project.properties"
        add_file_references(props, JAR_NAMES)
        run_uninstall(project)
        assert "file.reference.junit-jupiter-api-5.10.3.jar" not in props.read_text()

    def test_reverts_classpath(self, project: Path) -> None:
        props = project / "nbproject" / "project.properties"
        modify_classpath(props, JAR_NAMES)
        run_uninstall(project)
        assert "${file.reference.junit-jupiter-api-5.10.3.jar}" not in props.read_text()

    def test_removes_build_xml_markers(self, project: Path) -> None:
        inject_build_xml(project / "build.xml", OVERRIDE_CONTENT)
        run_uninstall(project)
        assert MARKER_BEGIN not in (project / "build.xml").read_text()

    def test_full_install_uninstall_cycle(self, project: Path) -> None:
        with patch("setup.fetch_jar_names", return_value=JAR_NAMES), patch("setup.download_jars"):
            run_install(project)
        run_uninstall(project)
        props = (project / "nbproject" / "project.properties").read_text()
        assert "file.reference.junit-jupiter-api-5.10.3.jar" not in props
        assert MARKER_BEGIN not in (project / "build.xml").read_text()
