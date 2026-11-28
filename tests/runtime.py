"""Validate candidate native binaries and exercise CasaMemo media operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from zipfile import ZipFile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from artifacts import EXIFTOOL_VERSION, FFMPEG_VERSION, binary_names, layout, verify
from inputs import SOURCES, sha256, source_tree
from windows_exiftool import RUNTIME_BUILD, dependency_report

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


def command(*arguments, cwd=None, env=None):
    result = subprocess.run([str(value) for value in arguments], stderr=subprocess.PIPE,
                            stdout=subprocess.PIPE, timeout=60, cwd=cwd, env=env)
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


def png_icc(path):
    data = path.read_bytes()
    index = 8
    while index < len(data):
        length, kind = struct.unpack_from(">I4s", data, index)
        if kind == b"iCCP":
            _, payload = data[index + 8:index + 8 + length].split(b"\0", 1)
            require(payload[0] == 0, "Unexpected PNG ICC compression")
            return zlib.decompress(payload[1:])
        index += length + 12
    raise RuntimeError("PNG has no ICC profile")


def heic_checks(work, convert, probe, exiftool):
    def quadrants(rgb, width, height):
        require(len(rgb) == width * height * 3, "Unexpected RGB frame size")
        corners = []
        for y in (height // 4, 3 * height // 4):
            for x in (width // 4, 3 * width // 4):
                index = 3 * (y * width + x)
                corners.append(tuple(component > 125 for component in rgb[index:index + 3]))
        return corners

    red, green, blue, yellow = (True, False, False), (False, True, False), (False, False, True), (True, True, False)
    tiled = FIXTURES / "tiled.heic"
    groups = probe("-show_stream_groups", tiled)["stream_groups"]
    require(any(group["type"] == "Tile Grid" and group["nb_streams"] == 4 for group in groups),
            "Tiled HEIC is missing its four-tile stream group")
    graph = ("[0:0][0:1][0:2][0:3]xstack=inputs=4:layout=0_0|512_0|0_512|512_512,"
             "crop=1024:768:0:0:exact=1,setparams=range=pc:colorspace=smpte170m,"
             "scale=64:48:flags=lanczos,format=rgb24[image]")
    pixels = convert("-noautorotate", "-f", "mov", "-i", tiled, "-filter_complex_threads", "1",
                     "-filter_complex", graph, "-map", "[image]", "-frames:v", "1", "-f", "rawvideo", "-")
    require(quadrants(pixels, 64, 48) == [red, green, blue, yellow],
            "Explicit HEIC tile assembly changed the quadrant order or colour")

    profiled = FIXTURES / "profiled.heic"
    transform = "transpose=clock,vflip,format=rgb24"
    mirrored = convert("-noautorotate", "-i", profiled, "-vf", transform,
                       "-frames:v", "1", "-f", "rawvideo", "-")
    require(quadrants(mirrored, 48, 64) == [yellow, green, blue, red],
            "HEIC mirrored rotation produced incorrect pixels")
    convert("-noautorotate", "-i", profiled, "-vf", transform, "-frames:v", "1", "oriented-heic.png")
    oriented = work / "oriented-heic.png"
    require(struct.unpack_from(">II", oriented.read_bytes(), 16) == (48, 64),
            "HEIC mirrored rotation did not swap image dimensions")
    output_profile = png_icc(oriented)
    require(hashlib.sha256(output_profile).hexdigest()
            == "904d9d78a48e10b01a7d76c57c9321df5ab3228b9441489d21fbc4fa53b5fe41",
            "HEIC embedded ICC profile changed after decode and transform")
    if exiftool:
        metadata = json.loads(command(exiftool, "-config", "", "-json", "-n",
                                      "-IFD0:Orientation", profiled))[0]
        require(metadata["Orientation"] == 7, "Mirrored HEIC fixture lost its EXIF orientation")
        require(command(exiftool, "-config", "", "-b", "-ICC_Profile", profiled) == output_profile,
                "HEIC ICC extraction disagrees with the decoded PNG")

    hdr = FIXTURES / "pq.heic"
    stream = probe("-select_streams", "v:0", "-show_streams", hdr)["streams"][0]
    expected = {"pix_fmt": "yuv420p10le", "color_primaries": "bt2020",
                "color_transfer": "smpte2084", "color_space": "bt2020nc"}
    require(all(stream.get(key) == value for key, value in expected.items()),
            "10-bit HEIC HDR signalling changed")
    decoded = convert("-noautorotate", "-i", hdr, "-pix_fmt", "yuv420p10le",
                      "-frames:v", "1", "-f", "rawvideo", "-")
    require(len(decoded) == 64 * 48 * 3, "Incorrect bit depth or dimensions for the PQ HEIC")
    middle = struct.unpack_from("<H", decoded, 2 * (24 * 64 + 32))[0]
    require(256 < middle < 1024, "PQ HEIC sample was clipped or reduced to 8 bits")


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
    raw_h265 = work / "video.h265"
    shutil.copyfile(FIXTURES / "video.hevc", raw_h265)
    inputs = [*work.glob("frame-*.png"), work / "deflate.tiff", work / "orientation.jpg",
              *FIXTURES.glob("*.heic"), *FIXTURES.glob("*.avif"), FIXTURES / "local-video.mp4",
              FIXTURES / "video.h264", FIXTURES / "video.hevc", raw_h265]
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
    heic_checks(work, convert, probe, exiftool)

    for raw, codec in ((FIXTURES / "video.h264", "h264"), (raw_h265, "hevc"), (FIXTURES / "video.hevc", "hevc")):
        result = probe("-show_entries", "format=format_name:stream=codec_name,width,height", raw)
        stream = result["streams"][0]
        require(result["format"]["format_name"] == codec and stream["codec_name"] == codec
                and (stream["width"], stream["height"]) == (64, 48),
                f"Raw {raw.suffix} stream was not probed correctly")
        image = work / (raw.suffix[1:] + "-frame.png")
        convert("-ss", "0", "-i", raw, "-frames:v", "1", "-an", "-f", "image2", image)
        require(struct.unpack_from(">II", image.read_bytes(), 16) == (64, 48),
                f"Raw {raw.suffix} frame extraction changed the PNG dimensions")

    video = FIXTURES / "local-video.mp4"
    result = probe("-show_entries", "format=format_name,duration:stream=index,codec_type,codec_name,width,height",
                   video)
    require(result["streams"][0]["codec_name"] == "h264", "FFprobe did not identify H.264")
    convert("-ss", "0.5", "-i", video, "-frames:v", "1", "-an", "-f", "image2", "video-frame.png")
    require((work / "video-frame.png").stat().st_size > 0, "Video frame extraction failed")

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


def windows_exiftool_checks(work, executable, source_archive):
    info = SOURCES["exiftool"]
    fixture = f"{info['directory']}/t/images/JXL2.jxl"
    with ZipFile(source_archive) as sources, sources.open(f"upstream/{info['file']}") as source:
        with tarfile.open(fileobj=source, mode="r:gz") as upstream:
            with upstream.extractfile(fixture) as stream:
                jxl = stream.read()
    folder = work / "사진 문서"
    folder.mkdir()
    media = folder / "撮影-é 🏡.jxl"
    media.write_bytes(jxl)
    original = sha256(media)
    system = Path(os.environ["SystemRoot"])
    env = dict(os.environ, PATH=os.pathsep.join(map(str, (system / "System32", system))))
    versions = command(executable, "-config", "", "-ver", "-v", cwd=work, env=env).decode()
    for name, version in (("Win32::FindFile", SOURCES["perl-findfile"]["version"]),
                          ("Win32API::File", "0.1203_01")):
        require(re.search(rf"^\s+{re.escape(name)}[ \t]+{re.escape(version)}\s*$",
                          versions, re.MULTILINE), f"ExifTool could not load {name}")
    for target in (media.relative_to(work), folder.relative_to(work)):
        data = json.loads(command(executable, "-config", "", "-G1", "-json", "-IFD0:Artist",
                                  "-XMP-dc:Subject", "-ImageSize", target, cwd=work, env=env))
        require(len(data) == 1 and data[0].get("IFD0:Artist") == "me"
                and data[0].get("XMP-dc:Subject") == "ExifTool test"
                and data[0].get("Composite:ImageSize") == "200x130",
                "Compressed JPEG XL EXIF or XMP extraction failed on a Unicode path")
        require(Path(data[0]["SourceFile"]).name == media.name, "ExifTool changed the Unicode filename")
    require(sha256(media) == original, "ExifTool changed the original JPEG XL")
    print("Windows ExifTool compressed JPEG XL, Unicode paths and original integrity verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--architecture-only", action="store_true")
    args = parser.parse_args()
    verify(args.candidate)
    data = json.loads((args.candidate / "artifacts.json").read_text(encoding="utf-8"))
    platform = data["platform"]
    ffmpeg_archive, ffprobe_archive, exiftool_archive, sources = layout(platform, data["revision"])
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for filename in [ffmpeg_archive] + ([ffprobe_archive] if ffprobe_archive else []):
            with ZipFile(args.candidate / filename) as archive:
                archive.extractall(work)
        binaries = [work / "bin" / name for name in binary_names(platform)]
        for binary in binaries:
            binary.chmod(0o755)
        verify_architecture(binaries, platform)
        exiftool = None
        if platform == "windows-x64":
            exif_work = work / "ExifTool 工具"
            with ZipFile(args.candidate / exiftool_archive) as archive:
                archive.extractall(exif_work)
            record = json.loads((exif_work / RUNTIME_BUILD).read_text(encoding="utf-8"))
            require(dependency_report(exif_work, "objdump", os.environ) == record["peImports"],
                    "Windows ExifTool packaged PE dependency report differs from the binaries")
            print("Windows ExifTool PE architecture and DLL closure verified")
            exiftool = exif_work / "exiftool.exe"
        if args.architecture_only:
            return
        if platform == "windows-x64":
            windows_exiftool_checks(work, exiftool, args.candidate / sources)
        else:
            record = SOURCES["exiftool"]
            shutil.copyfile(args.candidate / exiftool_archive, work / record["file"])
            exiftool = source_tree("exiftool", work, work) / "exiftool"
        media_checks(work, *binaries, exiftool)


if __name__ == "__main__":
    main()
