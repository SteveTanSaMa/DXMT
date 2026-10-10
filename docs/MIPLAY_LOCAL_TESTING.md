# MiPlay-DXMT independent integration environment

Environment established on 2026-10-09. Updates on 2026-10-10:
[serial game observations](MIPLAY_GAME_SMOKE_2026-10-10.md) and
[early Metal cache initialization fix](MIPLAY_METAL_CACHE_INITIALIZATION.md).
Later game runs use provenance-tracked, independent APFS game copies,
redirected Prefix user folders/Z: and explicitly enabled Metal HUD. This is the DXMT fork's environment;
the LSFG fork must create its own **MiPlay-LSFG**, application identity and
state directories. No LSFG checkout or another Codex workspace was modified.

## Source and state ownership

```text
DXMT/
  .local-testing/                         # ignored by the outer Git repository
    MiPlay-DXMT/                          # full, independent private Git clone
    clone-dxmt.json                       # immutable clone provenance
    DerivedData-DXMT/                     # this clone's Xcode build products
    downloads/                           # independently downloaded Wine archive
    state-dxmt/
      environment.json                   # clone/renderer/runtime identities
      runtime-origin.json                # pinned Wine archive and executable hash
      Candidate/                         # verified package and cloned Steam stubs
      ArchivedCandidates/                # preserved package generations
      AppSupport/
        AppData.json
        WineVersions/wine-crossover-11.0-1-signed/
        WinePrefixes/shared/
        MediaCache/
        RuntimeAssets/                   # generated icons, not production assets
        LaunchApps/                      # test-only game wrapper bundles
        Logs/
      Caches/AIR/                         # DXMT conversion cache
      Caches/Metal/                       # Metal framework PSO cache
      Logs/DXMT/
      Logs/compute-probe.txt
      SyntheticGame/                     # synthetic fixtures; no real game files
      Tests/dxmt_compute.exe
      tmp/
      Run/
    results-dxmt/                        # logs and .xcresult bundles
    artifacts-dxmt/                      # private migration patch and provenance
```

Clone URL: `https://github.com/SteveTanSaMa/MiPlay.git`.
Initial commit: `00f97b3b9f3512e57bb3ead7c69a6b3c9c608c57`.
Branch: `local-testing/dxmt-isolation`. Its `.git` directory and complete
history remain intact. No alternates, linked worktree or existing testing copy
was used. The clone's Git push URL is disabled; its fetch URL remains valid.
The outer tooling reports existing modifications and never resets the clone.

Test application: **MiPlay-DXMT-Testing.app**.
Bundle ID: `SteveTan.MiPlay.DXMTTesting`; XCTest ID:
`SteveTan.MiPlay.DXMTTestingTests`. The Swift module stays `MiPlay` so existing
tests can import it. Both configurations in the clone enable
`MIPLAY_DXMT_TESTING`; they have distinct process/bundle identities.

The downloaded Wine input is the exact tag used by MiPlay, not a copy of an
installed production runtime. Archive:
`wine-crossover-11.0-1-osx64-signed.tar.xz`, SHA-256:
`89fa7e90fb626523a90d5867a03c6be785d017176739c6320a3b86c7838c3a35`.
The build SDK remains `v8.16-3shain`; successful probes below validate specific
operations against the newer runtime, not its entire private ABI.

## Why cloning alone was insufficient

The original code has independent fallbacks to
`~/Library/Application Support/MiPlay` in GameFileSystemRepository,
PersistenceStore, MediaCacheManager and LaunchCompatibilityEnvironment.
WineVersionManager derives WineVersions from that root; WineRuntimeProvider
derives `WinePrefixes/shared`, writes the display registry and stops its
wineserver. LaunchCompatibilityEnvironment patches the runtime, copies prefix
DLLs, moves game-bundled Vulkan files and generates wrapper apps. ProcessManager
inherits ambient Wine/renderer/injection settings. Those are actual source
paths, not assumptions based on the clone location.

The testing patch redirects those defaults, refuses external resolved bookmarks,
runtime paths, staging and filesystem writes, and checks child executable/cwd/
prefix ownership. System command-line tools and resources inside the separately
identified test app remain usable for existing fixtures. Named wrapper bundles
use a test-only identifier. Network sessions use ephemeral caches; icon work
directories and fixture temporary directories are test-owned. File logs and
the OSLog subsystem have separate identities.

