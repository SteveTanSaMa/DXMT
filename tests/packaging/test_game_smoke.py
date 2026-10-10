import sys
import json
from types import SimpleNamespace
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

    def test_owned_run_never_reads_formal_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp)
            state = area / 'state-dxmt'
            game = state / 'Games/ZenlessZoneZero'
            game.mkdir(parents=True)
            executable = game / 'ZenlessZoneZero.exe'
            executable.write_bytes(b'fixture')
            (state / 'Config').mkdir()
            (state / 'Candidate').mkdir()
            (state / 'Candidate/manifest.json').write_text('{}')
            (state / 'runtime-origin.json').write_text('{}')
            marker = {'source': '/DO-NOT-ACCESS/formal-game', 'files': {'ZenlessZoneZero.exe': [0, 7, 0]},
                      'executable_sha256': smoke.sha256(executable)}
            (state / 'Config/game-copy-ZenlessZoneZero.json').write_text(json.dumps(marker))
            (state / 'Logs').mkdir()
            (area / 'results-dxmt').mkdir()
            inventory = smoke.inventory
            owned = smoke.owned
            def owned_inventory(path):
                self.assertTrue(path.is_relative_to(state))
                return inventory(path)
            def run(command, **kwargs):
                if command[0] == 'xcodebuild':
                    (state / 'Logs/game-smoke-ZenlessZoneZero.json').write_text(json.dumps({
                        'checkpoints': [{'target_seconds': n, 'game_process_alive': True} for n in [40, 140]]}))
                    (state / 'Logs/game-smoke-ZenlessZoneZero.log').write_text('no renderer rejection')
                return SimpleNamespace(returncode=0)
            with patch.object(smoke, 'AREA', area), patch.object(smoke, 'STATE', state), \
                 patch.object(smoke, 'owned', side_effect=lambda p, boundary=None: owned(p, boundary or area)), \
                 patch.object(smoke, 'preflight', return_value={'source': {'commit': 'test'}}), \
                 patch.object(smoke, 'assert_idle'), patch.object(smoke, 'clone_identity', return_value={'commit': 'test'}), \
                 patch.object(smoke, 'inventory', side_effect=owned_inventory), \
                 patch.object(smoke.subprocess, 'run', side_effect=run), \
                 patch.object(sys, 'argv', ['smoke', '--owned-game', 'ZenlessZoneZero']):
                smoke.main()
            result = json.loads(next((area / 'results-dxmt').glob('*.json')).read_text())
            self.assertEqual(result['result'], 'completed')
            self.assertFalse(result['source_comparison_performed'])
            self.assertIsNone(result['source_installations_unchanged'])

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
