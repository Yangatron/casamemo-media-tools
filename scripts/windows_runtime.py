"""Verify the MSYS2 FFmpeg toolchain and record the owners of its linked objects."""

import argparse
from pathlib import Path
import re
import subprocess
import sys

from inputs import SOURCES

PREFIX = "mingw-w64-ucrt-x86_64-"
SOURCE_PACKAGES = {
    "gcc": "msys2-gcc", "libgcc": "msys2-gcc", "libstdc++": "msys2-gcc",
    "crt": "msys2-crt", "headers": "msys2-crt",
    "winpthreads": "msys2-winpthreads", "libwinpthread": "msys2-winpthreads",
    "windows-default-manifest": "msys2-default-manifest",
}


def command(*arguments):
    return subprocess.run(arguments, check=True, stdout=subprocess.PIPE, text=True).stdout


def check_packages():
    expected = {PREFIX + package: SOURCES[source]["version"]
                for package, source in SOURCE_PACKAGES.items()}
    actual = dict(line.split() for line in command("pacman", "-Q", *expected).splitlines())
    if actual != expected:
        changes = [f"{name} is {actual.get(name)}, expected {version}"
                   for name, version in expected.items() if actual.get(name) != version]
        raise ValueError("MSYS2 toolchain does not match the pinned source: " + "; ".join(changes))


def linked_objects(map_file, prefix):
    contents = map_file.read_text(encoding="utf-8", errors="replace")
    members = re.findall(r"^(.+?\.a)\(([^)]+)\)(?:\s|$)", contents, re.MULTILINE)
    result = set()
    for path, member in members:
        archive = Path(path)
        if archive.is_absolute():
            archive = archive.resolve()
            if archive.is_relative_to(prefix):
                result.add((archive, f"{archive.name}({Path(member).name})"))
    for path in re.findall(r"^LOAD (.+?\.o)$", contents, re.MULTILINE):
        obj = Path(path)
        if obj.is_absolute():
            obj = obj.resolve()
            if obj.is_relative_to(prefix):
                result.add((obj, obj.name))
    if not result:
        raise ValueError(f"No toolchain runtime objects found in {map_file.name}")
    return result


def linkage(map_file, prefix):
    result = linked_objects(map_file, prefix)
    owners = {}
    for path in sorted({path for path, _ in result}):
        package = command("pacman", "-Qqo", path.as_posix()).strip()
        if not package.startswith(PREFIX):
            raise ValueError(f"Unexpected owner for {path.name}: {package}")
        name = package.removeprefix(PREFIX)
        if name not in SOURCE_PACKAGES:
            raise ValueError(f"Missing source pin for MSYS2 runtime package {name}")
        owners[path] = name
    if not {"msys2-gcc", "msys2-crt"} <= {SOURCE_PACKAGES[name] for name in owners.values()}:
        raise ValueError(f"Incomplete GCC/CRT runtime objects in {map_file.name}")
    return sorted({f"{owners[path]} {member}" for path, member in result})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("maps", type=Path, nargs="*")
    args = parser.parse_args()
    try:
        check_packages()
        if args.report:
            prefix = Path(command("cygpath", "-m", "/ucrt64").strip()).resolve()
            lines = []
            for path in args.maps:
                lines.extend((path.stem, *linkage(path, prefix), ""))
            args.report.write_text("\n".join(lines), encoding="utf-8")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
