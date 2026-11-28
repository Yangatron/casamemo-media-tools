from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import artifacts
from artifacts import archive_zip, provisioning, verify_zip
from inputs import require_hash, sha256
import windows_perl


class MsysToolsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.msys = self.root / "MSYS2 tools" / "usr/bin"
        self.msys.mkdir(parents=True)
        for name in ("cygpath.exe", "bash.exe", "msys-2.0.dll", "pacman.exe"):
            (self.msys / name).touch(mode=0o755)

    def test_perl_launch_uses_msys2_bash_and_converts_all_paths(self):
        system = self.root / "System32"
        system.mkdir()
        (system / "bash.exe").touch(mode=0o755)
        recipe, patches, tools = self.root / "recipe", [self.root / "fix.patch"], self.root / "tools"
        arguments = [windows_perl.ROOT / "scripts/build-windows-perl.sh", recipe, *patches, tools]
        converted = ["/build/build-windows-perl.sh", "/build/recipe", "/build/fix.patch", "/build/tools"]
        with patch.dict(os.environ, PATH=os.pathsep.join(map(str, (system, self.msys))), MSYSTEM="UCRT64"):
            with patch.object(windows_perl.subprocess, "check_output",
                              side_effect=[path + "\n" for path in converted]) as convert:
                with patch.object(windows_perl.subprocess, "run") as run:
                    self.assertEqual(windows_perl.compile_perl(recipe, tools, patches, 4), recipe / "build-UCRT64")
        self.assertEqual(convert.call_args_list, [
            call([self.msys / "cygpath.exe", "-u", str(path)], text=True) for path in arguments
        ])
        run.assert_called_once_with([self.msys / "bash.exe", *converted, "4"], check=True)

    def test_missing_msys2_bash_fails_before_launch_even_with_a_path_fallback(self):
        (self.msys / "bash.exe").unlink()
        other = self.root / "other"
        other.mkdir()
        (other / "bash.exe").touch(mode=0o755)
        with patch.dict(os.environ, PATH=os.pathsep.join(map(str, (other, self.msys)))):
            with patch.object(windows_perl.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, r"Could not resolve MSYS2 /usr/bin/bash\.exe.*UCRT64"):
                    windows_perl.compile_perl(self.root, self.root, (), 4)
        run.assert_not_called()

    def test_non_msys2_cygpath_is_rejected(self):
        (self.msys / "pacman.exe").unlink()
        with patch.dict(os.environ, PATH=str(self.msys)):
            with self.assertRaisesRegex(ValueError, r"Could not resolve MSYS2 /usr/bin/bash\.exe"):
                windows_perl.msys_tool("bash.exe")


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)

    def test_checksum_rejects_changed_bytes(self):
        sample = self.work / "sample"
        sample.write_bytes(b"original")
        checksum = sha256(sample)
        require_hash(sample, checksum)
        sample.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            require_hash(sample, checksum)

    def test_zip_is_stable_across_input_order(self):
        item = self.work / "item"
        item.write_bytes(b"binary")
        first, second = self.work / "first.zip", self.work / "second.zip"
        members = [("bin/ffprobe", item, 0o755), ("bin/ffmpeg", item, 0o755)]
        archive_zip(first, members)
        archive_zip(second, reversed(members))
        verify_zip(first)
        self.assertEqual(sha256(first), sha256(second))

    def test_archive_rejects_paths_that_escape_extraction_root(self):
        package = self.work / "malformed.zip"
        sample = self.work / "sample"
        sample.write_bytes(b"archive traversal fixture")
        archive_zip(package, [("../elsewhere", sample, 0o644)])
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP member"):
            verify_zip(package)

    def test_archive_rejects_case_collisions_and_symlinks(self):
        sample = self.work / "sample"
        sample.write_bytes(b"file")
        collision = self.work / "collision.zip"
        archive_zip(collision, [("bin/ffmpeg", sample, 0o755), ("bin/FFMPEG", sample, 0o755)])
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP member"):
            verify_zip(collision)
        symlink = self.work / "symlink.zip"
        with ZipFile(symlink, "w") as archive:
            entry = ZipInfo("bin/ffmpeg")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "elsewhere")
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP member"):
            verify_zip(symlink)

    def test_windows_exiftool_has_its_own_zip(self):
        windows = provisioning("windows-x64", "r1")
        self.assertEqual(windows["exiftool"]["asset"], "casamemo-exiftool-13.64-windows-x64-r1.zip")
        self.assertEqual(windows["exiftool"]["checksumTarget"], "archive")
        self.assertIsNone(windows["ffprobe"])

    def test_macos_has_separate_ffprobe_at_the_same_version(self):
        for platform in ("macos-arm64", "macos-x64"):
            tools = provisioning(platform, "r1")
            self.assertNotEqual(tools["ffmpeg"]["asset"], tools["ffprobe"]["asset"])
            self.assertEqual(tools["ffmpeg"]["version"], tools["ffprobe"]["version"])
            self.assertEqual(tools["ffprobe"]["checksumTarget"], "archive")


    def test_recipe_excludes_local_and_unapproved_files(self):
        scripts = self.work / "scripts"
        scripts.mkdir()
        (scripts / "build.sh").write_text("build instructions")
        (scripts / "signing.p12").write_text("synthetic local signing material")
        (scripts / "private.md").write_text("synthetic unapproved file")
        with patch.multiple(artifacts, ROOT=self.work, RECIPE_PATHS=("scripts/build.sh",)):
            package = self.work / "source.zip"
            archive_zip(package, artifacts.recipe_files())
            with ZipFile(package) as archive:
                self.assertEqual(archive.namelist(), ["recipe/scripts/build.sh"])

    def test_recipe_rejects_ignored_approved_path(self):
        (self.work / ".git").mkdir()
        ignored = subprocess.CompletedProcess([], returncode=0, stdout=b"scripts/build.sh")
        with patch.multiple(artifacts, ROOT=self.work, RECIPE_PATHS=("scripts/build.sh",)):
            with patch.object(artifacts.subprocess, "run", return_value=ignored) as git:
                with self.assertRaisesRegex(ValueError, "ignored by Git"):
                    artifacts.recipe_files()
                self.assertIn("--no-index", git.call_args.args[0])

    def test_recipe_requires_git_in_checkout(self):
        (self.work / ".git").mkdir()
        with patch.object(artifacts, "ROOT", self.work):
            with patch.object(artifacts.subprocess, "run", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(ValueError, "Git executable not found on PATH"):
                    artifacts.recipe_files()

    def test_public_input_rejects_an_escaped_local_windows_path(self):
        sample = self.work / "disclosure.json"
        private_path = self.work.as_posix().replace("/", "\\\\").upper()
        sample.write_text(private_path, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "local build path"):
            artifacts.require_public_binary(sample, self.work)

    def test_recipe_rejects_symlinked_file_or_directory(self):
        outside = self.work / "outside"
        outside.mkdir()
        (outside / "build.sh").write_text("synthetic private file")
        for directory_link in (True, False):
            staged = self.work / str(directory_link)
            staged.mkdir()
            try:
                if directory_link:
                    (staged / "scripts").symlink_to(outside, target_is_directory=True)
                else:
                    (staged / "scripts").mkdir()
                    (staged / "scripts" / "build.sh").symlink_to(outside / "build.sh")
            except OSError:
                self.skipTest("Local symlink creation is unavailable")
            with self.subTest(directory_link=directory_link):
                with patch.multiple(artifacts, ROOT=staged, RECIPE_PATHS=("scripts/build.sh",)):
                    with self.assertRaisesRegex(ValueError, "Unsafe archive input"):
                        artifacts.recipe_files()

    def test_verify_rejects_missing_inventory_after_reindexing(self):
        sample = self.work / "sample"
        sample.write_bytes(b"placeholder payload")
        platform, revision = "windows-x64", "r1"
        runtime, _, exiftool, sources = artifacts.layout(platform, revision)
        records = artifacts.notice_names() | artifacts.build_record_names(platform)
        source_records = records | artifacts.EXIFTOOL_RECORDS
        upstream = {f"upstream/{artifacts.SOURCES[name]['file']}" for name in artifacts.source_inputs(platform)}
        recipe = {f"recipe/{name}" for name in artifacts.RECIPE_PATHS}
        bins = {f"bin/{name}" for name in artifacts.binary_names(platform)}
        missing_cases = (
            ("licenses/ffmpeg/COPYING.LGPLv2.1", True, True),
            ("build/toolchain.txt", True, True),
            ("build/windows-notices/COPYING.winpthreads", True, True),
            ("recipe/scripts/build.sh", True, False),
            ("recipe/scripts/build-windows-perl.sh", True, False),
            (f"upstream/{artifacts.SOURCES['msys2-perl']['file']}", True, False),
            (f"upstream/{artifacts.SOURCES['msys2-perl-win32-api']['file']}", True, False),
            (f"upstream/{artifacts.SOURCES['msys2-mingw-recipes-license']['file']}", True, False),
            (f"upstream/{artifacts.SOURCES['perl-regex-fix']['file']}", True, False),
            ("licenses/perl/Third-Party.txt", True, False),
            (min(upstream), True, False),
            ("licenses/libwebp/PATENTS", False, True),
        )
        for i, (missing, omit_source, omit_runtime) in enumerate(missing_cases):
            with self.subTest(missing=missing):
                folder = self.work / str(i)
                folder.mkdir()
                archive_zip(folder / sources, [(name, sample, 0o644)
                            for name in source_records | upstream | recipe
                            if name != missing or not omit_source])
                archive_zip(folder / runtime, [(name, sample, 0o755 if name in bins else 0o644)
                            for name in records | bins if name != missing or not omit_runtime])
                archive_zip(folder / exiftool, [("placeholder", sample, 0o644)])
                artifacts.index(folder, platform, revision, "ci-candidate")
                with self.assertRaisesRegex(ValueError, "Missing required archive member:") as error:
                    artifacts.verify(folder)
                self.assertIn(missing, str(error.exception))

    def test_windows_exiftool_inventory_rejects_extra_files_and_traversal(self):
        required = dict.fromkeys(artifacts.EXIFTOOL_REQUIRED, "0" * 64)
        artifacts.validate_exiftool_inventory(required)
        for name in ("exiftool_files/perl.exe", "exiftool_files/lib/../private.pm"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Windows ExifTool member"):
                artifacts.validate_exiftool_inventory({**required, name: "0" * 64})
        with self.assertRaisesRegex(ValueError, "Unexpected Windows ExifTool native binary inventory"):
            artifacts.validate_exiftool_inventory(
                {**required, "exiftool_files/lib/auto/Unknown/Unknown.dll": "0" * 64})

    def test_verify_rejects_modified_perl_source_after_reindexing(self):
        sample = self.work / "member"
        sample.write_bytes(b"substitute source bytes")
        platform, revision = "windows-x64", "r1"
        runtime, _, exiftool, sources = artifacts.layout(platform, revision)
        records = artifacts.notice_names() | artifacts.build_record_names(platform)
        bins = {f"bin/{name}" for name in artifacts.binary_names(platform)}
        dependencies = artifacts.source_inputs(platform)
        locked = {**artifacts.SOURCES, **{
            name: {**artifacts.SOURCES[name], "sha256": sha256(sample)}
            for name in dependencies if name != "msys2-perl"
        }}
        upstream = {f"upstream/{locked[name]['file']}" for name in dependencies}
        recipe = {f"recipe/{name}" for name in artifacts.RECIPE_PATHS}
        source_members = records | artifacts.EXIFTOOL_RECORDS | upstream | recipe
        archive_zip(self.work / sources, [(name, sample, 0o644) for name in source_members])
        archive_zip(self.work / runtime, [(name, sample, 0o755) for name in records | bins])
        archive_zip(self.work / exiftool, [("placeholder", sample, 0o644)])
        with patch.object(artifacts, "SOURCES", locked), patch.object(artifacts, "validate_config"):
            artifacts.index(self.work, platform, revision, "ci-candidate")
            with self.assertRaisesRegex(ValueError, "Corresponding source mismatch: msys2-perl"):
                artifacts.verify(self.work)

    def test_windows_build_record_rejects_bad_runtime_and_link_provenance(self):
        dlls = {
            name: {"package": package, "sha256": artifacts.SOURCES[package]["memberSha256"],
                   "recipeSha256": artifacts.SOURCES[package]["recipeSha256"]}
            for name, package in artifacts.RUNTIME_DLL_OWNERS.items()
        }
        members = {f"exiftool_files/{name}": data["sha256"] for name, data in dlls.items()}
        imports = {name: ["kernel32.dll"] for name in artifacts.NATIVE_FILES}
        inputs = {"ucrt64/lib/libgcc.a": {"owner": "gcc", "sha256": "0" * 64},
                  "ucrt64/lib/crt2.o": {"owner": "crt", "sha256": "0" * 64}}
        local = {name: {"owner": spec[0], "sha256": "0" * 64}
                 for name, spec in artifacts.LOCAL_LINK_ARCHIVES.items()}
        record = {
            "perlAbi": artifacts.PERL_ABI, "perlIdentity": artifacts.PERL_IDENTITY,
            "securityPatches": [artifacts.SOURCES[name]["sha256"] for name in artifacts.PERL_PATCHES],
            "compiledRegex": dict.fromkeys(("regexec.c", "regexp.h", "regexec.o"), "0" * 64),
            "perlCompiler": ["cc=gcc", "ld=g++", "ccflags=flags", "optimize=-Os", "ldflags=-s"],
            "nativeVersions": {"brotli": artifacts.BROTLI_VERSION, "zlib": artifacts.SOURCES["zlib"]["version"]},
            "members": members, "peImports": imports, "runtimeDlls": dlls, "linkInputs": inputs | local,
            "linkage": {name: {item: ["test.o"] for item in inputs.keys() | artifacts.required_local_archives(name)}
                        for name in artifacts.NATIVE_FILES - members.keys()},
        }
        artifacts.validate_windows_build(record)
        with self.assertRaisesRegex(ValueError, "MSYS2 DLL mismatch: libstdc"):
            artifacts.validate_windows_build(
                {**record, "members": {**members, "exiftool_files/libstdc++-6.dll": "0" * 64}})
        with self.assertRaisesRegex(ValueError, "Unexpected Windows ExifTool PE dependency"):
            artifacts.validate_windows_build(
                {**record, "peImports": {**imports, "exiftool.exe": ["msys-2.0.dll"]}})
        with self.assertRaisesRegex(ValueError, "Unreviewed Windows ExifTool link input"):
            artifacts.validate_windows_build(
                {**record, "linkInputs": {**record["linkInputs"], "ucrt64/lib/libforeign.a":
                                            {"owner": "foreign", "sha256": "0" * 64}}})

    def test_windows_exiftool_requires_shared_notice(self):
        placeholder = self.work / "placeholder"
        placeholder.write_bytes(b"placeholder")
        record = self.work / "exiftool.json"
        entries = dict.fromkeys(artifacts.EXIFTOOL_REQUIRED, sha256(placeholder))
        record.write_text(json.dumps({
            "members": entries,
            "perlAbi": "5.42.3|MSWin32-x64-multi-thread|13.2.0|xs.dll",
            "perlZlib": artifacts.SOURCES["zlib"]["version"],
            "peImports": {name: [] for name in entries if name.endswith((".exe", ".dll"))},
        }), encoding="utf-8")
        exe_and_records = [(name, placeholder, 0o755) for name in entries]
        exe_and_records.append((artifacts.RUNTIME_BUILD, record, 0o644))
        archive = self.work / "exiftool.zip"
        archive_zip(archive, exe_and_records)
        with self.assertRaisesRegex(ValueError, "Missing required archive member: licenses/THIRD_PARTY"):
            artifacts.verify_windows_exiftool(archive, None)

    def test_windows_release_index_is_withheld(self):
        with self.assertRaisesRegex(ValueError, "redistribution review"):
            artifacts.index(self.work, "windows-x64", "r1", "owner-finalized")
        self.assertFalse((self.work / "artifacts.json").exists())


if __name__ == "__main__":
    unittest.main()
