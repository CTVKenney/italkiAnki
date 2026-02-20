from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import tarfile
from typing import List, Sequence, Tuple
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_NAME = "italki-anki"
DIST_NAME = "italki_anki"
PACKAGE_NAME = "italki_anki"
VERSION = "0.1.0"
SUMMARY = "CLI tool to convert Chinese lesson text into Anki CSVs"
REQUIRES_PYTHON = ">=3.10"
WHEEL_TAG = "py3-none-any"

ENTRY_POINTS = """[console_scripts]
italki-anki = italki_anki.cli:main
italki_anki = italki_anki.cli:main
"""


def _dist_info_dir() -> str:
    return f"{DIST_NAME}-{VERSION}.dist-info"


def _wheel_filename() -> str:
    return f"{DIST_NAME}-{VERSION}-{WHEEL_TAG}.whl"


def _sdist_filename() -> str:
    return f"{DIST_NAME}-{VERSION}.tar.gz"


def _metadata_bytes() -> bytes:
    return (
        "Metadata-Version: 2.1\n"
        f"Name: {PROJECT_NAME}\n"
        f"Version: {VERSION}\n"
        f"Summary: {SUMMARY}\n"
        f"Requires-Python: {REQUIRES_PYTHON}\n"
        "\n"
    ).encode("utf-8")


def _wheel_bytes() -> bytes:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: build_backend\n"
        "Root-Is-Purelib: true\n"
        f"Tag: {WHEEL_TAG}\n"
        "\n"
    ).encode("utf-8")


def _entry_points_bytes() -> bytes:
    return ENTRY_POINTS.encode("utf-8")


def _hash_entry(path: str, data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{path},sha256={encoded},{len(data)}"


def _dist_info_members() -> List[Tuple[str, bytes]]:
    dist_info = _dist_info_dir()
    return [
        (f"{dist_info}/METADATA", _metadata_bytes()),
        (f"{dist_info}/WHEEL", _wheel_bytes()),
        (f"{dist_info}/entry_points.txt", _entry_points_bytes()),
    ]


def _package_members() -> List[Tuple[str, bytes]]:
    package_root = PROJECT_ROOT / PACKAGE_NAME
    members: List[Tuple[str, bytes]] = []
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        members.append((relative, path.read_bytes()))
    return members


def _write_wheel(path: Path, members: Sequence[Tuple[str, bytes]]) -> None:
    dist_info = _dist_info_dir()
    record_entries: List[str] = []
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for relative_path, data in members:
            wheel.writestr(relative_path, data)
            record_entries.append(_hash_entry(relative_path, data))
        record_path = f"{dist_info}/RECORD"
        record_body = "\n".join([*record_entries, f"{record_path},,"]) + "\n"
        wheel.writestr(record_path, record_body.encode("utf-8"))


def _write_metadata_dir(metadata_directory: str) -> str:
    dist_info_name = _dist_info_dir()
    dist_info_path = Path(metadata_directory) / dist_info_name
    dist_info_path.mkdir(parents=True, exist_ok=True)
    (dist_info_path / "METADATA").write_bytes(_metadata_bytes())
    (dist_info_path / "WHEEL").write_bytes(_wheel_bytes())
    (dist_info_path / "entry_points.txt").write_bytes(_entry_points_bytes())
    return dist_info_name


def _supported_features() -> List[str]:
    return ["build_editable"]


def get_requires_for_build_wheel(config_settings=None) -> List[str]:
    return []


def get_requires_for_build_editable(config_settings=None) -> List[str]:
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None) -> str:
    return _write_metadata_dir(metadata_directory)


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None) -> str:
    return _write_metadata_dir(metadata_directory)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None) -> str:
    wheel_name = _wheel_filename()
    wheel_path = Path(wheel_directory) / wheel_name
    members = [*_package_members(), *_dist_info_members()]
    _write_wheel(wheel_path, members)
    return wheel_name


def build_editable(wheel_directory, config_settings=None, metadata_directory=None) -> str:
    wheel_name = _wheel_filename()
    wheel_path = Path(wheel_directory) / wheel_name
    members = [
        (f"{DIST_NAME}.pth", f"{PROJECT_ROOT}\n".encode("utf-8")),
        *_dist_info_members(),
    ]
    _write_wheel(wheel_path, members)
    return wheel_name


def build_sdist(sdist_directory, config_settings=None) -> str:
    sdist_name = _sdist_filename()
    sdist_path = Path(sdist_directory) / sdist_name
    root_prefix = f"{DIST_NAME}-{VERSION}"
    include_paths = [
        "build_backend.py",
        "pyproject.toml",
        PACKAGE_NAME,
    ]
    with tarfile.open(sdist_path, mode="w:gz", format=tarfile.PAX_FORMAT) as sdist:
        for relative_path in include_paths:
            source = PROJECT_ROOT / relative_path
            arcname = f"{root_prefix}/{relative_path}"
            sdist.add(source, arcname=arcname)
    return sdist_name
