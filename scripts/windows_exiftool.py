"""Build the Windows ExifTool candidate with Strawberry Perl's own XS toolchain."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile

from inputs import ROOT, SOURCES, sha256, source_archive, source_tree
from windows_runtime import linked_objects

XS_SOURCES = ("perl-brotli", "perl-findfile", "perl-zlib")
WINLIBS_BASE_SOURCES = ("winlibs-gcc-upstream", "winlibs-mingw-upstream")
ARCHIVE_NOTICES = ("perl-core", *WINLIBS_BASE_SOURCES)
PERL_DLLS = ("perl542.dll", "libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")
RUNTIME_DIR = "exiftool_files"
RUNTIME_BUILD = "build/windows-exiftool.json"
CORE_MODULES = (
    "AutoLoader.pm", "AutoSplit.pm", "autouse.pm", "base.pm", "Carp.pm", "Carp", "Compress/Raw/Bzip2.pm",
    "Compress/Zlib.pm", "Config.pm", "Config_git.pl",
    "Config_heavy.pl", "Cwd.pm", "Digest.pm", "Digest", "DirHandle.pm", "DynaLoader.pm",
    "Encode.pm", "Encode", "Errno.pm", "Exporter.pm", "Exporter", "Fcntl.pm", "File",
    "FileHandle.pm", "Getopt", "IO.pm", "IO", "List", "MIME", "POSIX.pm",
    "Scalar", "SelectSaver.pm", "Symbol.pm", "Tie/Handle.pm", "Tie/StdHandle.pm",
    "Time", "Win32.pm", "Win32API",
    "XSLoader.pm", "bytes.pm", "constant.pm", "integer.pm", "lib.pm", "locale.pm",
    "overload.pm", "overload", "overloading.pm", "parent.pm", "strict.pm", "utf8.pm",
    "vars.pm", "warnings.pm", "warnings",
)
CORE_XS = (
    "Compress/Raw/Bzip2", "Cwd", "Digest", "Encode", "Fcntl", "File/DosGlob", "File/Glob",
    "IO", "List/Util", "MIME/Base64", "POSIX", "Time/HiRes", "Time/Piece",
    "Win32", "Win32API/File",
)
VENDOR_MODULES = ("Win32/API.pm", "Win32/API", "auto/Win32/API")
RUNTIME_SUFFIXES = {".pm", ".pl", ".al", ".ix", ".dll", ".enc"}
WIN32_FILE_DATA = "Win32API/File/cFile.pc"
NOTICE_FILES = {
    "licenses/exiftool/README", "licenses/exiftool/Artistic",
    "licenses/perl/Artistic", "licenses/perl/Copying", "licenses/perl/Readme",
    "licenses/perl-brotli/README", "licenses/perl-brotli/brotli/LICENSE",
    "licenses/perl-findfile/README", "licenses/perl-findfile/META.yml",
    "licenses/perl-win32-api/README", "licenses/perl-win32-api/META.json",
    "licenses/zlib/LICENSE", "licenses/perl-zlib/README",
} | {f"licenses/{name}/{path}" for name in ARCHIVE_NOTICES for path in SOURCES[name]["notices"]}
WINDOWS_SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "comctl32.dll", "kernel32.dll", "msvcrt.dll",
    "netapi32.dll", "ntdll.dll", "ole32.dll", "oleaut32.dll", "psapi.dll", "shell32.dll",
    "ucrtbase.dll", "user32.dll", "userenv.dll", "version.dll", "winhttp.dll", "ws2_32.dll",
}


def unpack_portable(archive, destination):
    # Select only the vendor directories needed to build or stage the package.
    names = set()
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            name = entry.filename.rstrip("/")
            if entry.is_dir() or (name != "portable.perl"
                                  and not name.startswith(("perl/", "c/", "licenses/perl/"))):
                continue
            parts = name.split("/")
            if (any(not part or part in {".", ".."} or part.endswith((".", " ")) for part in parts)
                    or "\\" in name or ":" in name or name.casefold() in names
                    or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)):
                raise ValueError(f"Unsafe Strawberry Perl ZIP member: {name}")
            names.add(name.casefold())
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def command(arguments, cwd, env, capture=False, **kwargs):
    result = subprocess.run([str(item) for item in arguments], cwd=cwd, env=env,
                            check=True, encoding="utf-8", errors="replace",
                            capture_output=capture, **kwargs)
    return result.stdout if capture else None


def tool_environment(portable):
    system = Path(os.environ["SystemRoot"])
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PERL", "LC_"))
           and key.upper() not in {"LANG", "SHELL", "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "CMAKE_GENERATOR"}}
    env["PATH"] = os.pathsep.join(map(str, (portable / "perl/bin", portable / "c/bin",
                                           system / "System32", system)))
    return env


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError(f"Duplicate ExifTool runtime path: {destination.name}")
    shutil.copyfile(source, destination)


def copy_modules(source, target, selections):
    for item in selections:
        path = source / item
        if not path.exists():
            raise ValueError(f"Missing selected Perl runtime module: {item}")
        for file in (path.rglob("*") if path.is_dir() else (path,)):
            if file.is_file() and file.suffix in RUNTIME_SUFFIXES:
                copy(file, target / file.relative_to(source))


def copy_upstream_notices(cache, output, name):
    record = SOURCES[name]
    with tarfile.open(source_archive(name, cache, download=True), "r:*") as archive:
        for path in record["notices"]:
            member = archive.getmember(f"{record['directory']}/{path}")
            if not member.isfile():
                raise ValueError(f"Expected a regular notice in {name}: {path}")
            destination = output / "licenses" / name / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer)


def build_brotli(source, tools, perl, env, jobs):
    build = source / "brotli-build"
    command([tools / "cmake.exe", "-S", "brotli", "-B", build, "-G", "Ninja",
             "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF",
             "-DBROTLI_BUILD_TOOLS=OFF", "-DCMAKE_C_COMPILER=gcc",
             f"-DCMAKE_C_FLAGS=-ffile-prefix-map={source.as_posix()}=/build"], source, env)
    command([tools / "cmake.exe", "--build", build, "--parallel", jobs], source, env)
    command([tools / "ar.exe", "-M"], build, env, input=(
        "create libbrotli.a\naddlib libbrotlienc.a\naddlib libbrotlidec.a\n"
        "addlib libbrotlicommon.a\nsave\nend\n"))
    command([tools / "ranlib.exe", "libbrotli.a"], build, env)
    command([perl, ROOT / "scripts/windows-brotli-Makefile.PL"], source, env)


def dependency_report(directory, objdump, env):
    files = [path.relative_to(directory).as_posix() for path in directory.rglob("*")
             if path.is_file() and path.suffix.lower() in {".exe", ".dll"}]
    bundled = set(PERL_DLLS)
    report = {}
    for name in sorted(files):
        if "pei-x86-64" not in command([objdump, "-f", name], directory, env, capture=True):
            raise ValueError(f"Incorrect Windows PE architecture: {name}")
        details = command([objdump, "-p", name], directory, env, capture=True)
        imports = sorted(set(re.findall(r"DLL Name:\s*(\S+)", details, re.IGNORECASE)), key=str.lower)
        missing = [item for item in imports if item.lower() not in WINDOWS_SYSTEM_DLLS | bundled
                   and not re.fullmatch(r"api-ms-win-crt-[a-z]+-l[0-9]+-[0-9]+-[0-9]+\.dll", item.lower())]
        if not imports or missing:
            raise ValueError(f"Unresolved Windows PE imports for {name}: {missing}")
        report[name] = [item.lower() for item in imports]
    if not all(f"{RUNTIME_DIR}/{name}" in report for name in bundled):
        raise ValueError("Incomplete Strawberry Perl DLL closure")
    return report


def build(cache, work, jobs):
    work, cache = work.resolve(), cache.resolve()
    build_dir = work / "exiftool-build"
    build_dir.mkdir()
    portable = build_dir / "perl"
    unpack_portable(source_archive("strawberry-perl", cache, download=True), portable)
    exif, brotli, findfile, zlib_xs, win32_api, zlib = [
        source_tree(name, cache, build_dir)
        for name in ("exiftool", *XS_SOURCES, "perl-win32-api", "zlib")
    ]
    tools, perl = portable / "c/bin", portable / "perl/bin/perl.exe"
    env = tool_environment(portable)
    abi = command([perl, "-MConfig", "-e",
                   "print join q{|}, @Config{qw(version archname gccversion dlext)}"],
                  build_dir, env, capture=True)
    if abi != "5.42.3|MSWin32-x64-multi-thread|13.2.0|xs.dll":
        raise ValueError(f"Unexpected Strawberry Perl ABI: {abi}")
    build_brotli(brotli, tools, perl, env, jobs)
    # Newer ParseXS generates the fallback overload registration automatically.
    # Remove the old duplicate declaration while retaining the real overloads.
    xs = findfile / "FindFile.xs"
    original = xs.read_text(encoding="ascii")
    declaration = "void\nnil()\n    OVERLOAD: )\n    PPCODE:\n\n"
    if original.count(declaration) != 1:
        raise ValueError("Unexpected Win32::FindFile fallback overload declaration")
    xs.write_bytes(original.replace(declaration, "").encode("ascii"))
    command([perl, "Makefile.PL"], findfile, env)
    # Build against the same patched zlib source used for FFmpeg.
    zlib_path = zlib.as_posix()
    command([perl, "Makefile.PL"], zlib_xs,
            dict(env, BUILD_ZLIB="True", ZLIB_INCLUDE=zlib_path, ZLIB_LIB=zlib_path))
    link_maps = {"brotli": brotli / "runtime.link.map", "findfile": findfile / "runtime.link.map",
                 "zlib": zlib_xs / "runtime.link.map", "launcher": build_dir / "launcher.link.map"}
    for source in (brotli, findfile, zlib_xs):
        command([tools / "gmake.exe", f"-j{jobs}", "OTHERLDFLAGS=-Wl,-Map,runtime.link.map"], source, env)
    version = command([perl, "-Mblib", "-MCompress::Raw::Zlib", "-e",
                       "print Compress::Raw::Zlib::zlib_version()"], zlib_xs, env, capture=True)
    if version != SOURCES["zlib"]["version"]:
        raise ValueError(f"Unexpected zlib version in Perl XS: {version}")

    output = work / "exiftool"
    runtime = output / RUNTIME_DIR
    library = runtime / "lib"
    copy(exif / "exiftool", runtime / "exiftool.pl")
    copy_modules(exif / "lib", library, ("Image", "File/RandomAccess.pm"))
    copy(exif / "lib/Image/ExifTool/Geolocation.dat", library / "Image/ExifTool/Geolocation.dat")
    for name in PERL_DLLS:
        copy(portable / "perl/bin" / name, runtime / name)
    copy_modules(portable / "perl/lib", library, CORE_MODULES + tuple(f"auto/{item}" for item in CORE_XS))
    copy(portable / "perl/lib" / WIN32_FILE_DATA, library / WIN32_FILE_DATA)
    copy_modules(portable / "perl/vendor/lib", library, VENDOR_MODULES)
    for source, modules in ((brotli, ("IO/Compress/Brotli.pm", "IO/Uncompress/Brotli.pm",
                                     "auto/IO/Compress/Brotli/Brotli.xs.dll")),
                            (findfile, ("Win32/FindFile.pm", "Win32/FindFile/FileData.pm",
                                        "auto/Win32/FindFile/FindFile.xs.dll")),
                            (zlib_xs, ("Compress/Raw/Zlib.pm", "auto/Compress/Raw/Zlib/Zlib.xs.dll"))):
        for module in modules:
            subdir = "arch" if module.startswith("auto/") else "lib"
            copy(source / "blib" / subdir / module, library / module)

    scripts = ROOT / "scripts"
    resource = build_dir / "launcher.o"
    command([tools / "windres.exe", "-i", scripts / "windows-exiftool-launcher.rc",
             "-o", resource], scripts, env)
    command([tools / "gcc.exe", "-O2", "-s", "-municode", "-D_WIN32_WINNT=0x0A00",
             "-Wall", "-Wextra", "-Wno-cast-function-type", scripts / "windows-exiftool-launcher.c",
             resource, "-Wl,-Map,launcher.link.map", "-o", output / "exiftool.exe"], build_dir, env)

    for name, source in (("exiftool", exif), ("perl-brotli", brotli), ("perl-findfile", findfile),
                         ("perl-win32-api", win32_api), ("perl-zlib", zlib_xs), ("zlib", zlib)):
        for item in SOURCES[name]["notices"]:
            copy(source / item, output / "licenses" / name / item)
    copy(ROOT / "licenses/ExifTool-Artistic.txt", output / "licenses/exiftool/Artistic")
    for item in ("Artistic", "Copying", "Readme"):
        copy(portable / "licenses/perl" / item, output / "licenses/perl" / item)
    for name in ARCHIVE_NOTICES:
        copy_upstream_notices(cache, output, name)

    imports = dependency_report(output, tools / "objdump.exe", env)
    objects = {name: sorted({item for _, item in linked_objects(path, portable)})
               for name, path in link_maps.items()}
    result = {"perlAbi": abi, "perlZlib": version, "peImports": imports, "winlibsLinkedObjects": objects,
              "members": {
        item.relative_to(output).as_posix(): sha256(item)
        for item in sorted(output.rglob("*")) if item.is_file()
    }}
    record = output / RUNTIME_BUILD
    record.parent.mkdir()
    record.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("jobs", type=int)
    args = parser.parse_args()
    if sys.platform != "win32" or args.jobs < 1:
        parser.error("The ExifTool build needs native Windows and a positive job count")
    try:
        build(args.cache, args.work, args.jobs)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
            tarfile.TarError, zipfile.BadZipFile) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
