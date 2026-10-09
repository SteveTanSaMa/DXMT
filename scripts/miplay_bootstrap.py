#!/usr/bin/env python3
"""Download checksum-pinned build dependencies into this repository only."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from miplay_package import sha256

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "toolchains/miplay")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / "toolchains"):
        parser.error("Dependencies must be inside this repository's toolchains/ directory")
    directory.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / "scripts/miplay_toolchains.json").read_text())
    for name, source in lock.items():
        archive = directory / source["archive"]
        if not archive.exists():
            temporary = Path(str(archive) + ".part")
            subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--retry-all-errors",
                            "--silent", "--show-error", "--output", str(temporary), source["url"]], check=True)
            if sha256(temporary) != source["sha256"]:
                raise ValueError(f"Downloaded archive checksum mismatch: {temporary}")
            temporary.rename(archive)
        if sha256(archive) != source["sha256"]:
            raise ValueError(f"Archive checksum mismatch: {archive}")
        target = directory / name
        if target.exists():
            marker = target / ".archive-sha256"
            if not marker.is_file() or marker.read_text().strip() != source["sha256"]:
                raise ValueError(f"Refusing to overwrite an unrecognized toolchain: {target}")
        else:
            with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=directory) as staging:
                extracted = Path(staging) / name
                extracted.mkdir()
                subprocess.run(["tar", "-xf", str(archive), f"--strip-components={source['strip_components']}",
                                "-C", str(extracted)], check=True)
                (extracted / ".archive-sha256").write_text(source["sha256"] + "\n")
                extracted.rename(target)
        print(f"Ready: {name} {source['version']}", flush=True)


if __name__ == "__main__":
    main()
