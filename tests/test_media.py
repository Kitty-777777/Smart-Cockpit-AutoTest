import sys
import time
from pathlib import Path

import can
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bus_util import open_bus  # noqa: E402
from ecu_sim import EcuSim  # noqa: E402

# 假设我们在 DBC 里定义的控制面板 ID 和 媒体数据 ID
ID_CONTROL = 0x400
ID_MEDIA_DATA = 0x300


@pytest.fixture(scope="module")
def bus_ecu():
    bus = open_bus()
    yield bus
    bus.shutdown()


@pytest.fixture(scope="module")
def ecu(bus_ecu):
    sim = EcuSim(bus_ecu)
    sim.start()
    time.sleep(0.1)
    yield sim
    sim.stop()


@pytest.fixture(scope="module")
def bus_test(ecu):
    bus = open_bus()
    yield bus
    bus.shutdown()


def get_media_status(bus, timeout=1.0):
    """从总线抓取当前 MediaStatus 信号（丢掉积压旧帧，取下一帧）"""
    while bus.recv(timeout=0.0) is not None:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=0.05)
        if msg is not None and msg.arbitration_id == ID_MEDIA_DATA:
            return msg.data[0]  # 信号在第一个字节
    return None


def test_play_music(bus_test):
    """P0: 点击播放后，总线信号变为 1"""
    # 1. 发送控制指令：按播放
    bus_test.send(can.Message(arbitration_id=ID_CONTROL, data=[0x01], is_extended_id=False))

    # 2. 等待并检查 MediaStatus 信号
    time.sleep(0.2)  # 给 ECU 一点反应时间
    status = get_media_status(bus_test)

    assert status == 1, f"预期 MediaStatus=1，实际得到 {status}"


def test_pause_music(bus_test):
    """P0: 点击暂停后，总线信号变为 0"""
    # 确保先处于播放状态
    bus_test.send(can.Message(arbitration_id=ID_CONTROL, data=[0x01], is_extended_id=False))
    time.sleep(0.2)

    # 发送暂停指令
    bus_test.send(can.Message(arbitration_id=ID_CONTROL, data=[0x00], is_extended_id=False))
    time.sleep(0.2)

    status = get_media_status(bus_test)
    assert status == 0, f"预期 MediaStatus=0，实际得到 {status}"
