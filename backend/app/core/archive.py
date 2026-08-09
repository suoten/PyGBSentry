from __future__ import annotations

from pathlib import Path
import tarfile
import zipfile


class UnsafeArchiveError(ValueError):
    pass


def _ensure_within_base(base: Path, dest: Path) -> None:
    base = base.resolve()
    dest = dest.resolve()
    if dest == base:
        return
    if base not in dest.parents:
        raise UnsafeArchiveError(f"Archive entry escapes target dir: {dest}")


def safe_extract_zip(
    zip_ref: zipfile.ZipFile,
    target_dir: str | Path,
    *,
    max_files: int = 5000,
    max_total_size: int = 1024 * 1024 * 512,
) -> None:
    base = Path(target_dir)
    base.mkdir(parents=True, exist_ok=True)

    infos = zip_ref.infolist()
    if len(infos) > max_files:
        raise UnsafeArchiveError("Too many files in zip")

    total = 0
    for info in infos:
        # Normalize directory entries
        name = info.filename
        if not name or name.endswith("/"):
            continue

        total += int(getattr(info, "file_size", 0) or 0)
        if total > max_total_size:
            raise UnsafeArchiveError("Zip uncompressed size too large")

        dest = base / name
        _ensure_within_base(base, dest)
        zip_ref.extract(info, base)


def safe_extract_tar(
    tar_ref: tarfile.TarFile,
    target_dir: str | Path,
    *,
    max_files: int = 5000,
    max_total_size: int = 1024 * 1024 * 512,
) -> None:
    base = Path(target_dir)
    base.mkdir(parents=True, exist_ok=True)

    members = tar_ref.getmembers()
    if len(members) > max_files:
        raise UnsafeArchiveError("Too many files in tar")

    total = 0
    for m in members:
        name = m.name
        if not name:
            continue
        if m.issym() or m.islnk():
            raise UnsafeArchiveError("Tar contains symlink/hardlink entries")
        if m.isdir():
            continue
        total += int(getattr(m, "size", 0) or 0)
        if total > max_total_size:
            raise UnsafeArchiveError("Tar uncompressed size too large")

        dest = base / name
        _ensure_within_base(base, dest)
        tar_ref.extract(m, base)

