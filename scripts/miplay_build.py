#!/usr/bin/env python3
"""Build/test/package a candidate; never install into MiPlay or launch games."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from miplay_package import package, sha256

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_BASE = "e94c312f5c054263acf261cfa109edf13e757587"


def capture(*command):
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def run(command, log, env):
    print("Running:", " ".join(map(str, command)), flush=True)
    with log.open("w") as stream:
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print("\n".join(log.read_text(errors="replace").splitlines()[-30:]), file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}); log: {log}")


def source_identity():
    commit = capture("git", "rev-parse", "HEAD")
    status = capture("git", "status", "--porcelain", "--untracked-files=all")
    digest = hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=ROOT))
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    for name in untracked.decode().split("\0"):
        if name:
            digest.update(name.encode())
            digest.update((ROOT / name).read_bytes())
    return {"commit": commit, "dirty": bool(status), "diff_sha256": digest.hexdigest(),
            "submodules": capture("git", "submodule", "status", "--recursive")}


def check_dependencies(library):
    lines = capture("otool", "-L", str(library)).splitlines()[2:]
    deps = [line.strip().split(" (", 1)[0] for line in lines]
    for dependency in deps:
        if not (dependency.startswith(("/System/Library/", "/usr/lib/"))
                or dependency in ("@rpath/ntdll.so", "@rpath/winemac.so")):
            raise ValueError(f"Non-system/toolchain dylib dependency: {dependency}")
    return deps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm-root", type=Path, required=True)
    parser.add_argument("--mingw-root", type=Path, required=True)
    parser.add_argument("--wine-sdk-root", type=Path, required=True)
    parser.add_argument("--wine-sdk-id", required=True)
    parser.add_argument("--wine-runtime-id", default="wine-crossover-11.0-1-signed")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/miplay-candidate")
    parser.add_argument("--output-root", type=Path, default=ROOT / "releases")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--deployment-target", default="14.0", help="Minimum macOS version for the Unix bridge")
    parser.add_argument("--allow-dirty", action="store_true", help="Development candidates only")
    args = parser.parse_args()
    if sys.platform != "darwin" or args.jobs < 1:
        parser.error("Requires macOS and a positive --jobs value")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", args.deployment_target):
        parser.error("--deployment-target must be a numeric macOS version")
    llvm, mingw, wine = [p.resolve() for p in (args.llvm_root, args.mingw_root, args.wine_sdk_root)]
    build = args.build_dir.resolve()
    # Restrict generated files to this repository's ignored build area.
    if not build.is_relative_to(ROOT / "build"):
        parser.error("--build-dir must be inside this repository's build/ directory")
    required = [llvm / "lib/libLLVMCore.a", llvm / "include/llvm/IR/Module.h",
                mingw / "bin/x86_64-w64-mingw32-clang++", wine / "bin/winebuild",
                wine / "lib/wine/x86_64-windows/libwinecrt0.a",
                wine / "lib/wine/x86_64-unix/ntdll.so", wine / "lib/wine/x86_64-unix/winemac.so"]
    for path in required:
        if not path.is_file():
            raise ValueError(f"Missing build input (a runtime alone is not a Wine SDK): {path}")
    if "x86_64" not in capture("lipo", "-info", str(required[0])):
        raise ValueError("LLVM must provide x86_64 static libraries")
    llvm_config = (llvm / "include/llvm/Config/llvm-config.h").read_text()
    if not re.search(r"#define LLVM_VERSION_MAJOR\s+15\b", llvm_config):
        raise ValueError("DXMT requires LLVM major version 15")
    source = source_identity()
    if source["dirty"] and not args.allow_dirty:
        raise ValueError("Commit changes first, or explicitly use --allow-dirty for development")
    subprocess.run(["git", "merge-base", "--is-ancestor", UPSTREAM_BASE, "HEAD"], cwd=ROOT, check=True)
    epoch = capture("git", "show", "-s", "--format=%ct", "HEAD")
    env = dict(os.environ, SOURCE_DATE_EPOCH=epoch, MACOSX_DEPLOYMENT_TARGET=args.deployment_target)
    build.mkdir(parents=True, exist_ok=True)
    # Limit the library search path to LLVM static archives. Official LLVM
    # bundles also ship libc++.dylib, which must not escape into the five files.
    view = build / "llvm-static"
    (view / "lib").mkdir(parents=True, exist_ok=True)
    desired = {path.name: path for path in (llvm / "lib").glob("libLLVM*.a")}
    for path in (view / "lib").iterdir():
        if not path.is_symlink():
            raise ValueError(f"Unexpected file in generated LLVM view: {path}")
        path.unlink()
    for name, target in desired.items():
        (view / "lib" / name).symlink_to(target)
    include = view / "include"
    if include.is_symlink():
        include.unlink()
    include.symlink_to(llvm / "include")
    cross = build / "cross.ini"
    binaries = {"c": "clang", "cpp": "clang++", "ar": "ar", "strip": "strip", "windres": "windres"}
    entries = [f"{key} = {str(mingw / 'bin' / ('x86_64-w64-mingw32-' + name))!r}" for key, name in binaries.items()]
    cross.write_text("[binaries]\n" + "\n".join(entries) +
                     "\n[properties]\nneeds_exe_wrapper = true\n[host_machine]\nsystem = 'windows'\n"
                     "cpu_family = 'x86_64'\ncpu = 'x86_64'\nendian = 'little'\n")
    options = ["--buildtype=release", "-Dwine_builtin_dll=true", "-Ddxmt_debug=false",
               "-Denable_tests=false", "-Denable_nvapi=false", "-Denable_nvngx=false",
               "-Denable_d3d12=false", "-Dbuild_airconv_for_windows=false",
               f"-Dnative_llvm_path={view.relative_to(ROOT)}", f"-Dwine_install_path={wine}",
               "-Dwine_build_path=", f"--prefix={build / 'install'}"]
    for option in ("c_args", "cpp_args", "c_link_args", "cpp_link_args"):
        options.append(f"-Dbuild.{option}=-mmacosx-version-min={args.deployment_target}")
    setup = ["meson", "setup"]
    if (build / "meson-private/coredata.dat").exists():
        setup += ["--reconfigure"]
    run(setup + [build, ROOT, "--cross-file", cross, *options], build / "setup.log", env)
    regression = build / "regression"
    test_setup = ["meson", "setup"]
    if (regression / "meson-private/coredata.dat").exists():
        test_setup += ["--reconfigure"]
    run(test_setup + [regression, ROOT / "tests/regression", "--buildtype=debug", "-Db_ndebug=false"],
        build / "test-setup.log", env)
    run(["meson", "test", "-C", regression, "--print-errorlogs"], build / "tests.log", env)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests/packaging", "-v"],
        build / "package-tests.log", env)
    run(["meson", "compile", "-C", build, "-j", args.jobs], build / "compile.log", env)
    run(["meson", "install", "-C", build, "--no-rebuild"], build / "install.log", env)
    dependencies = check_dependencies(build / "install/x86_64-unix/winemetal.so")
    load_commands = capture("otool", "-l", str(build / "install/x86_64-unix/winemetal.so"))
    minimum_os = re.search(r"\bminos\s+(\S+)", load_commands)
    if not minimum_os or tuple(map(int, minimum_os[1].split("."))) > tuple(map(int, args.deployment_target.split("."))):
        raise ValueError("Unix bridge minimum OS does not match the deployment target")
    if source_identity() != source:
        raise ValueError("Source changed during the build; candidate not packaged")
    metadata = {
        "source": source, "upstream_base": UPSTREAM_BASE, "source_date_epoch": epoch,
        "macos_deployment_target": args.deployment_target, "unix_minimum_os": minimum_os[1],
        "wine_sdk_id": args.wine_sdk_id, "target_wine_runtime_id": args.wine_runtime_id,
        "wine_runtime_compatibility": "not_validated", "profile": "x86_64-wine-builtin",
        "airconv_version": int(re.search(r"#define AIRCONV_VERSION (\d+)",
                                          (ROOT / "src/airconv/airconv_public.h").read_text())[1]),
        "build_parameters": options, "cross_file": cross.read_text(),
        "meson_build_options": json.loads(capture("meson", "introspect", str(build), "--buildoptions")),
        "tool_versions": {"meson": capture("meson", "--version"), "ninja": capture("ninja", "--version"),
                          "xcode": capture("xcodebuild", "-version"), "sdk": capture("xcrun", "--show-sdk-version"),
                          "native_cxx": capture("c++", "--version"),
                          "cross_cxx": capture(str(mingw / "bin/x86_64-w64-mingw32-clang++"), "--version")},
        "dependency_lock": json.loads((ROOT / "scripts/miplay_toolchains.json").read_text()),
        "dependency_archive_markers": {name: (path / ".archive-sha256").read_text().strip()
                                       if (path / ".archive-sha256").is_file() else "custom-unpinned-input"
                                       for name, path in (("llvm", llvm), ("mingw", mingw), ("wine", wine))},
        "llvm_library_sha256": {name: sha256(path) for name, path in desired.items()},
        "input_sha256": {str(path): sha256(path) for path in required if path.is_file()},
        "unix_dependencies": dependencies, "checks": {"regressions": "passed", "packaging": "passed", "cross_build": "passed"},
    }
    identity = source["commit"][:12] + ("-dirty-" + source["diff_sha256"][:8] if source["dirty"] else "")
    output = package(build / "install", args.output_root.resolve() / ("dxmt-miplay-" + identity), metadata)
    print(f"Candidate: {output}\nNo MiPlay files or runtime assets were changed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
