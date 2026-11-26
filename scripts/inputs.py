"""Download and verify pinned upstream source archives."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
FFMPEG_SOURCES = ("ffmpeg", "libwebp", "zlib", "lcms2", "dav1d")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(path, expected):
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path.name}: {actual} != {expected}")


def source_archive(name, cache, download=False):
    record = SOURCES[name]
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / record["file"]
    if not path.exists() and download:
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            fetched = Path(temporary) / record["file"]
            subprocess.run(
                ["curl", "--fail", "--location", "--silent", "--show-error",
                 "--proto", "=https", "--proto-redir", "=https", "--retry", "2",
                 "--max-time", "180", "--output", str(fetched), record["url"]],
                check=True,
            )
            require_hash(fetched, record["sha256"])
            fetched.replace(path)
    require_hash(path, record["sha256"])
    return path


def source_tree(name, cache, destination):
    archive = source_archive(name, cache, download=True)
    root = SOURCES[name]["directory"]
    target_root = destination / root
    if target_root.exists() or target_root.is_symlink():
        raise ValueError(f"Source destination already exists: {target_root}")
    with tarfile.open(archive, "r:*") as tar:
        names = set()
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != root or ".." in parts
                    or "\\" in member.name or ":" in member.name
                    or member.name.startswith("/") or parts in names or not (member.isdir() or member.isfile())):
                raise ValueError(f"Unexpected member in {archive.name}: {member.name}")
            names.add(parts)
        target_root.mkdir(parents=True, exist_ok=False)
        for member in tar.getmembers():
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, target.open("xb") as stream:
                    shutil.copyfileobj(source, stream)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
                os.utime(target, (member.mtime, member.mtime))
    return target_root


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("usage: inputs.py CACHE DESTINATION SOURCE ...")
    try:
        for source in sys.argv[3:]:
            source_tree(source, Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
