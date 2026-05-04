from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from setup import (
    _TEMPLATE_PATHS,
    _netbeans_base,
    are_templates_installed,
    download_and_apply_setup,
    find_netbeans_user_dir,
    is_setup_backup_present,
    rollback_setup,
    run_install_templates,
)


class TestNetbeansBase:
    def test_darwin_path(self) -> None:
        with patch("setup.sys") as mock_sys:
            mock_sys.platform = "darwin"
            result = _netbeans_base()
        assert result == Path.home() / "Library" / "Application Support" / "NetBeans"

    def test_win32_path_with_appdata(self) -> None:
        with patch("setup.sys") as mock_sys, patch("setup.os") as mock_os:
            mock_sys.platform = "win32"
            mock_os.environ.get.return_value = "C:\\AppData"
            result = _netbeans_base()
        assert result == Path("C:\\AppData") / "NetBeans"

    def test_win32_path_without_appdata(self) -> None:
        with patch("setup.sys") as mock_sys, patch("setup.os") as mock_os:
            mock_sys.platform = "win32"
            mock_os.environ.get.return_value = None
            result = _netbeans_base()
        assert result == Path.home() / "NetBeans"

    def test_linux_path(self) -> None:
        with patch("setup.sys") as mock_sys:
            mock_sys.platform = "linux"
            result = _netbeans_base()
        assert result == Path.home() / ".netbeans"


class TestFindNetbeansUserDir:
    def test_returns_none_when_dir_missing_or_empty(self, tmp_path: Path) -> None:
        assert find_netbeans_user_dir(tmp_path / "nonexistent") is None
        assert find_netbeans_user_dir(tmp_path) is None

    def test_returns_single_version_dir(self, tmp_path: Path) -> None:
        (tmp_path / "22").mkdir()
        assert find_netbeans_user_dir(tmp_path) == tmp_path / "22"

    def test_returns_highest_version(self, tmp_path: Path) -> None:
        for version in ["21", "22", "23"]:
            (tmp_path / version).mkdir()
        assert find_netbeans_user_dir(tmp_path) == tmp_path / "23"

    def test_uses_platform_default_when_no_base(self, tmp_path: Path) -> None:
        (tmp_path / "22").mkdir()
        with patch("setup._netbeans_base", return_value=tmp_path):
            result = find_netbeans_user_dir()
        assert result == tmp_path / "22"


class TestAreTemplatesInstalled:
    def test_false_when_templates_absent_or_partial(self, tmp_path: Path) -> None:
        assert are_templates_installed(tmp_path) is False
        classes_dir = tmp_path / "config" / "Templates" / "Classes"
        classes_dir.mkdir(parents=True)
        (classes_dir / "Class.java").write_text("x")
        assert are_templates_installed(tmp_path) is False

    def test_true_when_all_templates_present(self, tmp_path: Path) -> None:
        for relative_path in _TEMPLATE_PATHS:
            target = tmp_path / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x")
        assert are_templates_installed(tmp_path) is True


