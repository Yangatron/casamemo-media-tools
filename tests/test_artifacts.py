from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

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

    def test_windows_exiftool_has_no_distribution_filename(self):
        windows = provisioning("windows-x64", "r1")
        self.assertIsNone(windows["exiftool"])
        self.assertIsNone(windows["ffprobe"])

    def test_macos_has_separate_ffprobe_at_the_same_version(self):
        for platform in ("macos-arm64", "macos-x64"):
            tools = provisioning(platform, "r1")
            self.assertNotEqual(tools["ffmpeg"]["asset"], tools["ffprobe"]["asset"])
            self.assertEqual(tools["ffmpeg"]["version"], tools["ffprobe"]["version"])
            self.assertEqual(tools["ffprobe"]["checksumTarget"], "archive")


if __name__ == "__main__":
    unittest.main()
