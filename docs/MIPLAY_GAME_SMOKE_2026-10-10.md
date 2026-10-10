# MiPlay-DXMT 单线启动观察（2026-10-10）

后续已实现并验证早期 Metal 缓存配置，带 HUD 的复测结果见 [缓存初始化修复报告](MIPLAY_METAL_CACHE_INITIALIZATION.md)。本文件保留初始候选的原始结论。

## 范围与隔离

仅测试游戏启动后的进程存活状态：每两秒采样，在 40 秒和 140 秒写入检查点。没有登录、点击、游戏内操作或性能测量。存活不能证明画面正确、游戏内兼容性或长期稳定性。

使用 `.local-testing/MiPlay-DXMT`，不会复用 LSFG 或其他工作区的副本。独立下载的 Wine Runtime、Prefix、候选 DXMT 五件套、缓存、日志均在 `state-dxmt`。游戏来自本机已有完整安装，通过 APFS `clonefile` 创建独立 inode 的写时复制副本，拒绝源树中的符号链接。不会使用硬链接，也不会从原游戏目录启动。复制失败时保留部分副本并停止。

运行前将 Prefix 的用户目录链接改到 `state-dxmt/Home`，将 Z: 从系统根目录改为 `state-dxmt`；原神 Steam 存根参数相应使用 `Z:\Games\GenshinImpact\YuanShen.exe`。这仅是测试配置。Wine 并非操作系统安全沙箱；Rosetta、系统日志等仍由 macOS 管理。

逐个取得 MiPlay shared-prefix lease，准备 Prefix、停掉该 Prefix 的 Wine 服务、使用实际 `LaunchCompatibilityEnvironment.stage` 和 `launchInvocation`、核对安装的五件套与候选一致，再通过 `ProcessManager` 启动。原神使用 MiPlay 的 Steam 存根和 ESYNC，绝区零使用 MSYNC；不启用 LSFG、MetalFX、解锁帧率等性能选项。140 秒记录完成后才主动关闭该测试 Prefix 并恢复副本中的 Vulkan 文件，再开始下一个游戏。主动关闭不算闪退。

实际游戏与启动器分别记录。Wine 会改写进程参数，`ps eww` 无法可靠提供 WINEPREFIX；最终监测使用游戏 exe 名称、`lsof` 确认工作目录属于独立游戏副本、映射文件来自独立 Runtime，排除 Steam 启动器。日志保留每次采样、检查点 UTC 时间、实际间隔、游戏 PID、启动器状态、清理时间与启动器退出码。启动器退出码不等同于游戏退出码。

## 版本与重现

候选包为 `dxmt-miplay-51f9dc30d7d3`，源版本 `51f9dc30d7d355c234265c187d884cf3952d0ee0`；没有覆盖 MiPlay 正式 v0.80 资产。Wine 为 `wine-crossover-11.0-1-signed`，下载文件 SHA256 及各组件哈希沿用独立环境的清单。主机为 Apple M1 Pro，通过 x86_64 Wine/Rosetta 运行。MiPlay 测试提交 `dab976a`（基于原仓库 `00f97b3`）。

在 DXMT 工程目录执行：

```sh
python3 scripts/miplay_game_smoke.py --genshin '/完整原神安装目录' --zzz '/完整绝区零安装目录'
```

第一次创建副本；后续可添加 `--reuse-copies`，只允许来源及源文件清单与复制记录相符的副本，并复核 exe 哈希、独立 inode 与无符号链接。现有副本不会被覆盖。脚本通过独占会话锁禁止并行测试。测试配置、源文件大小/mtime/inode 清单和 exe 哈希保留在忽略的测试目录；不会提交私有文件。

## 结果

最终有效轮次：`games-20261009T173246`。所有时间为北京时间（UTC+8），采样延迟约 0.22–0.29 秒。

| 游戏 | 40 秒 | 140 秒 | 时间（40s / 140s） | 限制 |
| --- | --- | --- | --- | --- |
| 原神 | 存活，PID 84269；未观察到闪退 | 存活，PID 84269；未观察到闪退 | 01:33:32 / 01:35:12 | 确认映射候选 d3d11.dll、dxgi.dll、winemetal.so；未验证画面或游戏内功能 |
| 绝区零 | 存活，PID 84692；未观察到闪退 | 存活，PID 84692；未观察到闪退 | 01:35:53 / 01:37:33 | 严格缓存隔离拒绝 DXMT 初始化，不能记为渲染器启动成功 |
| 星穹铁道 | 未执行 | 未执行 | — | 未找到完整安装 |

绝区零日志出现三次 `Failed to set Metal cache path` / `Metal cache configuration rejected; refusing an unisolated renderer startup`。对应 `src/dxgi/dxgi.cpp` 的 DllMain 返回失败；`src/winemetal/unix/cache.c` 调用私有 Metal setter 后核对 getter，核对未通过。日志在此之前包含 MoltenVK 初始化信息，**推测**早期 Vulkan/Metal 初始化可能影响路径设置时机；实际原因需要补充 getter 的实际返回路径及初始化时序诊断，尚未确认。未关闭严格隔离保护，也未进行非隔离重试。后续需优先处理这一集成阻塞；这一轮不能证明绝区零使用候选 DXMT 成功呈现，进程存活也可能仅是错误界面或等待状态。亦不能证明此前其他 Metal 使用没有访问 macOS 管理的默认缓存。

每个游戏 140 秒检查点之后都进行了主动关闭，Prefix 服务已退出，副本中暂移的 Vulkan 文件已恢复。启动器关闭后退出码分别为 1（原神）和 0（绝区零）；这是主动清理之后获取的启动器结果，不能据此判断检查点发生游戏闪退。

原安装目录完整文件清单（inode、大小、mtime）与主程序 SHA256 在测试前后相同。没有修改正式 MiPlay 工程、Runtime、Prefix、DXMT v0.80 资产或 LSFG 工程。游戏运行只针对 DXMT 专用副本。

自动化验证：此次 XCTest 启动观察用例完成（仅证明测试流程完成）；MiPlay 全套 144 项中 142 通过、2 项按设计跳过（GPU probe 与真实游戏用例需显式启用），0 失败；DXMT 的 Python 隔离/复制/打包测试 14 项通过。没有重复构建 DXMT，本轮使用已生成的候选包；MiPlay 测试程序已重新构建。

有效原始结果保留于 `.local-testing/results-dxmt/games-20261009T173246.{json,log,xcresult}`，完整游戏日志及检查点保留于 `state-dxmt/Logs/game-smoke-*`；自动化套件结果为 `unit-20261009T173812`。

前置两次记录不作为游戏测试结论：第一次配置使用了错误的 GameType 大小写，在游戏启动前停止；第二次监测器依赖 Wine 不提供的进程环境信息，出现存活误报，主动中止并恢复副本。失败日志与 xcresult 保留，第二次报告标记为 `invalid-monitor-*`。最终轮次使用修正后的目录及 Runtime 归属检查重新计时。

## 后续人工验证

用户负责游戏内深度测试：登录与场景加载、持续运行、切换场景、画面/HDR、帧节奏及性能。此轮不声称修复历史闪退，也不验证 DXMT 与 LSFG 的共同呈现、同步或关闭回退。正式迁移前仍需这些验证。
