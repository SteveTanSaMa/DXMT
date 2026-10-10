#!/usr/bin/env python3
"""Package and verify the complete MiPlay x86_64 builtin renderer."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tarfile
import tempfile

FILES = {
    name: f"x86_64-windows/{name}"
    for name in ("d3d10core.dll", "d3d11.dll", "dxgi.dll", "winemetal.dll")
}
FILES["winemetal.so"] = "x86_64-unix/winemetal.so"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_binary(path):
    data = Path(path).read_bytes()
    if path.suffix == ".dll":
        if len(data) < 64 or data[:2] != b"MZ":
            raise ValueError(f"Not a PE DLL: {path}")
        offset = struct.unpack_from("<I", data, 60)[0]
        if offset + 26 > len(data) or data[offset:offset + 4] != b"PE\0\0":
            raise ValueError(f"Invalid PE header: {path}")
        machine = struct.unpack_from("<H", data, offset + 4)[0]
        characteristics = struct.unpack_from("<H", data, offset + 22)[0]
        magic = struct.unpack_from("<H", data, offset + 24)[0]
        if machine != 0x8664 or magic != 0x20B or not characteristics & 0x2000:
            raise ValueError(f"Expected x86_64 PE32+ DLL: {path}")
        return "x86_64 PE32+ DLL"
    if (len(data) < 32 or data[:4] != b"\xcf\xfa\xed\xfe"
            or struct.unpack_from("<I", data, 4)[0] != 0x01000007
            or struct.unpack_from("<I", data, 12)[0] != 6):
        raise ValueError(f"Expected x86_64 Mach-O dylib: {path}")
    return "x86_64 Mach-O dylib"


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("schema_version") != 1 or set(manifest["files"]) != set(FILES):
        raise ValueError("Manifest must describe exactly the five renderer files")
    actual = {p.name for p in (directory / "dxmt").iterdir()}
    if actual != set(FILES):
        raise ValueError("Renderer directory is incomplete or contains unexpected files")
    for name, record in manifest["files"].items():
        path = directory / "dxmt" / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected regular file: {path}")
        if sha256(path) != record["sha256"] or path.stat().st_size != record["size"]:
            raise ValueError(f"File checksum/size mismatch: {name}")
        if check_binary(path) != record["format"]:
            raise ValueError(f"File architecture mismatch: {name}")
    integration = manifest.get("integration_files", {})
    if set(integration) - {"dxmt-cache-bootstrap.dylib"}:
        raise ValueError("Unexpected integration helper")
    for name, record in integration.items():
        path = directory / "integration" / name
        if path.is_symlink() or not path.is_file() or sha256(path) != record["sha256"] or path.stat().st_size != record["size"] or check_binary(path) != record["format"]:
            raise ValueError("Integration helper checksum/architecture mismatch")
    expected = {"manifest.json", *(f"dxmt/{name}" for name in FILES), *(f"integration/{name}" for name in integration)}
    sums = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if name in sums or name not in expected:
            raise ValueError("Invalid checksum entry")
        sums[name] = digest
    if set(sums) != expected or any(sha256(directory / name) != digest for name, digest in sums.items()):
        raise ValueError("Package checksums do not match")
    return manifest


def package(install, output, metadata):
    install, output = Path(install), Path(output)
    if output.exists() or Path(str(output) + ".tar.gz").exists():
        raise ValueError(f"Refusing to overwrite a package: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".miplay-", dir=output.parent) as staging:
        directory = Path(staging) / output.name
        (directory / "dxmt").mkdir(parents=True)
        records = {}
        for name, relative in FILES.items():
            source = install / relative
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Missing renderer component: {source}")
            format_name = check_binary(source)
            target = directory / "dxmt" / name
            shutil.copyfile(source, target)
            target.chmod(0o644)
            records[name] = {"sha256": sha256(target), "size": target.stat().st_size, "format": format_name}
        integration = {}
        helper = install / "integration/dxmt-cache-bootstrap.dylib"
        if helper.exists():
            if helper.is_symlink(): raise ValueError("Expected a regular integration helper")
            format_name = check_binary(helper)
            (directory / "integration").mkdir()
            shutil.copyfile(helper, directory / "integration" / helper.name)
            integration[helper.name] = {"sha256": sha256(helper), "size": helper.stat().st_size, "format": format_name}
        manifest = dict(metadata, schema_version=1, files=records, integration_files=integration,
                        status="candidate", game_runtime_validation="not_performed")
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        checksummed = ["manifest.json", *(f"dxmt/{name}" for name in sorted(FILES)), *(f"integration/{name}" for name in sorted(integration))]
        (directory / "SHA256SUMS").write_text("".join(f"{sha256(directory / name)}  {name}\n" for name in checksummed))
        verify(directory)
        # Stable archive headers; this does not promise byte-identical compiler output.
        archive = Path(staging) / (output.name + ".tar.gz")
        with archive.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for path in sorted(directory.rglob("*")):
                    entry = tar.gettarinfo(str(path), arcname=f"{output.name}/{path.relative_to(directory)}")
                    entry.uid = entry.gid = 0
                    entry.uname = entry.gname = ""
                    entry.mtime = int(metadata["source_date_epoch"])
                    entry.mode = 0o755 if path.is_dir() else 0o644
                    if path.is_file():
                        with path.open("rb") as stream:
                            tar.addfile(entry, stream)
                    else:
                        tar.addfile(entry)
        digest = sha256(archive)
        directory.rename(output)
        archive.rename(Path(str(output) + ".tar.gz"))
        Path(str(output) + ".tar.gz.sha256").write_text(f"{digest}  {output.name}.tar.gz\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_directory", type=Path)
    args = parser.parse_args()
    verify(args.package_directory)
    print(f"Verified: {args.package_directory}")
