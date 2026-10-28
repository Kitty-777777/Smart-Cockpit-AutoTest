"""ECU simulation on virtual CAN — periodic frames + session-aware UDS."""
from __future__ import annotations

import argparse
import struct
import threading

time_mod = __import__("time")

import can

from bus_util import (
    ID_DIAG_REQ,
    ID_DIAG_RESP,
    ID_ENGINE,
    ID_VEHICLE,
    ID_MEDIA,
    ID_MEDIA_CTRL,
    load_db,
    open_bus,
)

# Session types (UDS 0x10 sub-function)
SESSION_DEFAULT = 0x01
SESSION_PROGRAMMING = 0x02
SESSION_EXTENDED = 0x03

# Practice DIDs
DID_VIN = (0xF1, 0x90)  # needs extended
DID_ECU_SW = (0xF1, 0x95)  # readable in default; writable after unlock
DID_FINGERPRINT = (0xF1, 0x5A)  # needs programming

# Practice DTCs (3-byte each)
PRACTICE_DTCS = [
    bytes([0x01, 0x23, 0x45]),  # P0123-ish demo
    bytes([0xC0, 0x01, 0x00]),
]

# Practice routine
ROUTINE_CHECK_PROG = (0xFF, 0x00)


def calc_key(seed: int) -> int:
    """练习用简单种子算法（真车由 OEM 保密算法决定）。"""
    return (seed ^ 0xA5A5A5A5) & 0xFFFFFFFF


