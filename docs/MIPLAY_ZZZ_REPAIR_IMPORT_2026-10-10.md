# MiPlay 绝区零修复同步记录（2026-10-10）

## 来源与合并判断

用户指定的正式 MiPlay 报告：
`/Users/stevetan/SteveTan/Document/Xcode/MiPlay/Docs/01-research/zzz-initialization-repair-2026-10-10.md`。
读取时 SHA256：`709783493cd0afbd9ba3412a83d34f4f9f9ea034a6fc0b87996875ea99a52262`。

报告说明：旧资源基线 `654f547` 中，`ArgumentEncodingContext::device_` 的声明晚于 `ClearUAV`，但后者构造时已通过 `getComputePipeline()` 读取它。未初始化的 handle 被用作 Objective-C Metal 接收对象。正确修复是上游 `fb4515681daefb789a4d0f403c4bdbca88f3b3de`，提前声明并初始化 `device_`，并非引用计数或 nil 防护。

该上游提交**已经是当前 DXMT Fork 的祖先**。当前 `src/dxmt/dxmt_context.hpp` 的 device 成员位于命令辅助对象之前，`src/dxmt/dxmt_context.cpp` 的初始化列表也首先初始化 device。对 MiPlay 提供的 `fb45156-device-initialization.patch` 执行 `git apply --reverse --check` 成功，确认补丁已完整存在。没有重复 cherry-pick、空提交或再次移动成员。

这处历史游戏崩溃与之前本 Fork 解决的严格 Metal 缓存初始化时机问题是两个独立问题。后者不能作为前者的根因或修复证明。

## 本次移植

### DXMT Fork

`tests/integration/dxmt_device_repro.c` 源自 MiPlay 的 `Tools/DXMT/device_repro.c`：循环 40 次创建设备、Flush、释放 context/device，在每次之前合法分配、写入非零数据并释放 256 个堆块。写入发生在释放前，没有越界或释放后写。使用 volatile 写入，确保优化器保留用于堆复用观察的填充操作。

原复现固定堆块大小 `0x10410`，与原 DXMT 基线 DWARF 一致。新 `scripts/miplay_device_repro.py` 使用当前构建的 `compile_commands.json` 和同一 x86_64 Windows 编译器生成 LLVM IR，读取实际 `sizeof(dxmt::CommandQueue)`，再将其作为 C 编译参数。本次自动计算 **66,576 字节（0x10410）**，恰好相同，后续不依赖此硬编码值。编译前要求当前 src/include/libs 与候选的源码 commit 无差异，避免使用新源码布局去测试旧候选二进制。

新增命令：

```sh
python3 scripts/miplay_local_testing.py device-probe
```

命令通过原有独占测试会话锁、五件套验证与 owned Runtime/Prefix 运行；编译命令、类布局大小、源程序及 exe 哈希记录在 `state-dxmt/Tests/device-repro-build.json`。报告必须含新的完整 40 次完成标记，跳过测试不能算通过。

堆填充仅增加分配器复用非零内容的机会，不保证每个 CommandQueue 都复用这些块。此轮没有回退 Fork 构建未修复控制组，不能把通过本身当成新的 A/B 因果证明；上游原补丁及 MiPlay 报告的旧→新→旧→新实验提供该来源证据。

本次按 Fork 已有构建流程重建完整五件套及可选缓存引导库：
`releases/dxmt-miplay-da047dc488a5`，源提交 `da047dc488a5c0be22406ee4b205849b05442c42`。
版本、构建选项、所有组件 SHA256 均在清单中。没有复制 MiPlay 报告中基于旧 `654f547` 的七件套，也没有启用本阶段未验证的 NVAPI/NVNGX/DLSS 配置。

### 独立 MiPlay-DXMT 副本

从正式工程的工作树中**仅提取**报告涉及的退出清理所有权修改与对应单元回归，移植至 `.local-testing/MiPlay-DXMT`，保留全部已有隔离约束：

- `LaunchOrchestrator` 保存带会话 ID 的监控任务。
- 监控启动后，由同一任务唯一提交退出状态并释放 Prefix lease；主动停止等待它完成。
- 旧会话不能清除新会话的游戏标识。
- 预启动失败仍走原清理，提交失败保留恢复守卫。
- 重复停止后再次启动的回归与自然退出回归保留。

未整文件覆盖正式工程的新启动编排，也未引入它的 NVEXT、webview、网络窗口、生产游戏验收入口或共享正式游戏路径。它们超出本次初始化缺陷与清理竞态的迁移范围。

新增独立真实 Wine 用例 `testDXMTRepeatedDeviceInitialization`，与原 GPU compute 用例共享受隔离检查保护的 staging/启动/结束代码。设备复现**不设置 `DYLD_INSERT_LIBRARIES`，不加载缓存引导或异常诊断探针**；严格缓存隔离仍启用，DXGI 在这个纯 D3D11 程序中足够早地设置路径。按此前用户要求，测试环境显式启用 Metal HUD；没有 swapchain/呈现时不以 HUD 帧率作结论。

## 验证与证据边界

- 完整候选交叉构建成功；6 项原生回归、16 项 Python 回归通过，组件架构、哈希和系统依赖检查通过。
- 真实设备回归 `device-probe-20261010T120615`：40 次 begin / created / released，完整完成标记存在，测试退出码 0。
- 移植退出清理后的首轮 MiPlay 单测 `unit-20261010T120213`：145 项中 143 通过、2 项按设计跳过，0 失败；重复停止及连续重启用例实际通过。
- 真实 GPU compute `wine-probe-20261010T120657` 通过，`COMPUTE_RESULT=42`。
- 最终完整 MiPlay 单测 `unit-20261010T120900`：146 项中 143 通过、3 项按设计跳过（显式启用的 compute、设备复现与游戏启动），0 失败。设备复现及 compute 已另行实际执行通过。

MiPlay 来源报告记录了其生产启动路径五次进入角色场景并运行至少 180 秒的验收。本次将其记为**MiPlay 侧报告结论**；没有重复这些游戏内操作，也没有把本 Fork 的设备回归或 XCTest 成功等同于本 Fork 的五轮真实游戏验收。其他游戏、DLSS 和长时间战斗未在本次验证。

正式 MiPlay 工程、正式 Runtime/Prefix/游戏文件和 LSFG 工程均未改动。新候选仅暂存到 DXMT 专用测试 Runtime，测试副本的 origin push 仍禁用。

## 本地提交与迁移

- 已有上游核心修复：`fb451568`。
- DXMT 回归接入：`da047dc`。
- MiPlay-DXMT 清理修复和回归：`d1ff894`。
- MiPlay-DXMT 设备复现集成：`2ce6f22`。

独立 MiPlay 改动可通过 `miplay_local_testing.py export` 导出累计补丁，也可从上述两个新提交单独导出，避免把正式项目已经修复的清理代码重复应用。所有提交仅本地保存，未向任何远端推送。
