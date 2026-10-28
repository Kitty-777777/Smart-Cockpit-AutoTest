# Smart-Cockpit-AutoTest

基于虚拟 CAN 总线的智能座舱自动化测试框架（Python / pytest / python-can / UDS）。

🌟 [测试报告：点击这里查看可视化 HTML 报告](./report.html)

## 功能

- 周期报文（类似 IG）
- DBC 编解码（类似 Trace 信号）
- 单帧 UDS 自动化（会话、安全访问、读/写 DID、DTC、例程）
- 座舱媒体 P0：车机按键 `0x400` → 功放状态 `0x300 MediaStatus`

## 安装

```bash
python -m pip install -r requirements.txt
```

## 运行测试

```bash
python -m pytest tests/test_media.py -v --html=report.html --self-contained-html
python -m pytest -q
```

完整诊断流程演示：

```bash
python src/diag_flow.py
```

只跑 ECU 仿真：

```bash
python src/ecu_sim.py
```

有真实 USB-CAN 时，改 `src/bus_util.py` 里 `open_bus()` 的 `interface` / `channel` 即可接到硬件。DBC 路径使用相对路径：`Path(__file__).resolve().parents[1] / "dbc" / "Practice.dbc"`。

## 目录

| 路径 | 作用 |
|------|------|
| `dbc/Practice.dbc` | 练习数据库 |
| `src/bus_util.py` | 虚拟总线 / UDS 单帧工具 |
| `src/ecu_sim.py` | ECU：周期帧 + UDS + 媒体状态 |
| `src/diag_flow.py` | 完整诊断流程演示 |
| `tests/test_media.py` | 播放/暂停 P0 用例 |
| `tests/test_uds_auto.py` | UDS 自动化套件 |
| `report.html` | pytest-html 可视化报告 |
| `TestReport.md` | Markdown 测试总结 |
| `INTERVIEW.md` | 简历 STAR 表述与面试题 |

## 简历项目经历（STAR）

**项目名称：** 基于虚拟 CAN 总线的智能座舱自动化测试框架  
**技术栈：** Python, Pytest, python-can, cantools, UDS

- **架构设计：** 基于 python-can 搭建虚拟总线，通过 EcuSim 模拟 ECU 周期报文与 UDS 诊断响应，实现脱离真实硬件的闭环测试。
- **接口自动化：** pytest + fixture 管理生命周期，覆盖 0x10 / 0x27 / 0x22 等诊断服务。
- **座舱业务测试：** 模拟车机控制面板（0x400）发指令，断言 ECU 媒体状态（0x300 MediaStatus），覆盖蓝牙音乐播放/暂停 P0。
- **报告输出：** pytest-html 可视化报告；DBC 解析物理值与原始报文断言。