class EcuSim:
    def __init__(self, bus: can.BusABC) -> None:
        self.bus = bus
        self.db = load_db()
        self._stop = threading.Event()
        self.rpm = 800.0
        self.temp_c = 50.0
        self.v_speed = 0.0
        self.session = SESSION_DEFAULT
        self.unlocked = False
        self._seed: int | None = None
        self.ecu_sw = bytes([0x01, 0x02])
        self.dtcs = list(PRACTICE_DTCS)
        self.routine_state = 0x00  # 0 idle / 1 running / 2 finished OK
        self.media_status = 0  # 0 暂停 / 1 播放
        self._rx = threading.Thread(target=self._rx_loop, daemon=True)
        self._tx = threading.Thread(target=self._tx_loop, daemon=True)

    def start(self) -> None:
        self._rx.start()
        self._tx.start()
        print("[ECU] started (periodic TX + full UDS practice)")

    def stop(self) -> None:
        self._stop.set()
        self._rx.join(timeout=1)
        self._tx.join(timeout=1)

    def _tx_loop(self) -> None:
        last_media = 0.0
        while not self._stop.is_set():
            now = time_mod.time()
            eng = self.db.get_message_by_name("EngineData")
            veh = self.db.get_message_by_name("VehicleStatus")
            media = self.db.get_message_by_name("MediaData")
            raw_eng = eng.encode(
                {
                    "EngineSpeed": self.rpm,
                    "CoolantTemp": self.temp_c,
                    "EngRunning": 1,
                }
            )
            raw_veh = veh.encode(
                {
                    "VehicleSpeed": self.v_speed,
                    "Gear": 1,
                }
            )
            self.bus.send(can.Message(arbitration_id=ID_ENGINE, data=raw_eng, is_extended_id=False))
            self.bus.send(can.Message(arbitration_id=ID_VEHICLE, data=raw_veh, is_extended_id=False))
            if now - last_media >= 0.1:
                last_media = now
                raw_media = media.encode({"MediaStatus": self.media_status})
                self.bus.send(
                    can.Message(arbitration_id=ID_MEDIA, data=raw_media, is_extended_id=False)
                )
            self.rpm = 800 + (time_mod.time() * 20) % 200
            if self.v_speed < 60:
                self.v_speed += 0.05
            time_mod.sleep(0.01)

    def _rx_loop(self) -> None:
        while not self._stop.is_set():
            msg = self.bus.recv(timeout=0.05)
            if msg is None:
                continue
            # 车机控制面板：0x400  0x01 播放 / 0x00 暂停
            if msg.arbitration_id == ID_MEDIA_CTRL and msg.data:
                cmd = msg.data[0]
                if cmd == 0x01:
                    self.media_status = 1
                    print("[ECU] media PLAY")
                elif cmd == 0x00:
                    self.media_status = 0
                    print("[ECU] media PAUSE")
                continue
            if msg.arbitration_id != ID_DIAG_REQ:
                continue
            data = bytes(msg.data)
            pci = data[0] & 0xF0
            if pci != 0x00:
                continue
            sid = data[1]
            resp = self._uds_response(sid, data)
            self.bus.send(
                can.Message(arbitration_id=ID_DIAG_RESP, data=resp, is_extended_id=False)
            )
            print(
                f"[ECU] sess=0x{self.session:02X} unlock={int(self.unlocked)} "
                f"SID=0x{sid:02X} -> {resp.hex(' ')}"
            )

    def _nrc(self, sid: int, code: int) -> bytes:
        return bytes([0x03, 0x7F, sid, code, 0x00, 0x00, 0x00, 0x00])

    def _uds_response(self, sid: int, req: bytes) -> bytes:
        if sid == 0x10:  # DiagnosticSessionControl
            sub = req[2] & 0x7F
            if sub not in (SESSION_DEFAULT, SESSION_PROGRAMMING, SESSION_EXTENDED):
                return self._nrc(0x10, 0x12)
            self.session = sub
            # 切会话时通常失去安全访问状态
            self.unlocked = False
            self._seed = None
            return bytes([0x06, 0x50, sub, 0x00, 0x32, 0x01, 0xF4, 0x00])

        if sid == 0x27:  # SecurityAccess
            return self._security_access(req)

        if sid == 0x22:  # ReadDataByIdentifier
            return self._read_data(req)

        if sid == 0x2E:  # WriteDataByIdentifier
            return self._write_data(req)

        if sid == 0x19:  # ReadDTCInformation
            return self._read_dtc(req)

        if sid == 0x31:  # RoutineControl
            return self._routine_control(req)

        if sid == 0x3E:  # TesterPresent
            return bytes([0x02, 0x7E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

        return self._nrc(sid, 0x11)  # serviceNotSupported

    def _security_access(self, req: bytes) -> bytes:
        if self.session != SESSION_EXTENDED:
            return self._nrc(0x27, 0x7E)  # serviceNotSupportedInActiveSession
        level = req[2]
        if level == 0x01:  # requestSeed
            self._seed = 0x11223344
            self.unlocked = False
            seed_bytes = struct.pack(">I", self._seed)
            return bytes([0x06, 0x67, 0x01]) + seed_bytes + bytes([0x00])
        if level == 0x02:  # sendKey
            if self._seed is None:
                return self._nrc(0x27, 0x24)  # requestSequenceError
            key = struct.unpack(">I", bytes(req[3:7]))[0]
            if key != calc_key(self._seed):
                self.unlocked = False
                return self._nrc(0x27, 0x35)  # invalidKey
            self.unlocked = True
            self._seed = None
            return bytes([0x02, 0x67, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])
        return self._nrc(0x27, 0x12)

    def _read_data(self, req: bytes) -> bytes:
        did = (req[2], req[3])
        if did == DID_VIN and self.session != SESSION_EXTENDED:
            return self._nrc(0x22, 0x33)
        if did == DID_FINGERPRINT and self.session != SESSION_PROGRAMMING:
            return self._nrc(0x22, 0x33)
        if did == DID_VIN:
            return bytes([0x07, 0x62, 0xF1, 0x90, 0x57, 0x56, 0x57, 0x5A])
        if did == DID_ECU_SW:
            return bytes([0x05, 0x62, 0xF1, 0x95, self.ecu_sw[0], self.ecu_sw[1], 0x00, 0x00])
        if did == DID_FINGERPRINT:
            return bytes([0x05, 0x62, 0xF1, 0x5A, 0xAA, 0xBB, 0x00, 0x00])
        return self._nrc(0x22, 0x31)

    def _write_data(self, req: bytes) -> bytes:
        if self.session != SESSION_EXTENDED:
            return self._nrc(0x2E, 0x7E)
        if not self.unlocked:
            return self._nrc(0x2E, 0x33)
        did = (req[2], req[3])
        if did != DID_ECU_SW:
            return self._nrc(0x2E, 0x31)
        self.ecu_sw = bytes([req[4], req[5]])
        return bytes([0x03, 0x6E, 0xF1, 0x95, 0x00, 0x00, 0x00, 0x00])

    def _read_dtc(self, req: bytes) -> bytes:
        sub = req[2]
        if sub == 0x02:  # reportDTCByStatusMask
            # SF demo: 1 DTC + status (真车常多帧)
            dtc = self.dtcs[0]
            status = 0x2F  # testFailed + confirmed 等练习位
            payload = bytes([0x59, 0x02, 0xFF]) + dtc + bytes([status])
            return bytes([len(payload) & 0x0F]) + payload.ljust(7, b"\x00")
        if sub == 0x01:  # reportNumberOfDTCByStatusMask
            n = len(self.dtcs)
            return bytes([0x06, 0x59, 0x01, 0xFF, 0x01, 0x00, n & 0xFF, 0x00])
        return self._nrc(0x19, 0x12)

    def _routine_control(self, req: bytes) -> bytes:
        if self.session != SESSION_EXTENDED:
            return self._nrc(0x31, 0x7E)
        if not self.unlocked:
            return self._nrc(0x31, 0x33)
        sub = req[2]
        rid = (req[3], req[4])
        if rid != ROUTINE_CHECK_PROG:
            return self._nrc(0x31, 0x31)
        if sub == 0x01:  # startRoutine
            self.routine_state = 0x02  # 练习：立刻完成
            return bytes([0x04, 0x71, 0x01, rid[0], rid[1], 0x00, 0x00, 0x00])
        if sub == 0x03:  # requestRoutineResults
            return bytes([0x05, 0x71, 0x03, rid[0], rid[1], self.routine_state, 0x00, 0x00])
        return self._nrc(0x31, 0x12)


def main() -> None:
    parser = argparse.ArgumentParser(description="Virtual ECU for python-can practice")
    parser.add_argument("--seconds", type=float, default=0, help="0 = run until Ctrl+C")
    args = parser.parse_args()

    bus = open_bus()
    ecu = EcuSim(bus)
    ecu.start()
    try:
        if args.seconds > 0:
            time_mod.sleep(args.seconds)
        else:
            while True:
                time_mod.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        ecu.stop()
        bus.shutdown()
        print("[ECU] stopped")


if __name__ == "__main__":
    main()
