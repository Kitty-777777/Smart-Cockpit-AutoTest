"""Automated UDS + signal checks on virtual CAN (no CANoe UI)."""
from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass

import can

from bus_util import ID_DIAG_REQ, ID_DIAG_RESP, ID_ENGINE, load_db, open_bus, sf_uds
from ecu_sim import EcuSim


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


def wait_for(
    bus: can.BusABC,
    arbitration_id: int,
    timeout: float = 1.0,
    match=None,
) -> can.Message | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=0.05)
        if msg is None:
            continue
        if msg.arbitration_id != arbitration_id:
            continue
        if match is None or match(msg):
            return msg
    return None


def run_suite(bus: can.BusABC) -> list[StepResult]:
    db = load_db()
    results: list[StepResult] = []

    # 1) Periodic EngineData must appear
    eng = wait_for(bus, ID_ENGINE, timeout=1.0)
    if eng is None:
        results.append(StepResult("EngineData TX", False, "no frame within 1s"))
    else:
        decoded = db.decode_message(ID_ENGINE, eng.data)
        ok = 700 <= float(decoded["EngineSpeed"]) <= 1100
        results.append(
            StepResult(
                "EngineData TX",
                ok,
                f"rpm={decoded['EngineSpeed']:.1f} temp={decoded['CoolantTemp']}",
            )
        )

    # 2) UDS 0x10 → 扩展会话（读 VIN 需要）
    bus.send(can.Message(arbitration_id=ID_DIAG_REQ, data=sf_uds(0x10, 0x03), is_extended_id=False))
    resp = wait_for(bus, ID_DIAG_RESP, timeout=1.0, match=lambda m: m.data[1] == 0x50)
    results.append(
        StepResult(
            "UDS 0x10 SessionControl",
            resp is not None and resp.data[2] == 0x03,
            "no 0x50" if resp is None else resp.data.hex(" "),
        )
    )

    # 3) UDS 0x22 F190（扩展会话下可读）
    bus.send(
        can.Message(arbitration_id=ID_DIAG_REQ, data=sf_uds(0x22, 0xF1, 0x90), is_extended_id=False)
    )
    resp = wait_for(bus, ID_DIAG_RESP, timeout=1.0, match=lambda m: m.data[1] == 0x62)
    results.append(
        StepResult(
            "UDS 0x22 RDBI F190",
            resp is not None and resp.data[4:8] == b"WVWZ",
            "fail" if resp is None else resp.data.hex(" "),
        )
    )

    # 4) UDS 0x3E
    bus.send(can.Message(arbitration_id=ID_DIAG_REQ, data=sf_uds(0x3E, 0x00), is_extended_id=False))
    resp = wait_for(bus, ID_DIAG_RESP, timeout=1.0, match=lambda m: m.data[1] == 0x7E)
    results.append(
        StepResult(
            "UDS 0x3E TesterPresent",
            resp is not None,
            "no 0x7E" if resp is None else resp.data.hex(" "),
        )
    )

    # 5) Unknown SID -> NRC 0x11（0x31 已纳入完整流程，这里用未实现 SID）
    bus.send(can.Message(arbitration_id=ID_DIAG_REQ, data=sf_uds(0x85, 0x01), is_extended_id=False))
    resp = wait_for(
        bus,
        ID_DIAG_RESP,
        timeout=1.0,
        match=lambda m: m.data[1] == 0x7F and m.data[3] == 0x11,
    )
    results.append(
        StepResult(
            "UDS NRC 0x11",
            resp is not None,
            "no NRC" if resp is None else resp.data.hex(" "),
        )
    )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated virtual CAN / UDS practice")
    parser.add_argument("--trace", action="store_true", help="print all RX frames during run")
    args = parser.parse_args()

    # Two endpoints on same virtual channel
    bus_ecu = open_bus()
    bus_test = open_bus()

    ecu = EcuSim(bus_ecu)
    ecu.start()
    time.sleep(0.1)

    tracer_stop = threading.Event()

    def _trace() -> None:
        while not tracer_stop.is_set():
            msg = bus_test.recv(timeout=0.05)
            if msg and args.trace:
                print(f"  RX id=0x{msg.arbitration_id:03X} data={bytes(msg.data).hex(' ')}")

    # For suite we use bus_test; if --trace, share carefully — simpler: no separate tracer
    # when not tracing. When tracing, drain is mixed — skip dedicated tracer thread.
    try:
        print("=== python-can automation suite ===")
        results = run_suite(bus_test)
        failed = 0
        for r in results:
            mark = "PASS" if r.ok else "FAIL"
            print(f"[{mark}] {r.name}: {r.detail}")
            if not r.ok:
                failed += 1
        print(f"=== done: {len(results) - failed}/{len(results)} passed ===")
        return 1 if failed else 0
    finally:
        tracer_stop.set()
        ecu.stop()
        bus_ecu.shutdown()
        bus_test.shutdown()


if __name__ == "__main__":
    sys.exit(main())