class TestDownloadAndApplySetup:
    @patch("requests.get")
    def test_extracts_allowed_and_skips_excluded(self, mock_get: MagicMock, tmp_path: Path) -> None:
        existing = tmp_path / "config/Templates/Classes/Class.java"
        existing.parent.mkdir(parents=True)
        existing.write_text("original")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("config/Templates/Classes/Class.java", "new")
            archive.writestr("config/Editors/text/x-java/Preferences/foo.xml", "<p/>")
            archive.writestr("config/Preferences/org/apache/tools/ant/module.properties", "v=2")
            archive.writestr("config/Preferences/org/netbeans/modules/autoupdate.properties", "x")
            archive.writestr("config/Editors/.DS_Store", "mac")
        mock_get.return_value.content = buffer.getvalue()
        mock_get.return_value.raise_for_status = MagicMock()
        download_and_apply_setup(tmp_path)
        assert existing.read_text() == "original"
        assert (tmp_path / "config/Editors/text/x-java/Preferences/foo.xml").is_file()
        assert (tmp_path / "config/Preferences/org/apache/tools/ant/module.properties").is_file()
        autoupdate_path = tmp_path / "config/Preferences/org/netbeans/modules/autoupdate.properties"
        assert not autoupdate_path.is_file()
        assert not (tmp_path / "config/Editors/.DS_Store").is_file()

    @patch("requests.get")
    def test_laf_platform_guard(self, mock_get: MagicMock, tmp_path: Path) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("config/Preferences/laf.properties", "laf=x")
        mock_get.return_value.content = buffer.getvalue()
        mock_get.return_value.raise_for_status = MagicMock()
        with patch("setup.sys") as mock_sys:
            mock_sys.platform = "darwin"
            download_and_apply_setup(tmp_path)
        assert (tmp_path / "config/Preferences/laf.properties").is_file()
        with patch("setup.sys") as mock_sys:
            mock_sys.platform = "linux"
            download_and_apply_setup(tmp_path / "second")
        assert not (tmp_path / "second" / "config/Preferences/laf.properties").is_file()

    @patch("requests.get")
    def test_creates_backup_record_for_new_files(self, mock_get: MagicMock, tmp_path: Path) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("config/Templates/Classes/Class.java", "t")
        mock_get.return_value.content = buffer.getvalue()
        mock_get.return_value.raise_for_status = MagicMock()
        download_and_apply_setup(tmp_path)
        assert is_setup_backup_present(tmp_path)
        record = tmp_path / "cct-setup-backup" / "new-files.txt"
        assert "config/Templates/Classes/Class.java" in record.read_text()

    @patch("requests.get")
    def test_no_backup_when_all_files_exist(self, mock_get: MagicMock, tmp_path: Path) -> None:
        existing = tmp_path / "config/Templates/Classes/Class.java"
        existing.parent.mkdir(parents=True)
        existing.write_text("original")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("config/Templates/Classes/Class.java", "new")
        mock_get.return_value.content = buffer.getvalue()
        mock_get.return_value.raise_for_status = MagicMock()
        download_and_apply_setup(tmp_path)
        assert not is_setup_backup_present(tmp_path)


class TestIsSetupBackupPresent:
    def test_false_when_no_backup(self, tmp_path: Path) -> None:
        assert is_setup_backup_present(tmp_path) is False

    def test_true_when_record_exists(self, tmp_path: Path) -> None:
        record = tmp_path / "cct-setup-backup" / "new-files.txt"
        record.parent.mkdir()
        record.write_text("config/Templates/Classes/Class.java\n")
        assert is_setup_backup_present(tmp_path) is True


class TestRollbackSetup:
    def test_deletes_new_files_and_backup_dir(self, tmp_path: Path) -> None:
        backup = tmp_path / "cct-setup-backup"
        backup.mkdir()
        target = tmp_path / "config/Templates/Classes/Class.java"
        target.parent.mkdir(parents=True)
        target.write_text("installed")
        (backup / "new-files.txt").write_text("config/Templates/Classes/Class.java\n")
        rollback_setup(tmp_path)
        assert not target.is_file()
        assert not backup.exists()

    def test_noop_when_no_record(self, tmp_path: Path) -> None:
        rollback_setup(tmp_path)

    def test_skips_missing_file_in_record(self, tmp_path: Path) -> None:
        backup = tmp_path / "cct-setup-backup"
        backup.mkdir()
        (backup / "new-files.txt").write_text("does-not-exist.txt\n")
        rollback_setup(tmp_path)
        assert not backup.exists()


class TestRunInstallTemplates:
    def test_calls_download_and_apply_setup(self, tmp_path: Path) -> None:
        with patch("setup.download_and_apply_setup") as mock_download:
            run_install_templates(tmp_path)
        mock_download.assert_called_once_with(tmp_path)
