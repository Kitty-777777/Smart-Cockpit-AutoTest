# 简历项目经历（可直接粘贴）

**基于虚拟 CAN 总线的智能座舱自动化测试框架**  
技术栈：Python、Pytest、python-can、cantools、UDS  
GitHub：https://github.com/Kitty-777777/Smart-Cockpit-AutoTest

- 针对实车/台架成本高、状态难复现的问题，基于 python-can 搭建虚拟 CAN 总线，自研 EcuSim 模拟 ECU 周期报文与 UDS 诊断响应，实现脱离硬件的闭环自动化测试。
- 使用 Pytest + Fixture 管理 ECU 启停与总线生命周期，覆盖 UDS 核心服务：0x10 会话控制、0x27 安全访问、0x22 读 DID、0x2E 写数据、0x19 读故障码、0x31 例程控制，并用 NRC 校验异常路径。
- 模拟车机控制面板（CAN ID 0x400）下发播放/暂停，断言功放媒体状态报文（0x300 MediaStatus）0/1 状态流转，完成蓝牙媒体 P0 主流程自动化；DBC 解析物理值后断言，避免只比对原始字节。
- 集成 pytest-html 输出可视化报告，P0 媒体用例 2 条全部通过（通过率 100%），报告见仓库 `report.html`。

---

## STAR 拆解（面试口述用）

| 要素 | 内容 |
|------|------|
| **S 情境** | 智能座舱媒体/诊断功能依赖实车或 CANoe，环境贵、排期紧，回归不稳定。 |
| **T 任务** | 在无实车条件下，把 UDS 诊断和蓝牙媒体播放/暂停做成可重复的自动化闭环。 |
| **A 行动** | 虚拟总线 + EcuSim；Pytest fixture 管生命周期；0x400 指令驱动、0x300 信号断言；DBC + pytest-html 出报告。 |
| **R 结果** | P0 播放/暂停 2 条用例 100% 通过；诊断主流程可一键跑通；项目已公开在 GitHub。 |

ADB / Appium 端到端尚未落地，面试时不要写成已完成；可放在「后续规划」。
