# MiPlay-DXMT Metal 缓存初始化修复

2026-10-10，独立 MiPlay-DXMT 测试环境，Apple M1 Pro / macOS 27.2 / x86_64 Wine（Rosetta）。

## 原因与证据

DXMT 的 `src/dxgi/dxgi.cpp:InitializeMetalCachePath` 在 DXGI DLL 初始化时才调用 `WMTSetMetalShaderCachePath`。绝区零日志在此之前已经出现 MoltenVK 初始化信息，失败后实际 Metal 缓存路径仍为 macOS 的 CrossOver wineloader 默认缓存目录，未变为指定的 `state-dxmt/Caches/Metal`。严格隔离检查正确地拒绝了 DXGI 初始化。

在本机的独立 x86_64 原生程序中复现：

- 首先调用 `MTLSetShaderCachePath(ownedPath)`，首次 getter 返回 ownedPath。
- 设备枚举之后再次设置另一个目录，getter 仍返回原目录。
- 更早的首次 getter 本身也会固定缓存路径，之后再 setter 同样不能更改。

因此这是一项**缓存首次访问时机**的集成问题。与绝区零日志的早期 Vulkan/Metal 初始化顺序吻合。尚未追踪游戏内部具体哪个调用第一次触发 Metal 缓存初始化；不能把某个 MoltenVK 内部函数认定为已证实的直接调用者。

诊断版本 `7b0c6d7` 曾在 setter 前读取 getter，诊断本身可能改变首次初始化时机。此副作用已在 `d320630` 移除，最终诊断仅在 setter 之后读取实际路径并在失败时记录。该诊断版本不能用于评估正常初始化行为，未推广到正式运行环境。

## 实现与接口契约

`src/winemetal/unix/cache_bootstrap.m` 提供小型原生启动引导库。MiPlay 显式将经过验证的库路径传入 Wine 的 `DYLD_INSERT_LIBRARIES`，使它在 Wine 进入游戏代码前执行：

1. 仅在 `DXMT_REQUIRE_ISOLATED_CACHE=1` 时启用。
2. 要求 UTF-8 绝对 `DXMT_METAL_CACHE_PATH`，创建目录失败则退出。
3. 先 setter 再 getter，绝不为诊断在 setter 前取值。
4. 核对实际路径必须与请求路径完全一致；失败立即退出码 78，阻止在默认 Metal 缓存下继续运行。
5. DXGI 仍保留原有严格核对，不放松保护。

原有五件套保持完整，普通使用者不依赖启动引导库，未设置严格模式时引导库不执行配置。新增的可选资产为 `integration/dxmt-cache-bootstrap.dylib`，针对 x86_64 Wine 编译，最低部署参数 macOS 14.0，链接系统 Foundation/Metal。构建和打包流程记录其架构、大小、SHA256、系统依赖；清单新增可选 `integration_files`，仍兼容只有五件套的旧包。

MiPlay-DXMT 测试副本新增 `DXMTLocalTesting.cacheBootstrapPath()`，先核对候选清单及引导库哈希、大小、架构标识和路径归属，再为真实 Wine compute / 游戏启动用例显式注入。不会继承其他项目的 DYLD 注入路径。

候选：`releases/dxmt-miplay-91a67dbf9dd3`；DXMT 源提交 `91a67dbf9dd3`。MiPlay 测试集成提交 `1604d41`，Metal HUD 设置提交 `c0021f8`。构建日志及全部文件哈希保留于候选清单和 `build/miplay-candidate`。

## 隔离与测试流程

游戏测试始终使用独立 APFS 写时复制副本，拒绝符号链接/共享 inode。Prefix 的用户目录链接和 Z: 仅指向测试目录。正式安装目录的运行数据在这轮开发期间发生了外部变化；原保护机制拒绝按旧来源清单重新启动。保留旧副本后创建过一次新绝区零副本，后续使用 `--owned-game` 完全在已有测试副本中运行，不再访问或同步正式游戏目录。

新副本模式记录独立副本来源清单、来源主程序哈希与复制记录哈希，复核 exe 独立 inode、大小和哈希，并记录测试开始时的副本文件清单。结果明确标记 `source_comparison_performed=false`、`source_installations_unchanged=null`，不会声称重新比较过动态变化的正式目录。

串行运行，每两秒采样实际游戏进程，在 40 / 140 秒保存检查点，然后才主动关闭该测试 Prefix 并恢复副本 staging 文件。原神仍使用 MiPlay Steam 存根 / ESYNC，绝区零使用 MSYNC。按用户要求设置 `MTL_HUD_ENABLED=1`；Metal HUD 开启时会有监测开销，此轮不进行性能比较。没有登录、点击、游戏内场景操作、帧率或性能结论。

