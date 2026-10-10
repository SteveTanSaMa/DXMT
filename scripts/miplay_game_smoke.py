#!/usr/bin/env python3
"""Serial 40/140-second observations using independently cloned APFS game files."""
import ctypes
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone
from miplay_local_testing import AREA, CLONE, ROOT, STATE, TAG, owned, preflight, assert_idle, clone_identity, sha256


def inventory(root):
    result = {}
    for directory, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f"Game source contains a symlink: {path}; cannot guarantee isolation")
        for name in files:
            path = Path(directory) / name
            st = path.stat()
            result[str(path.relative_to(root))] = [st.st_ino, st.st_size, st.st_mtime_ns]
    return result


def clone_game(source, destination):
    owned(destination, STATE)
    before = inventory(source)
    if destination.exists():
        raise ValueError(f"Existing game copy preserved: {destination}; choose a fresh session explicitly")
    destination.mkdir(parents=True)
    clonefile = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).clonefile
    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clonefile.restype = ctypes.c_int
    for name, identity in before.items():
        src, dst = source / name, destination / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if clonefile(os.fsencode(src), os.fsencode(dst), 0):
            raise OSError(ctypes.get_errno(), f"APFS clone failed: {src}; partial copy preserved")
        if dst.stat().st_ino == identity[0]:
            raise ValueError('Game clone unexpectedly shares inode')
    if inventory(source) != before:
        raise ValueError('Source installation changed during copy; refusing launch')
    return before


