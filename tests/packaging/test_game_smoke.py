import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import miplay_game_smoke as smoke


class GameCopyTests(unittest.TestCase):
    def test_cow_copy_has_distinct_inode_and_independent_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            (source / 'game.exe').write_bytes(b'original')
            destination = root / 'owned' / 'game'
            (root / 'owned').mkdir()
            with patch.object(smoke, 'STATE', root / 'owned'):
                smoke.clone_game(source, destination)
                self.assertNotEqual((source / 'game.exe').stat().st_ino, (destination / 'game.exe').stat().st_ino)
                (destination / 'game.exe').write_bytes(b'candidate')
                self.assertEqual((source / 'game.exe').read_bytes(), b'original')
                with self.assertRaises(ValueError):
                    smoke.clone_game(source, destination)

    def test_symlinks_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            (source / 'escape').symlink_to(root)
            with patch.object(smoke, 'STATE', root):
                with self.assertRaises(ValueError):
                    smoke.clone_game(source, root / 'copy')
            self.assertFalse((root / 'copy').exists())

    def test_destination_outside_owned_state_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'source').mkdir()
            (root / 'owned').mkdir()
            with patch.object(smoke, 'STATE', root / 'owned'):
                with self.assertRaises(ValueError):
                    smoke.clone_game(root / 'source', root / 'outside')
            self.assertFalse((root / 'outside').exists())