Existing ancestors are resolved before checking non-existent output paths.
Dangling links and paths escaping the root are rejected. The first negative
test exposed Foundation's incomplete resolution of a missing descendant; one
identified temporary probe was created under `/tmp` and removed after verifying
its creation time and content. The corrected tests place negative probes in
DXMT-owned `guard-probes-dxmt` fixtures, and now pass without external writes.

This is application-level isolation, not a system-wide OS sandbox. macOS
maintains its own unified log, framework services, LaunchServices registrations
and the unique test application's preferences. No production MiPlay database,
Wine installation, prefix or game files are imported or written. Other
uncontrolled components and real game installations are not authorized inputs.

## DXMT integration contract

The renderer must contain the strict cache-isolation implementation introduced
by `2e87d69`. Preparation and MiPlay validation check both the package hashes
and the presence of the corresponding interface strings in dxgi.dll.

| Variable | Testing profile behavior |
| --- | --- |
| `MIPLAY_DXMT_TEST_ROOT` | Defaults to this clone's `state-dxmt`; cannot escape it |
| `DXMT_SHADER_CACHE_PATH` | Absolute owned AIR cache path |
| `DXMT_METAL_CACHE_PATH` | Absolute owned Metal framework cache path |
| `DXMT_REQUIRE_ISOLATED_CACHE=1` | Reject renderer startup if cache configuration cannot be isolated |
| `DXMT_LOG_PATH` | Owned renderer log directory |
| `WINEPREFIX` | Owned `AppSupport/WinePrefixes/shared`, or another owned fixture prefix |
| `TMPDIR`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`, `XDG_RUNTIME_DIR` | Owned state directories |
| `MIPLAY_DXMT_REAL_WINE` | Real synthetic Wine probe only when explicitly set by the runner |

Ambient WINE/DXMT/LSFG/DYLD settings are removed before assembling the child
environment. Explicit Metal HUD settings remain supported. LSFG is not enabled
or loaded by this integration profile. Default upstream DXMT cache behavior
remains unchanged unless the new strict mode is requested.

The old v0.80 package does not implement this contract and must not be passed
to the strict runner as a baseline. A later A/B experiment needs a baseline
with equivalent isolation, or a separately reviewed cache isolation mechanism.

## Reusable commands

Build the renderer with the existing [candidate flow](MIPLAY_BUILD.md), then:

```sh
python3 scripts/miplay_local_testing.py clone
# Apply the exported private integration patch if this is a new clean clone.
python3 scripts/miplay_local_testing.py prepare --candidate releases/dxmt-miplay-51f9dc30d7d3
python3 scripts/miplay_local_testing.py runtime
python3 scripts/miplay_local_testing.py preflight
python3 scripts/miplay_local_testing.py test
python3 scripts/miplay_local_testing.py probe
python3 scripts/miplay_local_testing.py export
```

The runtime command verifies the pinned download, uses safe extraction for a
new runtime, and preserves an existing recognized runtime. It refuses unknown
inputs. Preflight verifies profile, package, runtime architecture and ownership.
It is explicitly not a compatibility pass.

Tests use only this clone/project and its DerivedData. The probe compiles a
synthetic executable, boots the owned prefix through WineRuntimeProvider,
stops that prefix's server before staging, installs through the real MiPlay
staging function, checks all five installed files against the candidate,
dispatches a compute shader and verifies readback. Success must produce a fresh
`COMPUTE_RESULT=42`; a skipped test cannot be reported as a real probe pass.
Cleanup stops only the owned prefix's server and releases its lease. No global
pkill/killall, production runtime installation or real game invocation occurs.

The command lock prevents concurrent runner operations. To switch candidates,
use `prepare --candidate <new-package> --replace-candidate`: it refuses an
active test app/prefix, validates the incoming package, and preserves the old
directory in ArchivedCandidates. The next probe stages the new package. An
archived candidate can be selected with the same command for rollback. There
is no automatic deletion/reset of source, runtime, prefix or diagnostic state.
For a full rebuild, first confirm the owned app/server has stopped, preserve
the state directory as an archive, then prepare/download into a fresh state
directory; keep the independent Git clone and its commits.

The export command refuses dirty clone changes and writes a `git format-patch`
series plus hashes/provenance. These artifacts are ignored because they
contain private MiPlay source context. They can be transferred without copying
the complete testing directory; they are not uploaded or committed into the
public fork.

## Completed validation and limitations

- DXMT complete five-file x86_64 candidate built and verified:
  `51f9dc30d7d3`, including strict cache isolation.
- Five C++ regressions passed normally and with ASan/UBSan.
- Eleven Python package/environment tests passed, including symlink escape,
  production profile rejection, busy-state refusal and candidate backup.
- MiPlay Debug build passed. The automated suite executed 143 tests: 142
  passed, one real-Wine test deliberately skipped, no failures.
- Real Crossover Wine + DXMT compute probe passed on Apple M1 Pro. HLSL to
  DXBC, DXMT/AIR to Metal, dispatch, GPU readback and owned server cleanup were
  exercised. The final run also checked exact installed component contents.
- First real probe failed in Wine's HLSL compiler on StructuredBuffer store;
  the successful synthetic sample uses typed RWBuffer instead. Failed logs
  remain available. This was a harness/compiler limitation, not a historical
  game crash fix.
- AIR SQLite and Metal framework cache files were observed under the owned
  state paths. All five runtime component hashes matched the candidate;
  an owned-prefix `wineserver -w` completed after testing.

The initial environment phase performed no real-game tests. Subsequent
40/140-second shallow game process observations are recorded in the linked
reports. Explicit swapchain/Drawable/HDR tests, LSFG joint runs, long-duration
game stability tests and FPS/performance benchmarks remain unperformed. The probe
does not cover all D3D11 operations, multi-device teardown races or all Wine
private macdrv interfaces. CI execution remains a separate validation step.

## DXMT/LSFG joint work to coordinate later

No changes are requested in the LSFG checkout at this stage. Record these
interfaces for a future joint environment:

| DXMT location | Coordination needed |
| --- | --- |
| `src/dxmt/dxmt_presenter.cpp:154` | One owner for acquiring/presenting each drawable; explicit native fallback if frame generation is off/fails |
| `src/d3d11/d3d11_swapchain.cpp:739` | SyncInterval, preferred frame rate, queue latency and generated-frame cadence must be coordinated |
| `src/dxmt/dxmt_command_queue.cpp:99` | Producer completion, resource recycling and consumer synchronization must agree; CPU completion alone is insufficient |
| `src/d3d11/d3d11_texture_device.cpp:393` | Shared texture handles, format, lifetime and resize behavior need actual producer/consumer tests |
| `src/dxmt/dxmt_presenter.cpp:105` | HDR/EDR metadata, gamma and color conversion must not be applied twice |
| `src/winemetal/unix/winemetal_unix.c:1685` | Wine macdrv ABI and architecture/loading must match the joint runtime |

First add synthetic windowed Present/resize/minimize and graphics lifecycle
tests under the same isolation boundary. Then validate shared texture/fence
transfer and native behavior with frame generation disabled. Joint LSFG tests
require a separately prepared and authorized combined environment; they must
not reuse either fork's independent root while it is active.

## Formal MiPlay adoption checklist

1. Review the private patch commits independently; keep unique identities,
   hardcoded clone guards and synthetic fixtures confined to test profiles.
2. Generalize the owned storage/config injection behind a MiPlay environment
   interface before enabling a production integration path.
3. Consume the five-file manifest/version/hash contract and implement staging
   failure reporting, transactional rollback and install-while-idle checks in
   MiPlay. Current production staging is not promoted by these tests.
4. Add a clear policy for renderer generation, cache schema and Wine runtime
   compatibility; keep original runtime backups and complete package rollback.
5. Validate actual game copies, Drawable/Present, HDR, resource sharing, cold/warm
   frame-time distributions and long sessions before replacing production assets.
6. Design LSFG control/failure fallback in MiPlay orchestration, keeping rendering
   and synchronization implementation in the corresponding forks.

Modifying the formal MiPlay checkout, pushing MiPlay changes, replacing its
runtime/assets/prefix or operating on real game directories remains outside
this work's authorization. No such actions were performed.
