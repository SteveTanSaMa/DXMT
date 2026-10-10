#!/usr/bin/env python3
"""Compile MiPlay's repeated-device regression for this Fork's actual Windows layout."""
import json
from pathlib import Path
import re
import shlex
import subprocess
from miplay_local_testing import ROOT, STATE, owned
from miplay_package import sha256


def compile_repro():
    manifest = json.loads((STATE / 'Candidate/manifest.json').read_text())
    renderer_commit = manifest['source']['commit']
    if not re.fullmatch(r'[0-9a-f]{40}', renderer_commit):
        raise ValueError('Invalid renderer source revision')
    if subprocess.run(['git', 'diff', '--quiet', renderer_commit, '--', 'src', 'include', 'libs'], cwd=ROOT).returncode:
        raise ValueError('Current layout sources differ from the candidate; build/select a matching candidate first')
    build = ROOT / 'build/miplay-candidate'
    entry = next(e for e in json.loads((build / 'compile_commands.json').read_text()) if e['file'].endswith('dxmt_context.cpp'))
    if Path(entry['directory']).resolve() != build.resolve():
        raise ValueError('Unexpected build directory in compile database')
    arguments = shlex.split(entry['command'])
    compiler = ROOT / 'toolchains/miplay/mingw/bin/x86_64-w64-mingw32-clang++'
    if Path(arguments[0]).resolve() != compiler.resolve():
        raise ValueError('Regression requires the pinned x86_64 Windows compiler')
    directory = owned(STATE / 'Tests', STATE)
    source = directory / 'command_queue_size.cpp'
    source.write_text('#include "dxmt_command_queue.hpp"\nextern "C" const unsigned long long miplay_command_queue_size = sizeof(dxmt::CommandQueue);\n')
    ir = directory / 'command_queue_size.ll'
    command = arguments[:arguments.index('-MD')] + ['-S', '-emit-llvm', str(source), '-o', str(ir)]
    subprocess.run(command, cwd=build, check=True)
    match = re.search(r'@miplay_command_queue_size\s*=.*?constant i64 (\d+)', ir.read_text())
    if not match or not 0 < int(match[1]) <= 16 * 1024 * 1024:
        raise ValueError('Cannot determine a valid CommandQueue size')
    size = int(match[1])
    executable = directory / 'dxmt_device_repro.exe'
    probe_source = ROOT / 'tests/integration/dxmt_device_repro.c'
    compile_command = [str(compiler.with_name('x86_64-w64-mingw32-clang')), '-std=c11', '-O2', '-static',
                       f'-DCOMMAND_QUEUE_SIZE={size}', str(probe_source), '-o', str(executable), '-ld3d11']
    subprocess.run(compile_command, check=True)
    (directory / 'device-repro-build.json').write_text(json.dumps({
        'fork_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'renderer_commit': renderer_commit,
        'upstream_fix': 'fb4515681daefb789a4d0f403c4bdbca88f3b3de', 'command_queue_size': size,
        'sizeof_command': command, 'compile_command': compile_command,
        'source_sha256': sha256(probe_source), 'executable_sha256': sha256(executable),
        'layout_limitation': 'Nonzero freed blocks encourage allocator reuse; reuse is not guaranteed.'}, indent=2) + '\n')
    print('Device regression compiled; CommandQueue size:', size, flush=True)


if __name__ == '__main__':
    compile_repro()