```sh
python3 scripts/miplay_local_testing.py prepare \
  --candidate releases/dxmt-miplay-91a67dbf9dd3 --replace-candidate
python3 scripts/miplay_local_testing.py probe
python3 scripts/miplay_game_smoke.py \
  --owned-game GenshinImpact --owned-game ZenlessZoneZero
```

## 验证结果

- 完整五件套及引导库交叉构建、架构/哈希/系统依赖检查通过。
- 原生回归测试 6 项通过，ASan/UBSan 6 项通过。新增用例包含在首次 getter / 设备枚举前配置缓存、空路径和相对路径的失败关闭，以及包含空格和中文的路径。
- Python 测试 16 项通过，包括引导库完整性检测、仅引导库变化时的候选替换、独立副本模式不会读取正式安装目录。
- 真实 Wine GPU compute 探针通过，`COMPUTE_RESULT=42`，结果 `wine-probe-20261010T010412`。
- 无 HUD 的绝区零修复验证：40.27s 与 140.20s 均存活，加载候选 DXGI/D3D11/winemetal 与引导库；完整日志没有 Metal 缓存拒绝错误。结果 `games-20261010T010531`，对应北京时间 09:06:14 / 09:07:54。
- 带 Metal HUD 的串行回归 `games-20261010T010905`：

| 游戏 | 40 秒 | 140 秒 | 北京时间（40s / 140s） | 缓存拒绝错误 |
| --- | --- | --- | --- | --- |
| 原神 | 存活，PID 98677 | 存活，PID 98677 | 09:09:51 / 09:11:31 | 无 |
| 绝区零 | 存活，PID 99107 | 存活，PID 99107 | 09:12:13 / 09:13:53 | 无 |

两进程均设置 `MTL_HUD_ENABLED=1` 并映射系统 `libMTLHud.dylib`，加载证据保存于 `Logs/*-hud-mapped.txt`。未进行屏幕截图或目视确认 HUD 排版；不根据库加载声称获取了 FPS 数据。检查点实际延迟约 0.20–0.31 秒。绝区零全部 70 次采样保持存活；原神的前两次（2s / 4s）采样尚未发现游戏子进程，自 6s 起的采样均保持存活。这是启动器与游戏子进程建立的间隔，不记作闪退。结束后的关闭为主动清理，不算闪退。完整日志保存于 `state-dxmt/Logs/game-smoke-*`；此前无 HUD 版本已归档，未覆盖历史结果。

MiPlay 全套单元测试 `unit-20261010T011439`：144 项中 142 通过、2 项按设计跳过（GPU 和游戏用例需显式启用），0 失败。前面的显式 compute 与带 HUD 游戏测试均实际执行，未被跳过。

所有候选只安装到独立 Runtime，未替换 MiPlay 正式 DXMT v0.80，也未修改正式 MiPlay 或 LSFG 工程。没有断言修复历史游戏崩溃。

## 正式 MiPlay 配套修改与剩余验证

这次已落地到 DXMT 构建产物和 MiPlay 测试流程；正式 MiPlay 尚未修改。后续正式集成需要：

- 将可选引导库和清单随资产分发，安装/迁移时验证架构、大小和 SHA256。
- 在**实际 x86_64 Wine exec 边界**设置经过验证的 `DYLD_INSERT_LIBRARIES`、严格开关和两个缓存绝对路径；不可直接把 x86_64 dylib 注入 arm64 的 MiPlay 或启动包装器。
- 若使用命名 `.app` / GameLauncher 路径，包装器需把专用参数转成 Wine exec 时的注入环境；本轮实际运行测试使用 ProcessManager 直接启动 Wine，尚未验证 LaunchServices 命名包装器链。
- 保留 DXGI 的核对和启动失败诊断；处理退出码 78，向用户提供明确错误而非静默回退。
- 在签名/公证/正式分发环境确认 dyld 注入许可和库签名要求。只有本机隔离环境验证，不等同于完整发行兼容性。
- 联合 LSFG 时确认初始化顺序、同一进程注入策略与缓存路径一致；本轮没有启用或修改 LSFG。

用户的游戏内深度测试应在这份候选及对应启动编排配置下进行；长期运行、画面、HDR、切换场景、性能和历史闪退仍未验证。游戏进程存活与组件加载不等同于呈现正确。

## 本地提交与移交

DXMT：`7b0c6d7` 初始诊断，`d320630` 去除诊断 getter 副作用，`91a67db` 启动引导库/构建/回归测试，`3267231` 独立游戏副本测试与集成资产完整性检查。MiPlay-DXMT：`1604d41` 校验并加载引导库，`c0021f8` 启用 Metal HUD。所有修改仅保留为本地提交，没有推送。MiPlay 补丁仍通过 `miplay_local_testing.py export` 从原始克隆 commit 导出，位于忽略的 `artifacts-dxmt`，不需要复制整个测试目录进行迁移。
