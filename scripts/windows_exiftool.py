"""Build Windows ExifTool and its XS modules against CasaMemo's patched Perl."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

from inputs import ROOT, SOURCES, path_spellings, sha256, source_tree
from windows_perl import (
    PERL_ABI, PERL_DLL, PERL_IDENTITY, PERL_PATCHES, PERL_RUNTIME_PACKAGES,
    compile_perl, msys_path, msys_tool, stage_perl, stage_recipe, stage_runtime_dlls, ucrt_prefix,
)
from windows_runtime import SOURCE_PACKAGES, check_packages, linked_objects

XS_SOURCES = ("perl-brotli", "perl-findfile", "perl-zlib")
RUNTIME_DLL_OWNERS = {SOURCES[key]["member"]: key for key in PERL_RUNTIME_PACKAGES}
PERL_DLLS = (PERL_DLL, *RUNTIME_DLL_OWNERS)
BROTLI_VERSION = "1.2.1"
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
    "Compress/Raw/Bzip2", "Cwd", "Digest/MD5", "Digest/SHA", "Encode",
    "Encode/Byte", "Encode/CN", "Encode/EBCDIC", "Encode/JP", "Encode/KR",
    "Encode/Symbol", "Encode/TW", "Encode/Unicode", "Fcntl", "File/DosGlob", "File/Glob",
    "IO", "List/Util", "MIME/Base64", "POSIX", "Time/HiRes", "Time/Piece",
    "Win32", "Win32API/File",
)
CORE_XS_FILES = tuple(f"auto/{name}/{name.rsplit('/', 1)[-1]}.dll" for name in CORE_XS)
VENDOR_MODULES = ("Win32/API.pm", "Win32/API", "auto/Win32/API")
RUNTIME_SUFFIXES = {".pm", ".pl", ".al", ".ix", ".dll", ".enc"}
WIN32_FILE_DATA = "Win32API/File/cFile.pc"
NOTICE_FILES = {
    "licenses/exiftool/README", "licenses/exiftool/Artistic",
    "licenses/perl/Artistic", "licenses/perl/Copying", "licenses/perl/Readme",
    "licenses/perl-brotli/README", "licenses/perl-brotli/brotli/LICENSE",
    "licenses/perl-findfile/README", "licenses/perl-findfile/META.yml",
    "licenses/perl-win32-api/README", "licenses/perl-win32-api/META.json",
    "licenses/zlib/LICENSE", "licenses/perl-zlib/README", "licenses/perl/bzip2-LICENSE",
    "licenses/msys2/COPYING.RUNTIME", "licenses/msys2/COPYING3",
    "licenses/msys2/COPYING.MinGW-w64-runtime.txt", "licenses/msys2/COPYING.winpthreads",
}
BUILT_XS = {
    "perl-brotli": ("IO/Compress/Brotli.pm", "IO/Uncompress/Brotli.pm", "auto/IO/Compress/Brotli/Brotli.dll"),
    "perl-findfile": ("Win32/FindFile.pm", "Win32/FindFile/FileData.pm", "auto/Win32/FindFile/FindFile.dll"),
    "perl-zlib": ("Compress/Raw/Zlib.pm", "auto/Compress/Raw/Zlib/Zlib.dll"),
}
NATIVE_FILES = {
    "exiftool.exe", *(f"{RUNTIME_DIR}/{name}" for name in PERL_DLLS),
    *(f"{RUNTIME_DIR}/lib/{name}" for name in CORE_XS_FILES),
    *(f"{RUNTIME_DIR}/lib/{modules[-1]}" for modules in BUILT_XS.values()),
    f"{RUNTIME_DIR}/lib/auto/Win32/API/API.dll",
    f"{RUNTIME_DIR}/lib/auto/Win32/API/Callback/Callback.dll",
}
PERL_IMPORT_ARCHIVE = "perl/lib/CORE/libperl544.a"
WIN32_CORE_ARCHIVE = "perl/lib/auto/Win32CORE/Win32CORE.a"
BROTLI_ARCHIVE = "brotli/brotli-build/libbrotli.a"
LOCAL_LINK_ARCHIVES = {
    PERL_IMPORT_ARCHIVE: ("msys2-perl", {"../../lib/CORE/libperl544.a", "../../../lib/CORE/libperl544.a"}),
    WIN32_CORE_ARCHIVE: ("msys2-perl", {"../lib/auto/Win32CORE/Win32CORE.a"}),
    BROTLI_ARCHIVE: ("perl-brotli", {"brotli-build/libbrotli.a"}),
}
WINDOWS_SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "comctl32.dll", "kernel32.dll", "msvcrt.dll",
    "netapi32.dll", "ntdll.dll", "ole32.dll", "oleaut32.dll", "psapi.dll", "shell32.dll",
    "ucrtbase.dll", "user32.dll", "userenv.dll", "version.dll", "winhttp.dll", "ws2_32.dll",
}


def command(arguments, cwd, env, capture=False, **kwargs):
    result = subprocess.run([str(item) for item in arguments], cwd=cwd, env=env,
                            check=True, encoding="utf-8", errors="replace",
                            capture_output=capture, **kwargs)
    return result.stdout if capture else None


def tool_environment(prefix, native_tools, perl_tree):
    system = Path(os.environ["SystemRoot"])
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PERL", "LC_"))
           and key.upper() not in {
               "LANG", "SHELL", "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "CMAKE_GENERATOR",
               "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CPATH", "LIBRARY_PATH", "PKG_CONFIG_LIBDIR",
           }}
    env["PATH"] = os.pathsep.join(map(str, (perl_tree, prefix / "bin", native_tools,
                                           system / "System32", system)))
    env["LC_ALL"] = "C"
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


def build_brotli(source, tools, perl, env, jobs, makefile_options):
    build = source / "brotli-build"
    cmake = shutil.which("cmake")
    if not cmake:
        raise ValueError("CMake is required to build the pinned Brotli sources")
    command([cmake, "-S", "brotli", "-B", build, "-G", "Ninja",
             "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF",
             "-DBROTLI_BUILD_TOOLS=OFF", "-DCMAKE_C_COMPILER=gcc",
             f"-DCMAKE_C_FLAGS=-ffile-prefix-map={source.as_posix()}=/build"], source, env)
    command([cmake, "--build", build, "--parallel", jobs], source, env)
    command([tools / "ar.exe", "-M"], build, env, input=(
        "create libbrotli.a\naddlib libbrotlienc.a\naddlib libbrotlidec.a\n"
        "addlib libbrotlicommon.a\nsave\nend\n"))
    command([tools / "ranlib.exe", "libbrotli.a"], build, env)
    # Expose the version from the encoder and decoder actually linked into this DLL.
    with (source / "Brotli.xs").open("a", encoding="ascii", newline="\n") as xs:
        xs.write("""

