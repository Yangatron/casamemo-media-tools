"""Validate candidate native binaries and exercise CasaMemo media operations."""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from zipfile import ZipFile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from artifacts import EXIFTOOL_VERSION, FFMPEG_VERSION, binary_names, layout, verify
from inputs import SOURCES, sha256, source_tree

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SIZE = (32, 24)
WINDOWS_SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "kernel32.dll", "msvcrt.dll", "ntdll.dll",
    "ole32.dll", "oleaut32.dll", "psapi.dll", "shell32.dll", "ucrtbase.dll",
    "user32.dll", "version.dll",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(*arguments, cwd=None):
    result = subprocess.run([str(value) for value in arguments], stderr=subprocess.PIPE,
                            stdout=subprocess.PIPE, timeout=60, cwd=cwd)
    if result.returncode:
        raise RuntimeError(f"{arguments[0]} failed ({result.returncode}): "
                           + result.stderr.decode(errors="replace"))
    return result.stdout


def verify_architecture(binaries, platform):
    for binary in binaries:
        if platform.startswith("macos-"):
            expected = "arm64" if platform == "macos-arm64" else "x86_64"
            require(command("lipo", "-archs", binary).decode().strip() == expected,
                    f"Incorrect Mach-O architecture for {binary.name}")
            version = command("vtool", "-show-build", binary).decode()
            require(re.search(r"^\s*minos 13\.0(?:\.0)?$", version, re.MULTILINE),
                    f"Incorrect macOS deployment target for {binary.name}")
            dependencies = [line.strip().rsplit(" (", 1)[0]
                            for line in command("otool", "-L", binary).decode().splitlines()[1:]]
            require(dependencies and all(link.startswith(("/usr/lib/", "/System/Library/"))
                                         for link in dependencies),
                    f"Non-system linkage for {binary.name}: {dependencies}")
            require(not any(Path(link).name.startswith(("libav", "libsw", "libz.", "liblcms",
                                                        "libwebp", "libdav1d", "libsharpyuv"))
                            for link in dependencies),
                    f"A pinned media library was linked dynamically in {binary.name}: {dependencies}")
        else:
            require("pei-x86-64" in command("objdump", "-f", binary).decode(),
                    f"Incorrect Windows PE architecture for {binary.name}")
            details = command("objdump", "-p", binary).decode(errors="replace")
            dependencies = re.findall(r"DLL Name:\s*(\S+)", details, re.IGNORECASE)
            unexpected = [item for item in dependencies if item.lower() not in WINDOWS_SYSTEM_DLLS
                          and not item.lower().startswith("api-ms-win-crt-")]
            require(dependencies and not unexpected, f"Non-system imports for {binary.name}: {unexpected}")
        print(f"{binary.name} architecture and linkage verified")


def png_chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data)))


def write_png(output, pixel):
    width, height = SIZE
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = (b"\0" + pixel * width) * height
    output.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
                       + png_chunk(b"IDAT", zlib.compress(rows)) + png_chunk(b"IEND", b""))


def write_tiff(output):
    width, height = SIZE
    pixels = bytes((210, 100, 24)) * (width * height)
    compressed = zlib.compress(pixels)
    offset = 8 + 2 + 10 * 12 + 4
    tags = (
        (256, 4, 1, width), (257, 4, 1, height), (258, 3, 3, offset), (259, 3, 1, 8),
        (262, 3, 1, 2), (273, 4, 1, offset + 6), (277, 3, 1, 3), (278, 4, 1, height),
        (279, 4, 1, len(compressed)), (284, 3, 1, 1),
    )
    entries = b"".join(struct.pack("<HHII", *tag) for tag in tags)
    output.write_bytes(b"II" + struct.pack("<HIH", 42, 8, len(tags)) + entries
                       + struct.pack("<IHHH", 0, 8, 8, 8) + compressed)
    return pixels


def add_jpeg_orientation(source, output):
    # A single TIFF IFD0 entry for orientation 6 (90 degrees clockwise).
    exif = b"Exif\0\0II" + struct.pack("<HIHHHII", 42, 8, 1, 274, 3, 1, 6) + b"\0" * 4
    original = source.read_bytes()
    output.write_bytes(original[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2)
                       + exif + original[2:])


