"""
完整 UDS 诊断流程（虚拟 CAN + 本仓库 EcuSim）

顺序：
  1) 切扩展会话  0x10 03
  2) 安全访问    0x27 01 / 0x27 02
  3) 读数据      0x22
  4) 写数据      0x2E
  5) 读故障码    0x19
  6) 例程控制    0x31

运行（在 src 目录）：
  python diag_flow.py
"""
from __future__ import annotations

import struct
import sys
import time

import can

from bus_util import ID_DIAG_REQ, ID_DIAG_RESP, open_bus, sf_uds
from ecu_sim import EcuSim, calc_key


def wait_resp(bus: can.BusABC, timeout: float = 1.0) -> can.Message | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=0.05)
        if msg is None:
            continue
        if msg.arbitration_id == ID_DIAG_RESP:
            return msg
    return None


def send_uds(bus: can.BusABC, *payload: int) -> can.Message | None:
    frame = sf_uds(*payload)
    req = can.Message(arbitration_id=ID_DIAG_REQ, data=frame, is_extended_id=False)
    bus.send(req)
    print(f"  TX  {req.arbitration_id:03X}  {bytes(req.data).hex(' ')}")
    resp = wait_resp(bus)
    if resp is None:
        print("  RX  (timeout)")
        return None
    print(f"  RX  {resp.arbitration_id:03X}  {bytes(resp.data).hex(' ')}")
    return resp


def is_positive(resp: can.Message | None, sid: int) -> bool:
    if resp is None or len(resp.data) < 2:
        return False
    return resp.data[1] == (sid + 0x40)


def is_nrc(resp: can.Message | None, sid: int | None = None) -> bool:
    if resp is None or len(resp.data) < 4:
        return False
    if resp.data[1] != 0x7F:
        return False
    if sid is not None and resp.data[2] != sid:
        return False
    return True


def step(title: str) -> None:
    print(f"\n=== {title} ===")


def run_flow(bus: can.BusABC) -> bool:
    ok_all = True

    # 1) 切扩展会话 DiagnosticSessionControl
    step("1) 切扩展会话  0x10 03")
    resp = send_uds(bus, 0x10, 0x03)
    ok = is_positive(resp, 0x10) and resp is not None and resp.data[2] == 0x03
    print("  ->", "PASS" if ok else "FAIL")
    ok_all &= ok

    # 2) 安全访问 SecurityAccess：先要种子，再回密钥
    step("2) 安全访问  0x27")
    resp = send_uds(bus, 0x27, 0x01)  # requestSeed
    if not is_positive(resp, 0x27) or resp is None:
        print("  -> FAIL (requestSeed)")
        ok_all = False
    else:
        seed = struct.unpack(">I", bytes(resp.data[3:7]))[0]
        key = calc_key(seed)
        print(f"  seed=0x{seed:08X}  key=0x{key:08X}")
        key_bytes = struct.pack(">I", key)
        resp = send_uds(bus, 0x27, 0x02, *key_bytes)
        ok = is_positive(resp, 0x27)
        print("  ->", "PASS" if ok else "FAIL (sendKey)")
        ok_all &= ok

    # 3) 读数据 ReadDataByIdentifier（扩展会话下读 VIN）
    step("3) 读数据  0x22 F190")
    resp = send_uds(bus, 0x22, 0xF1, 0x90)
    ok = is_positive(resp, 0x22)
    if ok and resp is not None:
        print(f"  DID data: {bytes(resp.data[4:8]).hex(' ')}")
    print("  ->", "PASS" if ok else "FAIL")
    ok_all &= ok

    # 4) 写数据 WriteDataByIdentifier（需已解锁）
    step("4) 写数据  0x2E F195")
    resp = send_uds(bus, 0x2E, 0xF1, 0x95, 0x0A, 0x0B)
    ok = is_positive(resp, 0x2E)
    print("  ->", "PASS" if ok else "FAIL")
    ok_all &= ok
    # 读回校验
    resp = send_uds(bus, 0x22, 0xF1, 0x95)
    ok_readback = (
        is_positive(resp, 0x22)
        and resp is not None
        and resp.data[4] == 0x0A
        and resp.data[5] == 0x0B
    )
    print("  读回校验:", "PASS" if ok_readback else "FAIL")
    ok_all &= ok_readback

    # 5) 读故障码 ReadDTCInformation
    step("5) 读故障码  0x19 02")
    resp = send_uds(bus, 0x19, 0x02, 0xFF)
    ok = is_positive(resp, 0x19)
    if ok and resp is not None:
        dtc = bytes(resp.data[4:7])
        status = resp.data[7]
        print(f"  DTC={dtc.hex(' ')}  status=0x{status:02X}")
    print("  ->", "PASS" if ok else "FAIL")
    ok_all &= ok

    # 6) 例程控制 RoutineControl：启动 + 查结果
    step("6) 例程控制  0x31")
    resp = send_uds(bus, 0x31, 0x01, 0xFF, 0x00)  # startRoutine
    ok_start = is_positive(resp, 0x31)
    print("  start:", "PASS" if ok_start else "FAIL")
    resp = send_uds(bus, 0x31, 0x03, 0xFF, 0x00)  # requestRoutineResults
    ok_result = is_positive(resp, 0x31)
    if ok_result and resp is not None:
        print(f"  result status=0x{resp.data[5]:02X}")
    print("  result:", "PASS" if ok_result else "FAIL")
    ok_all &= ok_start and ok_result

    return ok_all


def main() -> int:
    bus_ecu = open_bus()
    bus_test = open_bus()
    ecu = EcuSim(bus_ecu)
    ecu.start()
    time.sleep(0.1)
    try:
        print("完整诊断流程开始（虚拟 CAN）")
        print(f"请求 ID=0x{ID_DIAG_REQ:03X}  响应 ID=0x{ID_DIAG_RESP:03X}")
        passed = run_flow(bus_test)
        print("\n=== 流程结束:", "全部通过" if passed else "存在失败", "===")
        return 0 if passed else 1
    finally:
        ecu.stop()
        bus_ecu.shutdown()
        bus_test.shutdown()


if __name__ == "__main__":
    sys.exit(main())
