"""Build CasaMemo's native Perl from the pinned MSYS2 source recipe."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

from inputs import ROOT, SOURCES, require_hash, sha256, source_archive, source_tree

PERL_VERSION = "5.44.0"
PERL_DLL = "perl544.dll"
PERL_IDENTITY = "CasaMemo MSYS2 UCRT64 r1 (CVE-2026-15534)"
PERL_ABI = f"{PERL_VERSION}|MSWin32-x64-multi-thread|16.2.0|dll"
PERL_PATCHES = ("perl-regex-prerequisite", "perl-regex-fix")
PERL_RUNTIME_PACKAGES = ("msys2-libgcc", "msys2-libstdc++", "msys2-libwinpthread")
PERL_BUILD_INPUTS = ("msys2-native-make", *PERL_RUNTIME_PACKAGES)


def msys_tool(name):
    # Use the active shell's cygpath to locate MSYS2. Native CreateProcess
    # can find System32's Bash before executables on PATH.
    cygpath = shutil.which("cygpath.exe")
    if cygpath:
        bin_dir = Path(cygpath).resolve().parent
        if (bin_dir.name.lower() == "bin" and bin_dir.parent.name.lower() == "usr"
                and (bin_dir / "msys-2.0.dll").is_file() and (bin_dir / "pacman.exe").is_file()):
            executable = (bin_dir / name).resolve()
            if executable.parent == bin_dir and executable.is_file():
                return executable
    raise ValueError(f"Could not resolve MSYS2 /usr/bin/{name} from cygpath.exe on PATH. "
                     "Run the Windows build from the intended MSYS2 UCRT64 shell.")


def ucrt_prefix():
    if os.environ.get("MSYSTEM") != "UCRT64":
        raise ValueError("The Windows Perl build requires the native MSYS2 UCRT64 shell")
    prefix = subprocess.check_output([msys_tool("cygpath.exe"), "-m", "/ucrt64"], text=True).strip()
    return Path(prefix).resolve()


def msys_path(path, cygpath):
    return subprocess.check_output([cygpath, "-u", str(path)], text=True).strip()


def stage_recipe(key, cache, work, filename):
    recipe = source_tree(key, cache, work)
    source = recipe / filename
    require_hash(source, SOURCES[key]["upstreamSha256"])
    with tarfile.open(source, "r:*") as archive:
        nested_root = filename.rsplit(".tar.", 1)[0]
        for member in archive.getmembers():
            if (member.name.split("/", 1)[0] != nested_root or "\\" in member.name or ":" in member.name
                    or set(member.name.split("/")) & {"", ".", ".."}
                    or not (member.isfile() or member.isdir())):
                raise ValueError(f"Unexpected entry in the pinned source archive {source.name}")
        archive.extractall(recipe, filter="data")
    return recipe


def extract_package_file(archive, name, target):
    with tarfile.open(archive, "r:*") as package:
        member = package.getmember(name)
        if not member.isfile():
            raise ValueError(f"Expected a regular file in {archive.name}: {name}")
        with package.extractfile(member) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)


def stage_perl(cache, work):
    recipe = stage_recipe("msys2-perl", cache, work, f"perl-{PERL_VERSION}.tar.xz")
    native_tools = work / "native-tools"
    native_tools.mkdir()
    extract_package_file(source_archive("msys2-native-make", cache, download=True),
                         "ucrt64/bin/mingw32-make.exe", native_tools / "mingw32-make.exe")
    patches = [source_archive(name, cache, download=True) for name in PERL_PATCHES]
    return recipe, native_tools, patches


def compile_perl(recipe, native_tools, patches, jobs):
    bash = msys_tool("bash.exe")
    cygpath = msys_tool("cygpath.exe")
    arguments = [ROOT / "scripts/build-windows-perl.sh", recipe, *patches, native_tools]
    subprocess.run([bash, *(msys_path(path, cygpath) for path in arguments), str(jobs)], check=True)
    return recipe / "build-UCRT64"


def stage_runtime_dlls(cache, destination):
    receipts = {}
    for package in PERL_RUNTIME_PACKAGES:
        pin = SOURCES[package]
        source_pin = SOURCES[pin["source"]]
        binary_archive = source_archive(package, cache, download=True)
        source_path = source_archive(pin["source"], cache, download=True)
        directory = source_pin["file"].removesuffix(f"-{source_pin['version']}.src.tar.zst")
        with tarfile.open(source_path, "r:*") as source:
            with source.extractfile(f"{directory}/PKGBUILD") as recipe:
                recipe_hash = hashlib.file_digest(recipe, "sha256").hexdigest()
        with tarfile.open(binary_archive, "r:*") as binary:
            info = dict(line.split(" = ", 1) for line in binary.extractfile(".BUILDINFO")
                        .read().decode("utf-8").splitlines())
            if info.get("pkgbuild_sha256sum") != recipe_hash or recipe_hash != pin["recipeSha256"]:
                raise ValueError(f"Source recipe does not match the signed MSYS2 binary package: {package}")
        dll = destination / pin["member"]
        extract_package_file(binary_archive, f"ucrt64/bin/{dll.name}", dll)
        require_hash(dll, pin["memberSha256"])
        receipts[dll.name] = {"package": package, "sha256": sha256(dll), "recipeSha256": recipe_hash}
    return receipts
