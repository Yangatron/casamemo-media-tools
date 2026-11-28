"""Make versioned candidates and verify their archive and provisioning contracts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from inputs import FFMPEG_SOURCES, ROOT, SOURCES, require_hash, sha256, source_archive
from windows_exiftool import (
    NOTICE_FILES, PERL_DLLS, RUNTIME_BUILD, RUNTIME_DIR, WIN32_FILE_DATA,
    WINLIBS_BASE_SOURCES, XS_SOURCES,
)
from windows_runtime import SOURCE_PACKAGES

PLATFORMS = ("macos-arm64", "macos-x64", "windows-x64")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
FFMPEG_VERSION = SOURCES["ffmpeg"]["version"]
EXIFTOOL_VERSION = SOURCES["exiftool"]["version"]
SCHEMA_VERSION = 1
RECIPE_PATHS = (
    ".gitattributes", ".github/workflows/build.yml", ".gitignore", "AGENTS.md",
    "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "docs/RELEASING.md",
    "docs/SECURITY.md", "licenses/ExifTool-Artistic.txt", "sources.json",
    "patches/ffmpeg-9.1-raw-zero-seek.patch",
    "scripts/artifacts.py", "scripts/build.sh", "scripts/inputs.py", "scripts/macos-build-tools.txt",
    "scripts/windows-brotli-Makefile.PL", "scripts/windows-exiftool-launcher.c",
    "scripts/windows-exiftool-launcher.manifest", "scripts/windows-exiftool-launcher.rc",
    "scripts/windows_exiftool.py", "scripts/windows_runtime.py",
    "tests/runtime.py", "tests/test_artifacts.py", "tests/fixtures/README.md",
    "tests/fixtures/local-video.mp4", "tests/fixtures/still.avif",
    "tests/fixtures/still.heic", "tests/fixtures/tiled.heic",
    "tests/fixtures/video.h264", "tests/fixtures/video.hevc", "tests/fixtures/pq.heic",
    "tests/fixtures/profiled.heic",
)
BUILD_RECORDS = ("config.h", "config_components.h", "toolchain.txt")
WINDOWS_NOTICES = (
    "COPYING.RUNTIME", "COPYING3", "COPYING.MinGW-w64-runtime.txt", "COPYING.winpthreads",
)
WINDOWS_COMPANION_SOURCES = (*dict.fromkeys(SOURCE_PACKAGES.values()), "perl-core",
                             "strawberry-build", "perl-win32-api", *WINLIBS_BASE_SOURCES)
EXIFTOOL_RECORDS = NOTICE_FILES | {RUNTIME_BUILD}
EXIFTOOL_REQUIRED = {"exiftool.exe", *(f"{RUNTIME_DIR}/{name}" for name in PERL_DLLS),
                     f"{RUNTIME_DIR}/exiftool.pl", f"{RUNTIME_DIR}/lib/Image/ExifTool.pm",
                     f"{RUNTIME_DIR}/lib/Image/ExifTool/Geolocation.dat",
                     f"{RUNTIME_DIR}/lib/File/RandomAccess.pm",
                     f"{RUNTIME_DIR}/lib/{WIN32_FILE_DATA}",
                     f"{RUNTIME_DIR}/lib/auto/Compress/Raw/Zlib/Zlib.xs.dll",
                     f"{RUNTIME_DIR}/lib/auto/IO/Compress/Brotli/Brotli.xs.dll",
                     f"{RUNTIME_DIR}/lib/auto/Win32/FindFile/FindFile.xs.dll"} | NOTICE_FILES


def write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def archive_zip(path, members):
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, source, mode in sorted(members):
            info = zipfile.ZipInfo(name, ZIP_DATE)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with source.open("rb") as reader, archive.open(info, "w") as writer:
                shutil.copyfileobj(reader, writer)


def layout(platform, revision):
    ffmpeg = f"casamemo-ffmpeg-{FFMPEG_VERSION}-{platform}-{revision}.zip"
    source = f"casamemo-sources-{platform}-{revision}.zip"
    ffprobe = None
    exiftool_format = "zip"
    if platform.startswith("macos-"):
        ffprobe = f"casamemo-ffprobe-{FFMPEG_VERSION}-{platform}-{revision}.zip"
        exiftool_format = "tar.gz"
    exiftool = f"casamemo-exiftool-{EXIFTOOL_VERSION}-{platform}-{revision}.{exiftool_format}"
    return ffmpeg, ffprobe, exiftool, source


def source_inputs(platform):
    dependencies = (*FFMPEG_SOURCES, "exiftool")
    if platform == "windows-x64":
        return (*dependencies, *XS_SOURCES, *WINDOWS_COMPANION_SOURCES)
    return dependencies


def regular_file(root, relative):
    path = root
    parts = Path(relative).parts
    for part in parts:
        path = path / part
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Unsafe archive input: {relative}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Expected a regular archive input: {relative}")
    return path


def notice_names():
    return {"licenses/THIRD_PARTY_NOTICES.md"} | {
        f"licenses/{name}/{filename}"
        for name in FFMPEG_SOURCES for filename in SOURCES[name]["notices"]
    }


def notices(work):
    result = []
    for name in FFMPEG_SOURCES:
        record = SOURCES[name]
        for filename in record["notices"]:
            path = regular_file(work, f"source/{record['directory']}/{filename}")
            result.append((f"licenses/{name}/{filename}", path, 0o644))
    result.append(("licenses/THIRD_PARTY_NOTICES.md",
                   regular_file(ROOT, "THIRD_PARTY_NOTICES.md"), 0o644))
    return result


def recipe_files():
    # Source companions can be rebuilt outside a Git checkout. In a checkout,
    # fail closed if a required input is ignored by repository or local rules.
    if (ROOT / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", "-z", "--stdin"], cwd=ROOT,
                input=("\0".join(RECIPE_PATHS) + "\0").encode(), stdout=subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise ValueError("Git executable not found on PATH. The source archive inventory requires Git.") from error
        if result.returncode == 0:
            raise ValueError("An approved recipe path is ignored by Git")
        if result.returncode != 1:
            result.check_returncode()
    return [(f"recipe/{name}", regular_file(ROOT, name), 0o755 if name.endswith(".sh") else 0o644)
            for name in RECIPE_PATHS]


def binary_names(platform):
    suffix = ".exe" if platform == "windows-x64" else ""
    return [f"ffmpeg{suffix}", f"ffprobe{suffix}"]


def build_record_names(platform):
    names = {f"build/{name}" for name in BUILD_RECORDS}
    if platform == "windows-x64":
        names.update(f"build/windows-notices/{name}" for name in WINDOWS_NOTICES)
        names.add("build/windows-static-linkage.txt")
    return names


def build_record(work, platform):
    return [(name, regular_file(work, f"metadata/{name[6:]}"), 0o644)
            for name in sorted(build_record_names(platform))]


def require_inventory(archive, expected):
    actual = set(archive.namelist())
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"Missing required archive member: {', '.join(missing)}")
    if actual - expected:
        raise ValueError(f"Unexpected archive member: {', '.join(sorted(actual - expected))}")
    for item in archive.infolist():
        if not item.file_size:
            raise ValueError(f"Empty required archive member: {item.filename}")


def validate_config(text, components):
    for flag in ("GPL", "NONFREE", "VERSION3", "NETWORK", "AVDEVICE"):
        if not re.search(rf"^#define CONFIG_{flag} 0$", text, re.MULTILINE):
            raise ValueError(f"Expected CONFIG_{flag}=0")
    for flag in ("LCMS2", "LIBWEBP", "LIBDAV1D", "ZLIB"):
        if not re.search(rf"^#define CONFIG_{flag} 1$", text, re.MULTILINE):
            raise ValueError(f"Expected CONFIG_{flag}=1")
    for component in (
        "IMAGE_JPEG_PIPE_DEMUXER", "IMAGE_PNG_PIPE_DEMUXER", "IMAGE_TIFF_PIPE_DEMUXER",
        "WEBP_ANIM_DECODER", "WEBP_ANIM_DEMUXER", "LIBWEBP_ANIM_ENCODER", "HEVC_DECODER",
        "H264_DECODER", "H264_DEMUXER", "HEVC_DEMUXER", "TIFF_DECODER",
        "LIBDAV1D_DECODER", "PNG_ENCODER", "MOV_DEMUXER",
        "ICCGEN_FILTER", "ICCDETECT_FILTER", "XSTACK_FILTER", "COLORSPACE_FILTER",
    ):
        if not re.search(rf"^#define CONFIG_{component} 1$", components, re.MULTILINE):
            raise ValueError(f"Expected CONFIG_{component}=1")
    protocols = re.findall(r"^#define CONFIG_(\w+)_PROTOCOL 1$", components, re.MULTILINE)
    if set(protocols) != {"FILE", "PIPE"}:
        raise ValueError(f"Unexpected FFmpeg protocols: {protocols}")


def windows_exiftool_members(work):
    record_path = regular_file(work, f"exiftool/{RUNTIME_BUILD}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    entries = record["members"]
    validate_exiftool_inventory(entries)
    members = [(RUNTIME_BUILD, record_path, 0o644)]
    for name, checksum in entries.items():
        path = regular_file(work, f"exiftool/{name}")
        require_hash(path, checksum)
        if name.endswith((".exe", ".dll")):
            require_public_binary(path, work)
        members.append((name, path, 0o755 if name == "exiftool.exe" else 0o644))
    return members


def validate_exiftool_inventory(entries):
    if not isinstance(entries, dict) or not EXIFTOOL_REQUIRED <= entries.keys():
        raise ValueError("Windows ExifTool runtime inventory is incomplete")
    for name, digest in entries.items():
        if (name not in EXIFTOOL_REQUIRED
                and not re.fullmatch(rf"{RUNTIME_DIR}/lib/(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+\.(?:pm|pl|al|ix|dll|enc)", name)):
            raise ValueError(f"Unexpected Windows ExifTool member: {name}")
        if any(part.endswith(".") for part in name.split("/")):
            raise ValueError(f"Unsafe Windows ExifTool member: {name}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid Windows ExifTool member hash: {name}")


def require_public_binary(binary, work):
    contents = binary.read_bytes()
    for path in (ROOT, work, Path.home()):
        for value in {str(path), path.as_posix()}:
            if len(value) > 3 and (value.encode("utf-8") in contents
                                  or value.encode("utf-16le") in contents):
                raise ValueError(f"A local build path is embedded in {binary.name}")


def package(platform, cache, work, destination, revision):
    if destination.exists():
        raise ValueError(f"Output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_name, ffprobe_name, exiftool_name, source_name = layout(platform, revision)
    windows = platform == "windows-x64"
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary) / "candidate"
        staging.mkdir()
        evidence = build_record(work, platform)
        validate_config((work / "metadata/config.h").read_text(),
                        (work / "metadata/config_components.h").read_text())
        runtime = []
        for executable in binary_names(platform):
            binary = regular_file(work, f"ffmpeg/{executable}")
            require_public_binary(binary, work)
            runtime.append((f"bin/{executable}", binary, 0o755))
        inventory = notices(work)
        archive_zip(staging / ffmpeg_name, (runtime[:1] if ffprobe_name else runtime) + inventory + evidence)
        if ffprobe_name:
            archive_zip(staging / ffprobe_name, runtime[1:] + inventory + evidence)
        if windows:
            exif_members = windows_exiftool_members(work)
            archive_zip(staging / exiftool_name, exif_members)
            evidence += [member for member in exif_members
                         if member[0] in EXIFTOOL_RECORDS - notice_names()]
        else:
            shutil.copyfile(source_archive("exiftool", cache, download=True), staging / exiftool_name)
        inputs = [(f"upstream/{SOURCES[name]['file']}",
                   source_archive(name, cache, download=name in WINDOWS_COMPANION_SOURCES), 0o644)
                  for name in source_inputs(platform)]
        archive_zip(staging / source_name, inputs + inventory + evidence + recipe_files())
        index(staging, platform, revision, state="ci-candidate")
        verify(staging)
        staging.rename(destination)


def package_specs(platform, revision):
    ffmpeg, ffprobe, exiftool, source = layout(platform, revision)
    roles = [(ffmpeg, "ffmpeg" if ffprobe else "ffmpeg-ffprobe", "zip")]
    if ffprobe:
        roles.append((ffprobe, "ffprobe", "zip"))
    roles.append((exiftool, "exiftool", "zip" if platform == "windows-x64" else "tar.gz"))
    return roles + [(source, "source", "zip")]


def provisioning(platform, revision):
    ffmpeg, ffprobe, exiftool, _ = layout(platform, revision)
    return {
        "ffmpeg": {"asset": ffmpeg, "version": FFMPEG_VERSION, "checksumTarget": "archive"},
        "ffprobe": ({"asset": ffprobe, "version": FFMPEG_VERSION, "checksumTarget": "archive"}
                    if ffprobe else None),
        "exiftool": {"asset": exiftool, "version": EXIFTOOL_VERSION, "checksumTarget": "archive"},
    }


def index(directory, platform, revision, state):
    if platform == "windows-x64" and state == "owner-finalized":
        raise ValueError("Windows runtime redistribution review is still open")
    dependencies = source_inputs(platform)
    packages = []
    for name, role, archive_format in package_specs(platform, revision):
        path = directory / name
        packages.append({"filename": name, "role": role, "format": archive_format,
                         "sha256": sha256(path), "sizeBytes": path.stat().st_size})
    data = {
        "schemaVersion": SCHEMA_VERSION,
        "platform": platform,
        "revision": revision,
        "state": state,
        "sources": {name: SOURCES[name] for name in dependencies},
        "artifacts": packages,
        "provisioning": provisioning(platform, revision),
    }
    if platform == "windows-x64":
        data["buildInputs"] = {"strawberry-perl": SOURCES["strawberry-perl"]}
    write_json(directory / "artifacts.json", data)
    (directory / "SHA256SUMS").write_bytes(checksum_text(packages))


def checksum_text(packages):
    return "".join(f"{item['sha256']}  {item['filename']}\n" for item in packages).encode("ascii")


def verify_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = set()
        for item in archive.infolist():
            name = item.filename
            if (not re.fullmatch(r"[A-Za-z0-9_.()/+-]+", name)
                    or set(name.split("/")) & {"", ".", ".."} or name.casefold() in names
                    or stat.S_IFMT(item.external_attr >> 16) != stat.S_IFREG):
                raise ValueError(f"Unsafe ZIP member: {name}")
            names.add(name.casefold())
        for name in names:
            parts = name.split("/")
            if any("/".join(parts[:length]) in names for length in range(1, len(parts))):
                raise ValueError(f"ZIP file used as a directory: {name}")
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt ZIP member: {bad}")


def verify_windows_exiftool(path, sources):
    verify_zip(path)
    with zipfile.ZipFile(path) as archive:
        record = json.loads(archive.read(RUNTIME_BUILD))
        entries = record["members"]
        validate_exiftool_inventory(entries)
        require_inventory(archive, {RUNTIME_BUILD, *entries})
        if archive.getinfo("exiftool.exe").external_attr >> 16 & 0o755 != 0o755:
            raise ValueError("Missing executable permissions for exiftool.exe")
        if record["perlAbi"] != "5.42.3|MSWin32-x64-multi-thread|13.2.0|xs.dll" or (
                record["perlZlib"] != SOURCES["zlib"]["version"]):
            raise ValueError("Unexpected Windows ExifTool runtime versions")
        if set(record["peImports"]) != {name for name in entries if name.endswith((".exe", ".dll"))}:
            raise ValueError("Windows ExifTool PE record does not cover its complete binary inventory")
        objects = record["winlibsLinkedObjects"]
        if set(objects) != {"brotli", "findfile", "launcher", "zlib"} or not all(objects.values()):
            raise ValueError("Windows ExifTool static link record is incomplete")
        for name, expected in entries.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Windows ExifTool member mismatch: {name}")
        for name in sorted(EXIFTOOL_RECORDS):
            if archive.read(name) != sources.read(name):
                raise ValueError(f"Windows ExifTool and source records differ: {name}")


def verify(directory):
    data = json.loads((directory / "artifacts.json").read_text(encoding="utf-8"))
    platform, revision = data["platform"], data["revision"]
    if (data["schemaVersion"] != SCHEMA_VERSION or platform not in PLATFORMS
            or not re.fullmatch(r"r[1-9][0-9]*", revision)
            or data["state"] not in {"ci-candidate", "owner-finalized"}):
        raise ValueError("Invalid artifact metadata")
    if platform == "windows-x64" and data["state"] == "owner-finalized":
        raise ValueError("Windows runtime redistribution review is still open")
    ffmpeg, ffprobe, exiftool, source = layout(platform, revision)
    packages = data["artifacts"]
    records = [(item["filename"], item["role"], item["format"]) for item in packages]
    if package_specs(platform, revision) != records:
        raise ValueError("Unexpected artifact names, roles or formats")
    windows = platform == "windows-x64"
    dependencies = source_inputs(platform)
    if data["sources"] != {name: SOURCES[name] for name in dependencies}:
        raise ValueError("Artifact metadata does not match the source lock")
    if windows and data.get("buildInputs") != {"strawberry-perl": SOURCES["strawberry-perl"]}:
        raise ValueError("Artifact metadata does not match the Windows build input lock")
    if data["provisioning"] != provisioning(platform, revision):
        raise ValueError("Unexpected provisioning layout")
    if (directory / "SHA256SUMS").read_bytes() != checksum_text(packages):
        raise ValueError("SHA256SUMS does not match the artifact index")
    for item in packages:
        path = directory / item["filename"]
        require_hash(path, item["sha256"])
        if path.stat().st_size != item["sizeBytes"]:
            raise ValueError(f"Size mismatch: {path.name}")
    verify_zip(directory / source)
    names = binary_names(platform)
    runtime = [(ffmpeg, names[:1] if ffprobe else names)]
    if ffprobe:
        runtime.append((ffprobe, names[1:]))
    records = notice_names() | build_record_names(platform)
    upstream = {f"upstream/{SOURCES[name]['file']}" for name in dependencies}
    recipe = {f"recipe/{name}" for name in RECIPE_PATHS}
    with zipfile.ZipFile(directory / source) as source_archive_zip:
        source_records = records | EXIFTOOL_RECORDS if windows else records
        require_inventory(source_archive_zip, source_records | upstream | recipe)
        for filename, expected in runtime:
            path = directory / filename
            verify_zip(path)
            with zipfile.ZipFile(path) as archive:
                bins = {f"bin/{name}" for name in expected}
                require_inventory(archive, records | bins)
                for name in bins:
                    if archive.getinfo(name).external_attr >> 16 & 0o755 != 0o755:
                        raise ValueError(f"Missing executable permissions for {name}")
                validate_config(archive.read("build/config.h").decode(),
                                archive.read("build/config_components.h").decode())
                for key in sorted(records):
                    if archive.read(key) != source_archive_zip.read(key):
                        raise ValueError(f"Runtime and source records differ: {key}")
        for name in dependencies:
            item = SOURCES[name]
            with source_archive_zip.open(f"upstream/{item['file']}") as stream:
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                if digest.hexdigest() != item["sha256"]:
                    raise ValueError(f"Corresponding source mismatch: {name}")
        if windows:
            verify_windows_exiftool(directory / exiftool, source_archive_zip)
    if not windows:
        record = SOURCES["exiftool"]
        require_hash(directory / exiftool, record["sha256"])
        name = record["directory"]
        with tarfile.open(directory / exiftool, "r:gz") as archive:
            for required in ("exiftool", "lib/Image/ExifTool.pm", *record["notices"]):
                if not archive.getmember(f"{name}/{required}").isfile():
                    raise ValueError(f"ExifTool layout is incomplete: {required}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    prepare = sub.add_parser("package")
    prepare.add_argument("platform", choices=PLATFORMS)
    for arg in ("cache", "work", "destination"):
        prepare.add_argument(arg, type=Path)
    prepare.add_argument("--revision", default="r1")
    check = sub.add_parser("verify")
    check.add_argument("directory", type=Path)
    finalize = sub.add_parser("finalize-index")
    finalize.add_argument("platform", choices=PLATFORMS)
    finalize.add_argument("directory", type=Path)
    finalize.add_argument("--revision", required=True)
    arguments = parser.parse_args()
    if hasattr(arguments, "revision") and not re.fullmatch(r"r[1-9][0-9]*", arguments.revision):
        parser.error("Revision must be r followed by a positive integer")
    try:
        if arguments.operation == "package":
            package(arguments.platform, arguments.cache, arguments.work,
                    arguments.destination, arguments.revision)
        elif arguments.operation == "verify":
            verify(arguments.directory)
        else:
            index(arguments.directory, arguments.platform, arguments.revision, "owner-finalized")
            verify(arguments.directory)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, tarfile.TarError,
            subprocess.CalledProcessError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
