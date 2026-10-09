# MiPlay candidate build and release baseline

This flow produces a **candidate** DXMT renderer; it does not patch MiPlay, copy
files into its runtime, start Wine/game processes, or publish a GitHub release.
The existing MiPlay v0.80 assets remain the production baseline.

## Dependencies and build profile

- macOS with Xcode and the Metal toolchain, Python 3.11+, Meson 1.11.2, Ninja.
- `scripts/miplay_toolchains.json` pins archive URLs and SHA-256 for LLVM 15.0.7
  x86_64, LLVM-MinGW 20260908 UCRT macOS universal, and the upstream Wine
  development SDK `v8.16-3shain`. Bootstrap verifies archives before extraction
  and refuses to overwrite unknown toolchain directories.
- Release x86_64 Wine **builtin** DLLs; optional NVAPI, NVNGX and D3D12 are off.
  This package is intentionally the five components used by MiPlay staging.
- Unix bridge deployment target is explicitly macOS 14.0 (the upstream
  baseline), independent of the build host/SDK. The emitted Mach-O minimum OS
  is checked and recorded. MiPlay's product support remains macOS 26+.
- LLVM library search uses a generated static-only view, so LLVM's bundled
  `libc++.dylib` does not become an extra deployment dependency. Packaging
  rejects toolchain dylibs; only system libraries and Wine's ntdll/winemac are
  allowed dependencies of winemetal.so.

The development SDK is **not** MiPlay's fixed runtime
`wine-crossover-11.0-1-signed`. MiPlay's runtime lacks development libraries.
The target runtime identity is recorded separately; it is not a claim of
compatibility. Runtime compatibility needs isolated Wine/Metal/game testing.
You can supply another SDK with `--wine-sdk-root` and `--wine-sdk-id`; its
identity and file fingerprints are recorded. Never use a live MiPlay runtime
as an install prefix or build output.

## Local build

From the repository root, with committed changes:

```sh
python3 scripts/miplay_bootstrap.py
python3 scripts/miplay_build.py \
  --llvm-root toolchains/miplay/llvm \
  --mingw-root toolchains/miplay/mingw \
  --wine-sdk-root toolchains/miplay/wine \
  --wine-sdk-id v8.16-3shain
```

Default build output is `build/miplay-candidate`; final artifacts are under
`releases/dxmt-miplay-<commit>/`. Both are ignored by Git. Existing packages are
never overwritten; use `--output-root` to create a separate repeat-build area.
`--allow-dirty` is an explicit development-only option and records a source
diff fingerprint in the package name and manifest. If sources change during
the build, packaging fails. Submodule state is included.

The script runs native regression tests and packaging tests, compiles and
installs into the isolated build prefix, checks Mach-O dependencies, validates
all five binary formats, and packages only after all checks pass. Complete
command logs remain in the build directory; a failed command prints its final
diagnostics. The build directory must be inside this repository's `build/`.

## Artifact contract

```text
dxmt-miplay-<commit>/
  dxmt/d3d10core.dll
  dxmt/d3d11.dll
  dxmt/dxgi.dll
  dxmt/winemetal.dll
  dxmt/winemetal.so
  manifest.json
  SHA256SUMS
dxmt-miplay-<commit>.tar.gz
dxmt-miplay-<commit>.tar.gz.sha256
```

The manifest includes source/fork commit, upstream base, dirty fingerprint,
submodules, tool versions, dependency lock and input hashes, Meson options,
cross file, AIRCONV version, SDK identity, intended runtime identity, validated
Unix dependencies, file sizes/formats/SHA-256 and test/build status. It explicitly
marks runtime/game validation as **not performed**.

Verify a directory after transfer:

```sh
python3 scripts/miplay_package.py releases/dxmt-miplay-<commit>
```

Verification detects missing, extra, wrong-architecture, changed or symlinked
renderer files and changed manifests. Checksums provide integrity, not publisher
authentication. Keep the trusted archive checksum/CI artifact provenance
separately; this flow does not sign or notarize the renderer.

The recipe and third-party archives are pinned. Toolchain versions, SDK and
effective build parameters are recorded. Archive timestamps/ownership and gzip
headers are normalized. This is **not a guarantee of byte-identical binaries**
across different Xcode SDKs, hosts or paths; test archive determinism separately
from compiler output reproducibility.

## Regression tests

These are a standalone Meson project, so they do not require LLVM or Wine:

```sh
meson setup build/regression tests/regression --buildtype=debug
meson test -C build/regression --print-errorlogs
meson setup build/regression-asan tests/regression \
  --buildtype=debug -Db_sanitize=address,undefined
meson test -C build/regression-asan --print-errorlogs
python3 -m unittest discover -s tests/packaging -v
```

Assertions are enabled regardless of build type. Tests cover joining active
workers before destroying task storage, idle/repeated shutdown, rejected late
submissions; last-owner borrowed alias/self assignment and moves; real
autoreleased NSError lifetimes through mocked bridge functions, replacement
and success clearing; compiled-bitcode cleanup on early return, exception,
success and null input. Packaging tests use synthetic binary headers and cover
completeness, hashes, architecture, overwrite protection, dependency rejection
and deterministic archive headers.

The scheduler test exercises the production scheduler with an owner matching
PipelineCache's destruction boundary; it does not instantiate a real D3D device.
NSError tests use Foundation objects with mocked C bridge returns, not a Wine
process or actual failing Metal compilation. Bitcode tests exercise the
production owner with a mock destructor, not full AIR conversion. Cross-building
the real renderer supplies additional compiler/linker coverage; these tests do
not replace runtime validation.

## CI and release promotion

`.github/workflows/miplay.yml` preserves the existing upstream workflow and
adds a macOS 15 / Xcode 16.4 build, pinned build dependencies, sanitizer tests,
complete candidate packaging and diagnostic uploads. It runs on matching
pushes/PRs or manually. CI execution itself is not locally validated until the
workflow runs on GitHub. No release publishing or production promotion occurs.

Before promotion, verify all five files together against MiPlay's exact Wine
runtime in an **isolated copy/prefix**, including DLL loading, shader/compute
work, graphics, game startup, exit/cancellation, fullscreen/resize and long
sessions for all three games. Compare with v0.80. Historical ZZZ crashes are not
declared fixed by these source changes. MiPlay transactional staging and
package identity consumption remain a separately authorized next phase.
