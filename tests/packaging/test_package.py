import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from miplay_package import FILES, package, sha256, verify
from miplay_build import check_dependencies
from unittest.mock import patch


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.install = self.root / "install"
        for name, relative in FILES.items():
            path = self.install / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            data = bytearray(128)
            if name.endswith(".dll"):
                data[:2] = b"MZ"
                struct.pack_into("<I", data, 60, 64)
                data[64:68] = b"PE\0\0"
                struct.pack_into("<H", data, 68, 0x8664)
                struct.pack_into("<H", data, 86, 0x2000)
                struct.pack_into("<H", data, 88, 0x20B)
            else:
                data[:4] = b"\xcf\xfa\xed\xfe"
                struct.pack_into("<I", data, 4, 0x01000007)
                struct.pack_into("<I", data, 12, 6)
            path.write_bytes(data)

    def tearDown(self):
        self.temporary.cleanup()

    def create(self, output="candidate"):
        return package(self.install, self.root / output, {"source_date_epoch": "12345"})

    def test_complete_package_and_deterministic_archive(self):
        output = self.create()
        self.assertEqual(set(verify(output)["files"]), set(FILES))
        # Identical input and package name in another directory produce the same archive.
        other = self.root / "other/candidate"
        package(self.install, other, {"source_date_epoch": "12345"})
        self.assertEqual(sha256(str(output) + ".tar.gz"), sha256(str(other) + ".tar.gz"))

    def test_optional_bootstrap_is_packaged_and_integrity_checked(self):
        helper = self.install / "integration/dxmt-cache-bootstrap.dylib"
        helper.parent.mkdir()
        helper.write_bytes((self.install / FILES["winemetal.so"]).read_bytes())
        output = self.create()
        self.assertEqual(set(verify(output)["integration_files"]), {helper.name})
        (output / "integration" / helper.name).write_bytes(b"corrupted")
        with self.assertRaises(ValueError):
            verify(output)

    def test_missing_component_is_not_published(self):
        (self.install / FILES["winemetal.so"]).unlink()
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse((self.root / "candidate").exists())

    def test_wrong_architecture_is_rejected(self):
        path = self.install / FILES["d3d11.dll"]
        data = bytearray(path.read_bytes())
        struct.pack_into("<H", data, 68, 0xAA64)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "x86_64"):
            self.create()

    def test_tampered_component_and_manifest_are_detected(self):
        output = self.create()
        binary = output / "dxmt/dxgi.dll"
        binary.write_bytes(binary.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            verify(output)
        output = self.create("manifest-candidate")
        manifest = output / "manifest.json"
        data = json.loads(manifest.read_text())
        data["status"] = "different"
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify(output)

    def test_existing_package_is_preserved(self):
        output = self.create()
        before = sha256(output / "manifest.json")
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(before, sha256(output / "manifest.json"))

    def test_dependency_gate_rejects_toolchain_dylibs(self):
        with patch("miplay_build.capture", return_value="file:\n @rpath/winemetal.so (id)\n /usr/lib/libc++.1.dylib (version)"):
            self.assertEqual(check_dependencies(Path("file")), ["/usr/lib/libc++.1.dylib"])
        with patch("miplay_build.capture", return_value="file:\n @rpath/winemetal.so (id)\n @rpath/libc++.1.dylib (version)"):
            with self.assertRaises(ValueError):
                check_dependencies(Path("file"))


if __name__ == "__main__":
    unittest.main()
