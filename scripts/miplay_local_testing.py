#!/usr/bin/env python3
"""DXMT-owned MiPlay clone/state tooling. Never operates on a production project."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import fcntl
from datetime import datetime, timezone

from miplay_package import verify, sha256

ROOT = Path(__file__).resolve().parents[1]
AREA = ROOT / ".local-testing"
CLONE = AREA / "MiPlay-DXMT"
STATE = AREA / "state-dxmt"
ORIGIN = "https://github.com/SteveTanSaMa/MiPlay.git"
BASE = "00f97b3b9f3512e57bb3ead7c69a6b3c9c608c57"
TAG = "wine-crossover-11.0-1-signed"
ARCHIVE_SHA = "89fa7e90fb626523a90d5867a03c6be785d017176739c6320a3b86c7838c3a35"
ARCHIVE_URL = "https://github.com/yaagl/anime-game-wine/releases/download/wine-crossover-11.0-1-signed/wine-crossover-11.0-1-osx64-signed.tar.xz"


def owned(path, boundary=None):
    boundary = boundary or AREA
    path = Path(path)
    if not path.resolve().is_relative_to(boundary.resolve()) or boundary.is_symlink():
        raise ValueError(f"Path escapes the DXMT test area: {path}")
    return path


def git(*args):
    return subprocess.check_output(["git", "-C", str(CLONE), *args], text=True).strip()


def ensure_clone():
    owned(AREA)
    AREA.mkdir(exist_ok=True)
    if not CLONE.exists():
        subprocess.run(["git", "clone", ORIGIN, str(CLONE)], check=True)
    if CLONE.is_symlink() or not (CLONE / ".git").is_dir():
        raise ValueError("Expected an independent full clone, not a symlink/worktree")
    if git("remote", "get-url", "origin") != ORIGIN:
        raise ValueError("The existing test clone has a different origin; it was left untouched")
    if (CLONE / ".git/objects/info/alternates").exists():
        raise ValueError("The test clone must not borrow another checkout's object store")
    metadata = owned(AREA / "clone-dxmt.json")
    if not metadata.exists():
        metadata.write_text(json.dumps({"component": "DXMT", "origin": ORIGIN,
            "clone_commit": git("rev-parse", "HEAD"), "recorded_at": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
    # Fetch history remains available; accidental git push is locally disabled.
    subprocess.run(["git", "-C", str(CLONE), "remote", "set-url", "--push", "origin", "disabled://miplay-dxmt-testing"], check=True)
    print("Clone:", CLONE, "\nCommit:", git("rev-parse", "HEAD"), "\nStatus:\n", git("status", "--short"), flush=True)


def profile_ready():
    project = (CLONE / "MiPlay.xcodeproj/project.pbxproj").read_text()
    if "MIPLAY_DXMT_TESTING" not in project or "SteveTan.MiPlay.DXMTTesting;" not in project:
        raise ValueError("Isolation patch is not installed in this clone; refusing to launch/test it")
    if "PRODUCT_BUNDLE_IDENTIFIER = SteveTan.MiPlay;" in project:
        raise ValueError("A production bundle configuration remains in the test clone")


def clone_identity():
    diff = subprocess.check_output(["git", "-C", str(CLONE), "diff", "HEAD", "--binary"])
    digest = hashlib.sha256(diff)
    names = subprocess.check_output(["git", "-C", str(CLONE), "ls-files", "--others", "--exclude-standard", "-z"])
    for name in names.decode().split("\0"):
        if name:
            digest.update(name.encode())
            digest.update((CLONE / name).read_bytes())
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "diff_sha256": digest.hexdigest()}


def assert_idle():
    commands = subprocess.check_output(["ps", "-axo", "command="], text=True).splitlines()
    if any("/MiPlay-DXMT-Testing.app/Contents/MacOS/" in command for command in commands):
        raise ValueError("A DXMT test app is still running; existing test state was preserved")
    runtime = owned(STATE / "AppSupport/WineVersions" / TAG, STATE)
    server = runtime / "bin/wineserver"
    if server.is_file():
        owned(server, STATE)
        env = dict(os.environ, WINEPREFIX=str(STATE / "AppSupport/WinePrefixes/shared"))
        try:
            subprocess.run([str(server), "-w"], env=env, capture_output=True, timeout=2, check=True)
        except subprocess.TimeoutExpired:
            raise ValueError("The owned Wine prefix is still active; no files were replaced")


def prepare(candidate, replace=False):
    manifest = verify(candidate)
    binary = (candidate / "dxmt/dxgi.dll").read_bytes()
    if any(name.encode() not in binary for name in ("DXMT_METAL_CACHE_PATH", "DXMT_REQUIRE_ISOLATED_CACHE")):
        raise ValueError("Candidate predates the strict cache-isolation contract; it cannot be run safely here")
    owned(STATE)
    for name in ("tmp", "Logs/DXMT", "Caches/AIR", "Caches/Metal", "Config", "Run", "Tests", "SyntheticGame"):
        directory = owned(STATE / name, STATE)
        directory.mkdir(parents=True, exist_ok=True)
    (STATE / "Run").chmod(0o700)
    destination = owned(STATE / "Candidate", STATE)
    if destination.exists():
        existing = verify(destination)
        if existing["files"] != manifest["files"] or existing.get("integration_files", {}) != manifest.get("integration_files", {}):
            if not replace:
                raise ValueError("An existing candidate differs; --replace-candidate requires an idle test session and preserves a backup")
            assert_idle()
            temporary = owned(STATE / ("candidate-new-" + uuid.uuid4().hex), STATE)
            shutil.copytree(candidate, temporary)
            verify(temporary)
            backups = owned(STATE / "ArchivedCandidates", STATE)
            backups.mkdir(exist_ok=True)
            backup = backups / ("candidate-" + uuid.uuid4().hex)
            destination.rename(backup)
            try:
                temporary.rename(destination)
            except Exception:
                backup.rename(destination)
                raise
            print("Previous candidate preserved:", backup)
    else:
        shutil.copytree(candidate, destination)
    stubs = destination / "protonextras"
    if not stubs.exists():
        shutil.copytree(CLONE / "RuntimeAssets/protonextras", stubs)
    owned(STATE / "environment.json", STATE).write_text(json.dumps({
        "component": "DXMT", "clone": str(CLONE), "miplay_base": BASE,
        "miplay_commit": git("rev-parse", "HEAD"), "dxmt_commit": manifest["source"]["commit"],
        "candidate_manifest_sha256": sha256(destination / "manifest.json"),
        "runtime_tag": TAG, "runtime_archive_sha256": ARCHIVE_SHA,
        "root": str(STATE), "real_games_authorized": False, "lsfg_enabled": False
    }, indent=2) + "\n")


def prepare_runtime():
    downloads = owned(AREA / "downloads")
    downloads.mkdir(exist_ok=True)
    archive = owned(downloads / "wine-crossover-11.0-1-osx64-signed.tar.xz")
    if not archive.exists():
        temporary = owned(Path(str(archive) + ".part"))
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--retry-all-errors",
                        "--silent", "--show-error", "--output", str(temporary), ARCHIVE_URL], check=True)
        if sha256(temporary) != ARCHIVE_SHA:
            raise ValueError("Wine download checksum mismatch")
        temporary.rename(archive)
    if sha256(archive) != ARCHIVE_SHA:
        raise ValueError("Wine archive checksum mismatch")
    runtime = owned(STATE / "AppSupport/WineVersions" / TAG, STATE)
    marker = owned(STATE / "runtime-origin.json", STATE)
    if runtime.exists() and marker.exists():
        if json.loads(marker.read_text()).get("archive_sha256") != ARCHIVE_SHA:
            raise ValueError("Existing runtime has a different recorded origin; it was not changed")
        print("Existing independently downloaded runtime preserved")
        return
    if not runtime.exists():
        runtime.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="runtime-extract-dxmt-", dir=AREA) as staging:
            with tarfile.open(archive) as tar:
                # Python's data filter refuses paths/links escaping extraction.
                tar.extractall(staging, filter="data")
            source = Path(staging) / "wine"
            source.rename(runtime)
    # Recognize an already extracted archive only by a matching executable hash.
    with tarfile.open(archive) as tar:
        import hashlib
        expected = hashlib.file_digest(tar.extractfile("wine/bin/wine"), "sha256").hexdigest()
    if sha256(runtime / "bin/wine") != expected:
        raise ValueError("Existing runtime is not this pinned input; nothing was overwritten")
    marker.write_text(json.dumps({"archive_url": ARCHIVE_URL, "archive_sha256": ARCHIVE_SHA,
        "wine_binary_sha256": expected, "runtime": str(runtime)}, indent=2) + "\n")
    print("Independent pinned Wine runtime ready:", runtime)


def preflight():
    profile_ready()
    owned(STATE)
    manifest = verify(owned(STATE / "Candidate", STATE))
    runtime = owned(STATE / "AppSupport/WineVersions" / TAG, STATE)
    for path in (runtime / "bin/wine", runtime / "bin/wineserver", runtime / "lib/wine/x86_64-unix/ntdll.so",
                 runtime / "lib/wine/x86_64-unix/winemac.so"):
        owned(path, STATE)
        if not path.is_file():
            raise ValueError(f"Missing independent downloaded runtime input: {path}")
    if "x86_64" not in subprocess.check_output(["lipo", "-archs", str(runtime / "bin/wine")], text=True):
        raise ValueError("DXMT package requires an x86_64 Wine runtime")
    if not (STATE / "environment.json").is_file():
        raise ValueError("Prepare the owned environment before running it")
    if not (STATE / "runtime-origin.json").is_file():
        raise ValueError("Record/verify the independent runtime with the runtime command first")
    print("Preflight passed; this is not a game/GPU compatibility result.", flush=True)
    return manifest


def run_tests(real_wine=False):
    manifest = preflight()
    identity = clone_identity()
    env = dict(os.environ, MIPLAY_DXMT_TEST_ROOT=str(STATE), TMPDIR=str(STATE / "tmp") + "/")
    for key in list(env):
        if key.startswith(("WINE", "DXMT_", "LSFG_", "DYLD_")):
            del env[key]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    results = owned(AREA / "results-dxmt")
    results.mkdir(exist_ok=True)
    label = "wine-probe" if real_wine else "unit"
    command = ["xcodebuild", "-project", str(CLONE / "MiPlay.xcodeproj"), "-scheme", "MiPlay",
        "-configuration", "Debug", "-derivedDataPath", str(AREA / "DerivedData-DXMT"),
        "-resultBundlePath", str(results / f"{label}-{stamp}.xcresult"), "test",
        "CODE_SIGNING_ALLOWED=NO", "-parallel-testing-enabled", "NO",
        f"MIPLAY_DXMT_REAL_WINE={'1' if real_wine else '0'}"]
    if real_wine:
        compiler = ROOT / "toolchains/miplay/mingw/bin/x86_64-w64-mingw32-clang++"
        subprocess.run([str(compiler), "-std=c++20", "-O2", "-static", str(ROOT / "tests/integration/dxmt_wine_compute.cpp"),
            "-o", str(STATE / "Tests/dxmt_compute.exe"), "-ld3d11", "-ld3dcompiler"], check=True)
        command.append("-only-testing:MiPlayTests/MiPlayCoreTests/testDXMTDownloadedRuntimeComputeProbe")
    started = time.time()
    log = owned(results / f"{label}-{stamp}.log")
    trace = owned(results / f"{label}-{stamp}.json")
    record = {"component": "DXMT", "mode": label, "miplay_source": identity,
              "renderer_source": manifest["source"], "manifest_sha256": sha256(STATE / "Candidate/manifest.json"),
              "runtime": json.loads((STATE / "runtime-origin.json").read_text()),
              "command": command, "started_utc": datetime.now(timezone.utc).isoformat(),
              "real_game_validation": "not_performed", "lsfg_validation": "not_performed", "result": "running"}
    trace.write_text(json.dumps(record, indent=2) + "\n")
    try:
        with log.open("w") as stream:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        print("Test exit:", result.returncode, "Log:", log)
        if result.returncode:
            print("\n".join(log.read_text(errors="replace").splitlines()[-30:]))
            raise RuntimeError("Test failed; see the preserved log/result bundle")
        if clone_identity() != identity:
            raise RuntimeError("MiPlay source changed during testing; result cannot be attributed to the starting revision")
        if real_wine:
            report = owned(STATE / "Logs/compute-probe.txt", STATE)
            if not report.is_file() or report.stat().st_mtime < started or "COMPUTE_RESULT=42" not in report.read_text():
                raise RuntimeError("No fresh GPU readback result; a skipped test is not a successful real probe")
        record["result"] = "passed"
    except Exception:
        record["result"] = "failed"
        raise
    finally:
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        trace.write_text(json.dumps(record, indent=2) + "\n")


def export():
    if git("status", "--porcelain"):
        raise ValueError("Commit test-clone changes before exporting")
    directory = owned(AREA / "artifacts-dxmt")
    directory.mkdir(exist_ok=True)
    patch = directory / "MiPlay-DXMT-integration.patch"
    patch.write_bytes(subprocess.check_output(["git", "-C", str(CLONE), "format-patch", "--stdout", f"{BASE}..HEAD"]))
    (directory / "provenance.json").write_text(json.dumps({"miplay_base": BASE, "miplay_head": git("rev-parse", "HEAD"),
        "fork_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "patch_sha256": sha256(patch)}, indent=2) + "\n")
    print("Private local patch:", patch)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["clone", "prepare", "runtime", "preflight", "test", "probe", "export"])
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--replace-candidate", action="store_true")
    args = parser.parse_args()
    ensure_clone()
    if args.command == "prepare":
        if args.candidate is None: parser.error("prepare requires --candidate")
        prepare(args.candidate.resolve(), replace=args.replace_candidate)
    elif args.command == "runtime": prepare_runtime()
    elif args.command == "preflight": preflight()
    elif args.command == "test": run_tests()
    elif args.command == "probe": run_tests(real_wine=True)
    elif args.command == "export": export()


if __name__ == "__main__":
    try:
        AREA.mkdir(exist_ok=True)
        owned(AREA)
        with owned(AREA / "dxmt-session.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit("Another DXMT testing command is active; no state was changed")
            main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
