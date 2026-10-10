from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import miplay_local_testing as local


class LocalIsolationTests(unittest.TestCase):
    def setUp(self):
        build = Path(__file__).resolve().parents[2] / "build"
        build.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="isolation-test-", dir=build)
        self.base = Path(self.temp.name)
        self.area = self.base / ".local-testing"
        self.area.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_descendant_of_external_symlink_is_rejected(self):
        external = self.base / "external-probe"
        external.mkdir()
        link = self.area / "link"
        link.symlink_to(external, target_is_directory=True)
        with self.assertRaises(ValueError):
            local.owned(link / "not-yet-created/file", boundary=self.area)
        self.assertFalse((external / "not-yet-created").exists())

    def test_another_component_and_sibling_roots_are_rejected(self):
        root = self.area / "state-dxmt"
        root.mkdir()
        with self.assertRaises(ValueError):
            local.owned(self.area / "state-lsfg/file", boundary=root)
        with self.assertRaises(ValueError):
            local.owned(self.area / "state-dxmt-sibling/file", boundary=root)
        self.assertEqual(local.owned(root / "new/file", boundary=root), root / "new/file")

    def test_production_profile_cannot_be_launched(self):
        clone = self.area / "MiPlay-DXMT"
        project = clone / "MiPlay.xcodeproj/project.pbxproj"
        project.parent.mkdir(parents=True)
        project.write_text("PRODUCT_BUNDLE_IDENTIFIER = SteveTan.MiPlay;")
        with patch.object(local, "CLONE", clone):
            with self.assertRaises(ValueError):
                local.profile_ready()
        project.write_text("MIPLAY_DXMT_TESTING\nPRODUCT_BUNDLE_IDENTIFIER = SteveTan.MiPlay.DXMTTesting;")
        with patch.object(local, "CLONE", clone):
            local.profile_ready()

    def test_patch_export_refuses_uncommitted_changes(self):
        with patch.object(local, "git", return_value=" M user-change.swift"):
            with self.assertRaises(ValueError):
                local.export()

    def test_candidate_switch_refuses_busy_state_and_preserves_backup(self):
        clone = self.area / "MiPlay-DXMT"
        (clone / "RuntimeAssets/protonextras").mkdir(parents=True)
        candidates = []
        for label in ("first", "second"):
            path = self.base / label
            (path / "dxmt").mkdir(parents=True)
            (path / "dxmt/dxgi.dll").write_bytes(b"DXMT_METAL_CACHE_PATH DXMT_REQUIRE_ISOLATED_CACHE")
            (path / "manifest.json").write_text(json.dumps({"files": {"identity": "same-renderer"}, "integration_files": {"helper": label}, "source": {"commit": label}}))
            candidates.append(path)
        def fake_verify(path):
            return json.loads((path / "manifest.json").read_text())
        state = self.area / "state-dxmt"
        with patch.object(local, "AREA", self.area), patch.object(local, "STATE", state), patch.object(local, "CLONE", clone), \
             patch.object(local, "verify", side_effect=fake_verify), patch.object(local, "git", return_value="test-head"):
            local.prepare(candidates[0])
            with self.assertRaises(ValueError):
                local.prepare(candidates[1])
            with patch.object(local, "assert_idle", side_effect=ValueError("busy")):
                with self.assertRaises(ValueError):
                    local.prepare(candidates[1], replace=True)
            self.assertEqual(fake_verify(state / "Candidate")["source"]["commit"], "first")
            with patch.object(local, "assert_idle"):
                local.prepare(candidates[1], replace=True)
            self.assertEqual(fake_verify(state / "Candidate")["source"]["commit"], "second")
            backup = next((state / "ArchivedCandidates").iterdir())
            self.assertEqual(fake_verify(backup)["source"]["commit"], "first")


if __name__ == "__main__":
    unittest.main()
