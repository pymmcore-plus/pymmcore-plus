"""Test the install module functions."""

from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import pytest

from pymmcore_plus.install import MACH, PLATFORM, install

if TYPE_CHECKING:
    from pathlib import Path


def _create_test_zip(zip_path: Path) -> None:
    """Create a test zip file with some dummy content."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        # Add some dummy device adapter files
        zf.writestr("DCam.dll", "dummy content")
        zf.writestr("DStage.dll", "dummy content")
        zf.writestr("DWheel.dll", "dummy content")
        zf.writestr("libmmgr_dal_DCam.so", "dummy content")


def _mock_urlopen(url: str) -> Any:
    """Mock urlopen for GitHub API calls."""

    class MockResponse:
        def read(self) -> bytes:
            if "api.github.com" in url:
                # Mock GitHub API response
                releases_data = [
                    {"tag_name": "74.20250825"},
                    {"tag_name": "74.20250820"},
                    {"tag_name": "74.20250815"},
                    {"tag_name": "73.20250318"},
                    {"tag_name": "71.20221031"},
                ]
                return json.dumps(releases_data).encode()
            return b""

        def decode(self, encoding: str = "utf-8") -> str:
            return self.read().decode(encoding)

        def __enter__(self) -> MockResponse:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    return MockResponse()


def _mock_download_url(url: str, output_path: Path, show_progress: bool = True) -> None:
    """Mock download URL function that creates a test zip file."""
    _create_test_zip(output_path)


def _mock_subprocess_run(*args, **kwargs):
    """Mock subprocess.run to avoid actually running xattr."""
    return Mock(returncode=0)


def test_test_dev_install_basic(tmp_path: Path) -> None:
    """Test basic functionality of _test_dev_install."""
    dest = tmp_path / "test_install"

    # just to exercise the code path where apple silicon auto-downloads test adapters
    test_adapters = not (PLATFORM == "Darwin" and MACH == "arm64")
    with (
        patch("pymmcore_plus.install.urlopen", _mock_urlopen),
        patch("pymmcore_plus.install._download_url", _mock_download_url),
        patch("subprocess.run", _mock_subprocess_run),
    ):
        install(dest=dest, release="20250825", test_adapters=test_adapters)

    # Check that destination directory exists
    assert dest.exists()

    # Check that files were extracted (zip contains dummy device files)
    files = list(dest.rglob("*"))
    assert len(files) > 0


def test_test_dev_install_latest(tmp_path: Path) -> None:
    """Test _test_dev_install with 'latest' release."""
    dest = tmp_path / "test_install_latest"

    with (
        patch("pymmcore_plus.install.urlopen", _mock_urlopen),
        patch("pymmcore_plus.install._download_url", _mock_download_url),
        patch("subprocess.run", _mock_subprocess_run),
    ):
        install(dest=dest, release="latest", test_adapters=True)

    assert dest.exists()


def test_test_dev_install_latest_compatible(tmp_path: Path) -> None:
    """Test _test_dev_install with 'latest-compatible' release."""
    dest = tmp_path / "test_install_compatible"

    with (
        patch("pymmcore_plus.install.urlopen", _mock_urlopen),
        patch("pymmcore_plus.install._download_url", _mock_download_url),
        patch("subprocess.run", _mock_subprocess_run),
        patch("pymmcore_plus.install.PYMMCORE_DIV", 74),
    ):
        install(dest=dest, release="latest-compatible", test_adapters=True)

    assert dest.exists()


def test_test_dev_install_invalid_release(tmp_path: Path) -> None:
    """Test _test_dev_install with invalid release."""
    dest = tmp_path / "test_install_invalid"

    with (
        patch("pymmcore_plus.install.urlopen", _mock_urlopen),
        pytest.raises(ValueError, match="not found"),
    ):
        install(dest=dest, release="invalid_release", test_adapters=True)


def test_test_dev_install_no_compatible_releases(tmp_path: Path) -> None:
    """Test error when no compatible releases are found."""
    dest = tmp_path / "test_install_no_compat"

    def mock_empty_github_releases():
        """Mock GitHub API with no releases for old interface."""
        return {}

    with (
        patch("pymmcore_plus.install.urlopen", _mock_urlopen),
        patch("pymmcore_plus.install.PYMMCORE_DIV", 50),
        patch(
            "pymmcore_plus.install._available_test_adapter_releases",
            mock_empty_github_releases,
        ),
        pytest.raises(ValueError, match="No test device releases found"),
    ):
        install(dest=dest, release="latest-compatible", test_adapters=True)


def test_test_dev_install_creates_directory(tmp_path: Path) -> None:
    """Test that _test_dev_install creates the destination directory."""
    dest = tmp_path / "nested" / "test_install"

    # Ensure the directory doesn't exist initially
    assert not dest.exists()

    with (
        patch("pymmcore_plus.install.urlopen", _mock_urlopen),
        patch("pymmcore_plus.install._download_url", _mock_download_url),
        patch("subprocess.run", _mock_subprocess_run),
    ):
        install(dest=dest, release="20250825", test_adapters=True)

    # Check that the nested directory was created
    assert dest.exists()
