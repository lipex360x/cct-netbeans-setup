from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from setup import download_template_zip


class TestDownloadTemplateZip:
    @patch("requests.get")
    def test_downloads_and_saves_zip(self, mock_get: MagicMock, tmp_path: Path) -> None:
        mock_get.return_value.content = b"zip-bytes"
        mock_get.return_value.raise_for_status = MagicMock()
        result = download_template_zip(tmp_path)
        assert result == tmp_path / "Template.zip"
        assert (tmp_path / "Template.zip").read_bytes() == b"zip-bytes"

    @patch("requests.get")
    def test_creates_destination_if_missing(self, mock_get: MagicMock, tmp_path: Path) -> None:
        destination = tmp_path / "subdir"
        mock_get.return_value.content = b"zip-bytes"
        mock_get.return_value.raise_for_status = MagicMock()
        download_template_zip(destination)
        assert (destination / "Template.zip").is_file()

    @patch("requests.get")
    def test_overwrites_existing_zip(self, mock_get: MagicMock, tmp_path: Path) -> None:
        (tmp_path / "Template.zip").write_bytes(b"old-bytes")
        mock_get.return_value.content = b"new-bytes"
        mock_get.return_value.raise_for_status = MagicMock()
        download_template_zip(tmp_path)
        assert (tmp_path / "Template.zip").read_bytes() == b"new-bytes"

    @patch("requests.get")
    def test_returns_path_to_zip(self, mock_get: MagicMock, tmp_path: Path) -> None:
        mock_get.return_value.content = b"zip-bytes"
        mock_get.return_value.raise_for_status = MagicMock()
        result = download_template_zip(tmp_path)
        assert isinstance(result, Path)
        assert result.name == "Template.zip"
