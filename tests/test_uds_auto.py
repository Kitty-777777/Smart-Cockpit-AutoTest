"""pytest entry — same automation as auto_uds, for CI-style practice."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import can

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_uds import run_suite  # noqa: E402
from bus_util import open_bus  # noqa: E402
from ecu_sim import EcuSim  # noqa: E402


def test_virtual_can_uds_suite():
    bus_ecu = open_bus()
    bus_test = open_bus()
    ecu = EcuSim(bus_ecu)
    ecu.start()
    time.sleep(0.1)
    try:
        results = run_suite(bus_test)
        failed = [r for r in results if not r.ok]
        assert not failed, "; ".join(f"{r.name}: {r.detail}" for r in failed)
    finally:
        ecu.stop()
        bus_ecu.shutdown()
        bus_test.shutdown()
