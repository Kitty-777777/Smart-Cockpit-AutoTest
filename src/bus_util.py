"""Shared virtual CAN bus helpers (no hardware)."""
from __future__ import annotations

from pathlib import Path

import can
import cantools

ROOT = Path(__file__).resolve().parents[1]
DBC_PATH = ROOT / "dbc" / "Practice.dbc"
CHANNEL = "practice_vcan"

# UDS single-frame IDs (match DBC)
ID_DIAG_REQ = 0x7DF  # 2015
ID_DIAG_RESP = 0x7E8  # 2024
ID_ENGINE = 0x100  # 256
ID_VEHICLE = 0x200  # 512
ID_MEDIA = 0x300  # 768 功放状态（周期）
ID_MEDIA_CTRL = 0x400  # 1024 车机播放/暂停键


def load_db() -> cantools.database.Database:
    return cantools.database.load_file(str(DBC_PATH))


def open_bus(receive_own_messages: bool = False) -> can.BusABC:
    """Open a virtual bus. Same CHANNEL connects participants in one process / OS."""
    return can.Bus(
        interface="virtual",
        channel=CHANNEL,
        receive_own_messages=receive_own_messages,
        bitrate=500000,
    )


def sf_uds(sid: int, *payload: int) -> bytes:
    """Build ISO-TP single-frame UDS request (PCI + SID + data), padded to 8 bytes."""
    data = bytes([sid, *payload])
    pci = len(data) & 0x0F
    frame = bytes([pci]) + data
    return frame.ljust(8, b"\x00")