UV
casamemo_native_version()
  CODE:
    RETVAL = BrotliEncoderVersion();
    if (RETVAL != BrotliDecoderVersion())
        croak("The linked Brotli encoder and decoder versions differ");
  OUTPUT:
    RETVAL
""")
    command([*perl, ROOT / "scripts/windows-brotli-Makefile.PL", *makefile_options], source, env)


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
        raise ValueError("Incomplete UCRT64 Perl DLL closure")
    return report


def build(cache, work, jobs):
    work, cache = work.resolve(), cache.resolve()
    check_packages()
    build_dir = work / "exiftool-build"
    build_dir.mkdir()
    recipe, native_tools, patches = stage_perl(cache, build_dir)
    perl_tree = compile_perl(recipe, native_tools, patches, jobs)
    build_runtime(cache, work, build_dir, recipe, native_tools, perl_tree, jobs)


def required_local_archives(binary):
    name = Path(binary).name
    if name == "exiftool.exe":
        return set()
    if name == PERL_DLL:
        return {WIN32_CORE_ARCHIVE}
    if name == "Brotli.dll":
        return {PERL_IMPORT_ARCHIVE, BROTLI_ARCHIVE}
    return {PERL_IMPORT_ARCHIVE}


def record_linkage(imports, prefix, perl_tree, core_maps, extension_maps, brotli):
    compiler_inputs, targets = {}, {}
    external_names = {"Brotli.dll", "FindFile.dll", "Zlib.dll", "API.dll", "Callback.dll", "exiftool.exe"}
    for member in imports:
        filename = Path(member).name
        if filename in RUNTIME_DLL_OWNERS:
            continue
        maps = extension_maps if filename in external_names else core_maps
        link_map = maps / f"{filename}.map"
        objects = linked_objects(link_map, prefix)
        inputs = {}
        for path, object_name in sorted(objects):
            name = f"ucrt64/{path.relative_to(prefix).as_posix()}"
            if name not in compiler_inputs:
                owner = subprocess.check_output(["pacman", "-Qqo", path.as_posix()], text=True).strip()
                owner = owner.removeprefix("mingw-w64-ucrt-x86_64-")
                if owner not in SOURCE_PACKAGES:
                    raise ValueError(f"Unreviewed UCRT64 link input {path.name} from {owner}")
                compiler_inputs[name] = {"owner": owner, "sha256": sha256(path)}
            inputs.setdefault(name, []).append(object_name)
        map_text = link_map.read_text(encoding="utf-8", errors="replace")
        mapped = re.search(r"(?m)^OUTPUT\((.+) pei-x86-64\)$", map_text)
        if not mapped or Path(mapped[1]).name != filename:
            raise ValueError(f"The native link map does not describe {filename}")
        if filename == PERL_DLL and not re.search(r"(?m)^LOAD .*regexec\.o$", map_text):
            raise ValueError("The patched Perl link map does not contain regexec.o")
        local_inputs = {}
        for spelling, item in re.findall(r"(?m)^(\S[^\r\n]*?\.a)\(([^)]+)\)(?:\s|$)", map_text):
            path = Path(spelling)
            if path.is_absolute() and path.resolve().is_relative_to(prefix):
                continue
            for name, (owner, relative_paths) in LOCAL_LINK_ARCHIVES.items():
                area, relative = name.split("/", 1)
                archive = (perl_tree if area == "perl" else brotli) / relative
                if (path.resolve() == archive.resolve() if path.is_absolute()
                        else path.as_posix() in relative_paths):
                    if name not in compiler_inputs:
                        compiler_inputs[name] = {"owner": owner, "sha256": sha256(archive)}
                    local_inputs.setdefault(name, set()).add(item)
                    break
            else:
                raise ValueError(f"Unreviewed static archive {path.name} in the map for {filename}")
        if set(local_inputs) != required_local_archives(member):
            raise ValueError(f"Unexpected local static link inventory for {filename}")
        inputs.update({name: sorted(members) for name, members in local_inputs.items()})
        targets[member] = inputs
    return compiler_inputs, targets


def redact_build_paths(text, *build_roots):
    for root in sorted({ROOT, Path.home(), *build_roots}, key=lambda path: len(str(path)), reverse=True):
        for value in path_spellings(root):
            text = re.sub(re.escape(value), "@CASAMEMO_BUILD@", text, flags=re.IGNORECASE)
    return text


def sanitize_perl_configuration(library, prefix, recipe):
    # These generated module files include paths for the build-time compiler
    # and installation prefix. The shipped interpreter uses the explicit -I.
    for filename in ("Config.pm", "Config_heavy.pl", "Config_git.pl"):
        path = library / filename
        text = redact_build_paths(path.read_text(encoding="utf-8"), prefix, recipe)
        path.write_text(text, encoding="utf-8", newline="\n")


def build_runtime(cache, work, build_dir, recipe, native_tools, perl_tree, jobs):
    exif, brotli, findfile, zlib_xs, zlib = [
        source_tree(name, cache, build_dir)
        for name in ("exiftool", *XS_SOURCES, "zlib")
    ]
    api_recipe = stage_recipe("msys2-perl-win32-api", cache, build_dir, "Win32-API-0.84.tar.gz")
    win32_api = api_recipe / "Win32-API-0.84"
    command([msys_tool("patch.exe"), "--batch", "--forward", "--fuzz=0", "-p1", "-i",
             msys_path(api_recipe / "0001-clang-as-defines.patch", msys_tool("cygpath.exe"))],
            win32_api, os.environ)
    prefix = ucrt_prefix()
    tools = prefix / "bin"
    perl_lib = perl_tree / "lib"
    perl = (perl_tree / "perl.exe", f"-I{perl_lib}")
    env = tool_environment(prefix, native_tools, perl_tree)
    # MakeMaker starts child interpreters without the top-level -I. Limit
    # their search path to this freshly built tree as well.
    env["PERL5LIB"] = str(perl_lib)
    abi = command([*perl, "-MConfig", "-e",
                   "print join q{|}, @Config{qw(version archname gccversion dlext)}"],
                  build_dir, env, capture=True)
    if abi != PERL_ABI:
        raise ValueError(f"Unexpected patched Perl ABI: {abi}")
    identity = command([*perl, "-MConfig", "-e", "print join qq(\\n), Config::local_patches()"],
                       build_dir, env, capture=True)
    if PERL_IDENTITY not in identity.splitlines():
        raise ValueError("Compiled Perl lacks the CasaMemo security build identity")
    makefile_options = (f"PERL_LIB={perl_lib.as_posix()}", f"PERL_ARCHLIB={perl_lib.as_posix()}",
                        f"PERL_INC={(perl_lib / 'CORE').as_posix()}")
    build_brotli(brotli, tools, perl, env, jobs, makefile_options)
    # Newer ParseXS generates the fallback overload registration automatically.
    # Remove the old duplicate declaration while retaining the real overloads.
    xs = findfile / "FindFile.xs"
    original = xs.read_text(encoding="ascii")
    declaration = "void\nnil()\n    OVERLOAD: )\n    PPCODE:\n\n"
    if original.count(declaration) != 1:
        raise ValueError("Unexpected Win32::FindFile fallback overload declaration")
    xs.write_bytes(original.replace(declaration, "").encode("ascii"))
    command([*perl, "Makefile.PL", *makefile_options], findfile, env)
    command([*perl, "Makefile.PL", *makefile_options], win32_api, dict(env, PERL_MM_USE_DEFAULT="1"))
    # Build against the same patched zlib source used for FFmpeg.
    zlib_path = zlib.as_posix()
    command([*perl, "Makefile.PL", *makefile_options], zlib_xs,
            dict(env, BUILD_ZLIB="True", ZLIB_INCLUDE=zlib_path, ZLIB_LIB=zlib_path))
    extension_maps = build_dir / "extension-maps"
    extension_maps.mkdir()
    map_flag = f"-Wl,-Map={extension_maps.as_posix()}"
    root = ROOT.as_posix()
    windows_root = root.replace("/", "\\")
    prefix_flags = (f"-ffile-prefix-map={root}=/build", f"-ffile-prefix-map={windows_root}=/build")
    optimize = command([*perl, "-MConfig", "-e", 'print $Config{optimize}'],
                       build_dir, env, capture=True)
    # Native headers can expand __FILE__ with an absolute Windows path.
    # MakeMaker propagates this option to subextensions such as Callback.
    optimize_flags = " ".join((optimize, *prefix_flags))
    for source in (brotli, findfile, zlib_xs, win32_api):
        command([native_tools / "mingw32-make.exe", f"-j{jobs}", f"OTHERLDFLAGS={map_flag}",
                 f"OPTIMIZE={optimize_flags}"], source, env)
    zlib_version = command([*perl, "-Mblib", "-MCompress::Raw::Zlib", "-e",
                            "print Compress::Raw::Zlib::zlib_version()"], zlib_xs, env, capture=True)
    brotli_number = int(command([*perl, "-Mblib", "-MIO::Compress::Brotli", "-e",
                                 "print IO::Compress::Brotli::casamemo_native_version()"],
                                brotli, env, capture=True))
    brotli_version = f"{brotli_number >> 24}.{brotli_number >> 12 & 0xfff}.{brotli_number & 0xfff}"
    if zlib_version != SOURCES["zlib"]["version"] or brotli_version != BROTLI_VERSION:
        raise ValueError(f"Unexpected Perl XS native libraries: Brotli {brotli_version}, zlib {zlib_version}")

    output = work / "exiftool"
    runtime = output / RUNTIME_DIR
    library = runtime / "lib"
    copy(exif / "exiftool", runtime / "exiftool.pl")
    copy_modules(exif / "lib", library, ("Image", "File/RandomAccess.pm"))
    copy(exif / "lib/Image/ExifTool/Geolocation.dat", library / "Image/ExifTool/Geolocation.dat")
    copy(perl_tree / PERL_DLL, runtime / PERL_DLL)
    runtime_dlls = stage_runtime_dlls(cache, runtime)
    copy_modules(perl_lib, library, CORE_MODULES + CORE_XS_FILES)
    copy(perl_lib / WIN32_FILE_DATA, library / WIN32_FILE_DATA)
    sanitize_perl_configuration(library, prefix, recipe)
    copy_modules(win32_api / "blib/lib", library, VENDOR_MODULES[:2])
    copy_modules(win32_api / "blib/arch", library, VENDOR_MODULES[2:])
    for key, source in zip(XS_SOURCES, (brotli, findfile, zlib_xs), strict=True):
        for module in BUILT_XS[key]:
            subdir = "arch" if module.startswith("auto/") else "lib"
            copy(source / "blib" / subdir / module, library / module)

    scripts = ROOT / "scripts"
    resource = build_dir / "launcher.o"
    command([tools / "windres.exe", "-i", scripts / "windows-exiftool-launcher.rc",
             "-o", resource], scripts, env)
    command([tools / "gcc.exe", "-O2", *prefix_flags, "-s", "-municode", "-D_WIN32_WINNT=0x0A00",
             "-Wall", "-Wextra", "-Wno-cast-function-type", scripts / "windows-exiftool-launcher.c",
             resource, map_flag, "-o", output / "exiftool.exe"], build_dir, env)

    for name, source in (("exiftool", exif), ("perl-brotli", brotli), ("perl-findfile", findfile),
                         ("perl-zlib", zlib_xs), ("zlib", zlib)):
        for item in SOURCES[name]["notices"]:
            copy(source / item, output / "licenses" / name / item)
    for item in ("README", "META.json"):
        copy(win32_api / item, output / "licenses/perl-win32-api" / item)
    copy(ROOT / "licenses/ExifTool-Artistic.txt", output / "licenses/exiftool/Artistic")
    for item in ("Artistic", "Copying", "README"):
        copy(perl_tree / item, output / "licenses/perl" / ("Readme" if item == "README" else item))
    copy(perl_tree / "cpan/Compress-Raw-Bzip2/bzip2-src/LICENSE", output / "licenses/perl/bzip2-LICENSE")
    for name in ("COPYING.RUNTIME", "COPYING3", "COPYING.MinGW-w64-runtime.txt", "COPYING.winpthreads"):
        copy(work / "metadata/windows-notices" / name, output / "licenses/msys2" / name)

    imports = dependency_report(output, tools / "objdump.exe", env)
    link_inputs, linkage = record_linkage(imports, prefix, perl_tree, recipe / "link-maps",
                                         extension_maps, brotli)
    compiler_config = command([*perl, "-MConfig", "-e",
                               'print "$_=$Config{$_}\\n" for qw(cc ld ccflags optimize ldflags)'],
                              build_dir, env, capture=True)
    result = {"perlAbi": abi, "perlIdentity": PERL_IDENTITY,
              "securityPatches": [SOURCES[name]["sha256"] for name in PERL_PATCHES],
              "perlCompiler": redact_build_paths(compiler_config, prefix, recipe).splitlines(),
              "compiledRegex": {name: sha256(perl_tree / name)
                                for name in ("regexec.c", "regexp.h", "regexec.o")},
              "nativeVersions": {"brotli": brotli_version, "zlib": zlib_version},
              "peImports": imports, "runtimeDlls": runtime_dlls,
              "linkInputs": link_inputs, "linkage": linkage, "members": {
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
            tarfile.TarError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