def media_checks(work, ffmpeg, ffprobe, exiftool):
    for binary in (ffmpeg, ffprobe):
        output = command(binary, "-version").decode()
        require(output.splitlines()[0].split()[2] == FFMPEG_VERSION, f"Incorrect version for {binary}")
        for flag in ("--disable-gpl", "--disable-version3", "--disable-nonfree", "--disable-network"):
            require(flag in output, f"Missing {flag} in {binary.name}")

    def convert(*arguments):
        return command(ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                       "-filter_threads", "1", *arguments, cwd=work)

    def probe(*arguments):
        return json.loads(command(ffprobe, "-v", "error", "-of", "json", *arguments, cwd=work))

    def pixels(source, pixel_format="rgba"):
        return convert("-i", source, "-pix_fmt", pixel_format, "-fps_mode", "passthrough",
                       "-f", "rawvideo", "-")

    orange, blue = bytes((250, 103, 25, 128)), bytes((22, 41, 229, 255))
    write_png(work / "frame-01.png", orange)
    write_png(work / "frame-02.png", blue)
    tiff = write_tiff(work / "deflate.tiff")
    convert("-i", "frame-01.png", "-frames:v", "1", "-c:v", "mjpeg", "orientation-source.jpg")
    add_jpeg_orientation(work / "orientation-source.jpg", work / "orientation.jpg")
    inputs = [*work.glob("frame-*.png"), work / "deflate.tiff", work / "orientation.jpg",
              *FIXTURES.glob("*.heic"), *FIXTURES.glob("*.avif"), FIXTURES / "local-video.mp4"]
    originals = {item: sha256(item) for item in inputs}
    require(pixels("frame-01.png") == orange * (SIZE[0] * SIZE[1]), "PNG transparency changed")
    require(pixels("deflate.tiff", "rgb24") == tiff, "Deflate TIFF pixels changed")
    convert("-i", "frame-01.png", "-c:v", "libwebp", "-lossless", "1", "still.webp")
    require(pixels("still.webp") == orange * (SIZE[0] * SIZE[1]), "WebP alpha or RGB changed")
    convert("-f", "image2", "-framerate", "2", "-i", "frame-%02d.png",
            "-c:v", "libwebp_anim", "-lossless", "1", "animated.webp")
    require(pixels("animated.webp") == (orange * (SIZE[0] * SIZE[1]) + blue * (SIZE[0] * SIZE[1])),
            "Animated WebP did not retain both frames")
    convert("-i", "orientation.jpg", "-frames:v", "1", "oriented.png")
    require(struct.unpack(">II", (work / "oriented.png").read_bytes()[16:24]) == SIZE[::-1],
            "EXIF orientation was not applied")
    convert("-i", "frame-02.png", "-vf",
            "format=rgb24,setparams=color_primaries=bt709:color_trc=iec61966-2-1,iccgen",
            "-frames:v", "1", "profile.png")
    icc = (work / "profile.png").read_bytes()
    require(b"iCCP" in icc, "Generated ICC profile was not embedded")
    convert("-i", "profile.png", "-vf", "iccdetect", "-frames:v", "1", "profile-detected.png")
    require(b"iCCP" in (work / "profile-detected.png").read_bytes(), "ICC profile was lost")

    for name in ("still.heic", "tiled.heic", "still.avif"):
        convert("-f", "mov", "-i", FIXTURES / name, "-frames:v", "1", name + ".png")
        dimensions = struct.unpack(">II", (work / (name + ".png")).read_bytes()[16:24])
        require(dimensions == ((1024, 768) if name == "tiled.heic" else (64, 48)),
                f"Incorrect decoded dimensions for {name}: {dimensions}")
    groups = probe("-show_stream_groups", FIXTURES / "tiled.heic")["stream_groups"]
    require(any(group["type"] == "Tile Grid" and group["nb_streams"] > 1 for group in groups),
            "Tiled HEIC is missing a multi-tile stream group")

    video = FIXTURES / "local-video.mp4"
    result = probe("-show_entries", "format=format_name,duration:stream=index,codec_type,codec_name,width,height",
                   video)
    require(result["streams"][0]["codec_name"] == "h264", "FFprobe did not identify H.264")
    convert("-ss", "0.5", "-i", video, "-frames:v", "1", "-an", "-f", "image2", "video-frame.jpg")
    require((work / "video-frame.jpg").stat().st_size > 0, "Video frame extraction failed")

    if exiftool:
        require(command(exiftool, "-ver").decode().strip() == EXIFTOOL_VERSION,
                "Incorrect ExifTool version")
        metadata = json.loads(command(exiftool, "-json", "-n", "-d", "%Y-%m-%dT%H:%M:%S%z",
                                      "-Orientation", "orientation.jpg", cwd=work))[0]
        require(metadata["Orientation"] == 6, "ExifTool did not report orientation")
        metadata = json.loads(command(exiftool, "-config", "", "-json", "-n", "-b",
                                      "-ICC_Profile", "profile.png", cwd=work))[0]
        require(metadata["ICC_Profile"].startswith("base64:"), "ExifTool did not read the ICC profile")

    require(originals == {item: sha256(item) for item in inputs}, "A source media file changed")
    print("Media capability and original integrity checks passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--architecture-only", action="store_true")
    args = parser.parse_args()
    verify(args.candidate)
    data = json.loads((args.candidate / "artifacts.json").read_text(encoding="utf-8"))
    platform = data["platform"]
    ffmpeg_archive, ffprobe_archive, exiftool_archive, _ = layout(platform, data["revision"])
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for filename in [ffmpeg_archive] + ([ffprobe_archive] if ffprobe_archive else []):
            with ZipFile(args.candidate / filename) as archive:
                archive.extractall(work)
        binaries = [work / "bin" / name for name in binary_names(platform)]
        for binary in binaries:
            binary.chmod(0o755)
        verify_architecture(binaries, platform)
        if args.architecture_only:
            return
        exiftool = None
        if exiftool_archive:
            record = SOURCES["exiftool"]
            shutil.copyfile(args.candidate / exiftool_archive, work / record["file"])
            exiftool = source_tree("exiftool", work, work) / "exiftool"
        media_checks(work, *binaries, exiftool)


if __name__ == "__main__":
    main()
