"""
按响应结果决定是否进入下一步：
  切扩展会话 → 安全访问 → 读数据 → 写数据 → 读故障码 → 例程控制

本脚本会同时拉起虚拟 ECU，否则 virtual 总线上无人应答。
"""
import struct
import time

import can

from bus_util import ID_DIAG_REQ, ID_DIAG_RESP, open_bus, sf_uds
from ecu_sim import EcuSim, calc_key


def recv_diag(bus, timeout=1.0):
    """只收诊断响应 ID。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=0.05)
        if msg is not None and msg.arbitration_id == ID_DIAG_RESP:
            return msg
    return None


def send_and_wait(bus, *payload):
    request = can.Message(
        arbitration_id=ID_DIAG_REQ,
        data=sf_uds(*payload),
        is_extended_id=False,
    )
    bus.send(request)
    print(f"TX {bytes(request.data).hex(' ')}")
    response = recv_diag(bus)
    if response is None:
        print("未响应")
        return None
    print(f"RX {bytes(response.data).hex(' ')}")
    return response


# 两端虚拟总线（同 channel 才能互通）
bus_ecu = open_bus()
bus = open_bus()
ecu = EcuSim(bus_ecu)
ecu.start()
time.sleep(0.1)

try:
    # 1) 切扩展会话  请求 0x10 03 → 肯定响应 0x50
    response = send_and_wait(bus, 0x10, 0x03)
    if response is not None and response.data[1] == 0x50:
        print("肯定响应：扩展会话成功")

        # 2) 请求种子  0x27 01 → 肯定响应 0x67
        response = send_and_wait(bus, 0x27, 0x01)
        if response is not None and response.data[1] == 0x67:
            print("种子请求成功")
            seed = struct.unpack(">I", bytes(response.data[3:7]))[0]
            key = calc_key(seed)
            key_bytes = struct.pack(">I", key)

            # 3) 发送密钥  0x27 02 → 肯定响应 0x67
            response = send_and_wait(bus, 0x27, 0x02, *key_bytes)
            if response is not None and response.data[1] == 0x67:
                print("解锁成功")

                # 4) 读数据  0x22 F190 → 肯定响应 0x62
                response = send_and_wait(bus, 0x22, 0xF1, 0x90)
                if response is not None and response.data[1] == 0x62:
                    print("读数据成功")
                else:
                    print("读数据失败")

                # 5) 写数据  0x2E F195 → 肯定响应 0x6E（需上一步已解锁）
                response = send_and_wait(bus, 0x2E, 0xF1, 0x95, 0x0A, 0x0B)
                if response is not None and response.data[1] == 0x6E:
                    print("写配置成功")
                else:
                    print("写配置失败")

                # 6) 读故障码  0x19 02 → 肯定响应 0x59
                response = send_and_wait(bus, 0x19, 0x02, 0xFF)
                if response is not None and response.data[1] == 0x59:
                    print("读故障码成功")
                else:
                    print("读故障码失败")

                # 7) 例程控制  0x31 01 → 肯定响应 0x71
                response = send_and_wait(bus, 0x31, 0x01, 0xFF, 0x00)
                if response is not None and response.data[1] == 0x71:
                    print("例程控制成功")
                else:
                    print("例程控制失败")

            else:
                print("解锁失败")
        else:
            print("种子请求失败")

    elif response is not None and response.data[1] == 0x7F:
        print("否定响应 NRC=", hex(response.data[3]))
    else:
        print("扩展会话失败/未响应")

finally:
    ecu.stop()
    bus.shutdown()
    bus_ecu.shutdown()