def main():
    manifest = preflight()
    assert_idle()
    # Explicit source arguments; never silently use another Fork's copy.
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--genshin', type=Path)
    parser.add_argument('--zzz', type=Path)
    parser.add_argument('--owned-game', choices=['GenshinImpact', 'ZenlessZoneZero'], action='append', help='Run existing provenance-tracked DXMT copies without accessing formal installations')
    parser.add_argument('--reuse-copies', action='store_true', help='Reuse only source-matched copies with provenance markers')
    args = parser.parse_args()
    if args.owned_game and (args.genshin or args.zzz):
        parser.error('--owned-game cannot be combined with source paths')
    configs, sources = [], []
    for kind in args.owned_game or []:
        if any(c['type'] == kind for c in configs):
            parser.error('A game may be selected only once')
        exe = 'YuanShen.exe' if kind == 'GenshinImpact' else 'ZenlessZoneZero.exe'
        game = owned(STATE / 'Games' / kind, STATE)
        marker = owned(STATE / f'Config/game-copy-{kind}.json', STATE)
        provenance = json.loads(marker.read_text())
        if not provenance.get('files') or not (game / exe).is_file():
            raise ValueError('Owned game copy lacks clone provenance or executable')
        copied = inventory(game)
        original_exe = provenance['files'].get(exe)
        if not original_exe or copied[exe][0] == original_exe[0] or copied[exe][1] != original_exe[1] or provenance.get('executable_sha256') != sha256(game / exe):
            raise ValueError('Owned executable inode/size does not match independent-copy provenance')
        configs.append({'type': kind, 'exe': exe})
        sources.append({'game': kind, 'source': None, 'copy': str(game), 'clone_origin': provenance['source'],
                        'provenance_sha256': sha256(marker), 'copy_before': copied,
                        'executable_sha256': sha256(game / exe)})
    for kind, source, exe in [('GenshinImpact', args.genshin, 'YuanShen.exe'), ('ZenlessZoneZero', args.zzz, 'ZenlessZoneZero.exe')]:
        if source is None:
            continue
        source = source.resolve(strict=True)
        if not (source / exe).is_file():
            raise ValueError(f'No executable: {source / exe}')
        game = owned(STATE / 'Games' / kind, STATE)
        marker = owned(STATE / f'Config/game-copy-{kind}.json', STATE)
        if args.reuse_copies:
            provenance = json.loads(marker.read_text())
            before = inventory(source)
            if provenance['source'] != str(source) or provenance['files'] != before:
                raise ValueError('Source differs from the recorded clone; copies preserved')
            if not game.is_dir() or (game / exe).stat().st_ino == (source / exe).stat().st_ino or sha256(game / exe) != sha256(source / exe):
                raise ValueError('Copy executable mismatch; copies preserved')
            inventory(game)  # Reject any newly introduced symlinks.
        else:
            before = clone_game(source, game)
            marker.write_text(json.dumps({'source': str(source), 'files': before, 'executable_sha256': sha256(source / exe)}, indent=2) + '\n')
        configs.append({'type': kind, 'exe': exe})
        sources.append({'game': kind, 'source': str(source), 'copy': str(game), 'files': before,
                        'executable_sha256': sha256(source / exe)})
    if not configs:
        raise ValueError('Provide at least one complete game directory')
    (STATE / 'Config/game-smoke.json').write_text(json.dumps(configs, indent=2) + '\n')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    results = owned(AREA / 'results-dxmt')
    log = results / f'games-{stamp}.log'
    trace = results / f'games-{stamp}.json'
    record = {'miplay_source': clone_identity(), 'renderer_source': manifest['source'],
              'candidate_manifest_sha256': sha256(STATE / 'Candidate/manifest.json'),
              'runtime': json.loads((STATE / 'runtime-origin.json').read_text()),
              'sources': sources, 'lsfg_enabled': False, 'result': 'running',
              'scope': 'sequential 40s/140s process survival; no gameplay input'}
    trace.write_text(json.dumps(record, indent=2) + '\n')
    command = ['xcodebuild', '-project', str(CLONE / 'MiPlay.xcodeproj'), '-scheme', 'MiPlay',
               '-configuration', 'Debug', '-derivedDataPath', str(AREA / 'DerivedData-DXMT'),
               '-resultBundlePath', str(results / f'games-{stamp}.xcresult'), 'test',
               'CODE_SIGNING_ALLOWED=NO', '-parallel-testing-enabled', 'NO',
               'MIPLAY_DXMT_REAL_WINE=0', 'MIPLAY_DXMT_GAME_SMOKE=1',
               '-only-testing:MiPlayTests/MiPlayCoreTests/testDXMTSequentialGameSmoke']
    env = dict(os.environ, MIPLAY_DXMT_TEST_ROOT=str(STATE), TMPDIR=str(STATE / 'tmp') + '/')
    for key in list(env):
        if key.startswith(('WINE', 'DXMT_', 'LSFG_', 'DYLD_')): del env[key]
    print('Sequential smoke run:', log, flush=True)
    started = time.time()
    try:
        with log.open('w') as stream:
            status = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600).returncode
        record['xcode_exit_code'] = status
        observations = []
        for item in configs:
            path = STATE / f"Logs/game-smoke-{item['type']}.json"
            if path.exists() and path.stat().st_mtime >= started:
                value = json.loads(path.read_text())
                game_log = owned(STATE / f"Logs/game-smoke-{item['type']}.log", STATE)
                value['renderer_initialization_rejected'] = game_log.exists() and 'Metal cache configuration rejected' in game_log.read_text(errors='replace')
                value['process_observation'] = 'alive_at_both_checkpoints' if len(value.get('checkpoints', [])) == 2 and all(c['game_process_alive'] for c in value['checkpoints']) else 'exit_or_launch_failure_requires_review'
                observations.append(value)
        record['observations'] = observations
        record['source_comparison_performed'] = any(s['source'] for s in sources)
        record['source_installations_unchanged'] = all(inventory(Path(s['source'])) == s['files'] and sha256(Path(s['source']) / next(c['exe'] for c in configs if c['type'] == s['game'])) == s['executable_sha256'] for s in sources if s['source']) if record['source_comparison_performed'] else None
        record['result'] = 'completed' if status == 0 and len(observations) == len(configs) and all([c['target_seconds'] for c in v.get('checkpoints', [])] == [40, 140] for v in observations) and record['source_installations_unchanged'] is not False else 'failed'
        if record['miplay_source'] != clone_identity():
            record['result'] = 'failed'
            raise ValueError('Clone source changed during testing')
        assert_idle()
        print('Result:', record['result'], trace, flush=True)
        if record['result'] != 'completed': raise RuntimeError(f'Smoke harness failed; inspect {log}')
    except Exception:
        record['result'] = 'failed'
        raise
    finally:
        # This runner owns the exclusive session lock. Kill only its own prefix,
        # including on timeout/host failure; never use a global wineserver kill.
        server = owned(STATE / 'AppSupport/WineVersions' / TAG / 'bin/wineserver', STATE)
        prefix = owned(STATE / 'AppSupport/WinePrefixes/shared', STATE)
        cleanup_env = dict(env, WINEPREFIX=str(prefix))
        subprocess.run([str(server), '-k'], env=cleanup_env, capture_output=True, timeout=15)
        subprocess.run([str(server), '-w'], env=cleanup_env, capture_output=True, timeout=15, check=True)
        for item in configs:
            plugins = 'YuanShen_Data/Plugins' if item['type'] == 'GenshinImpact' else 'ZenlessZoneZero_Data/Plugins/x86_64'
            original = owned(STATE / 'Games' / item['type'] / plugins / 'vulkan-1.dll', STATE)
            backup = owned(Path(str(original) + '.bak'), STATE)
            if not original.exists() and backup.exists(): backup.rename(original)
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        trace.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    with owned(AREA / 'dxmt-session.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
