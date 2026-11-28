from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import artifacts
from artifacts import archive_zip, provisioning, verify_zip
from inputs import require_hash, sha256


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
            (f"recipe/{artifacts.WINLIBS_EVIDENCE_PATH}", True, False),
            (f"upstream/{artifacts.SOURCES['winlibs-recipes']['file']}", True, False),
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
        xs = "exiftool_files/lib/auto/Compress/Raw/Bzip2/Bzip2.xs.dll"
        artifacts.validate_exiftool_inventory({**required, xs: "0" * 64})
        for name in ("exiftool_files/perl.exe", "exiftool_files/lib/../private.pm"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Windows ExifTool member"):
                artifacts.validate_exiftool_inventory({**required, name: "0" * 64})

    def test_windows_winlibs_provenance_rejects_changed_dll_or_link_input(self):
        evidence = artifacts.winlibs_evidence()
        members = {f"exiftool_files/{name}": digest
                   for name, digest in evidence["runtimeDllSha256"].items()}
        files = [Path(name).name for name in evidence["linkInputSha256"]]
        objects = {name: files.copy() for name in ("brotli", "findfile", "launcher", "zlib")}
        record = {"members": members, "winlibsLinkedObjects": objects}
        artifacts.validate_winlibs_provenance(record, evidence)
        with self.assertRaisesRegex(ValueError, "WinLibs r8 DLL mismatch: libstdc"):
            artifacts.validate_winlibs_provenance(
                {**record, "members": {**members, "exiftool_files/libstdc++-6.dll": "0" * 64}},
                evidence)
        objects["launcher"].append("libunreviewed.a(runtime.o)")
        with self.assertRaisesRegex(ValueError, "link inputs differ"):
            artifacts.validate_winlibs_provenance(record, evidence)

    def test_windows_exiftool_requires_shared_notice_and_matching_source_evidence(self):
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

        archive = self.work / "exiftool-with-notice.zip"
        archive_zip(archive, exe_and_records + [(name, placeholder, 0o644)
                    for name in artifacts.EXIFTOOL_PACKAGE_NOTICES])
        source_evidence = self.work / "evidence.json"
        source_evidence.write_text("{}", encoding="utf-8")
        source = self.work / "source.zip"
        archive_zip(source, [(f"recipe/{artifacts.WINLIBS_EVIDENCE_PATH}", source_evidence, 0o644)])
        with ZipFile(source) as sources:
            with self.assertRaisesRegex(ValueError, "WinLibs evidence differs"):
                artifacts.verify_windows_exiftool(archive, sources)

    def test_windows_release_index_is_withheld(self):
        with self.assertRaisesRegex(ValueError, "redistribution review"):
            artifacts.index(self.work, "windows-x64", "r1", "owner-finalized")
        self.assertFalse((self.work / "artifacts.json").exists())


if __name__ == "__main__":
    unittest.main()
