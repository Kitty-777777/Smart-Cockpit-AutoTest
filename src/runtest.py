import can
import pytest
from bus_util import ID_DIAG_REQ, ID_ENGINE, ID_DIAG_RESP,load_db,open_bus,sf_uds
from ecu_sim import EcuSim,calc_key
import struct
import time 

@pytest.fixture(scope='function')
def bus_ecu():
    bus = open_bus()
    yield bus
    bus.shutdown()

@pytest.fixture(scope='function')
def ecu(bus_ecu):
    sim = EcuSim(bus_ecu)
    sim.start()
    yield sim
    sim.stop()
    
@pytest.fixture(scope='function')
def bus_test(ecu):
    bus = open_bus()
    yield bus
    bus.shutdown()

def send_and_wait(bus,*payload,timeout=1.0):
    bus.send(can.Message(
        arbitration_id=ID_DIAG_REQ,
        data=sf_uds(*payload),
        is_extended_id=False
        ))
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=0.05)
        if msg is None:
            continue
        if msg.arbitration_id == ID_DIAG_RESP:
            return msg
    return None

def test_engine_data(bus_test):
    #周期报文 Enginedata 正常发送
    db = load_db()
    msg = bus_test.recv(timeout=1.0)
    assert msg is not None
    decoded = db.decode_message(ID_ENGINE,msg.data)
    assert 700 < decoded['EngineSpeed'] <= 1100

def test_sessiom_control(bus_test):
    #0x10 03 切扩展会话
    #send_and_wait(bus_test,0x10,0x00)
    resp = send_and_wait(bus_test,0x10,0x03)
    assert resp is not None
    assert resp.data[1] == 0x50
    assert resp.data[2] == 0x03

def test_security_access(bus_test):
    #0x27  安全访问解锁
    send_and_wait(bus_test,0x10,0x03)
    resp = send_and_wait(bus_test,0x27,0x01)
    assert resp is not None
    assert resp.data[1] == 0x67
    seed  = struct.unpack('>I',resp.data[3:7])[0]
    key = calc_key(seed)
    resp = send_and_wait(bus_test,0x27,0x02,*struct.pack('>I',key))
    assert resp is not None
    assert resp.data[1] == 0x67
   
def test_read_vin(bus_test):
    #0x22 F190 读VIN
    send_and_wait(bus_test,0x10,0x03)
    resp = send_and_wait(bus_test,0x22,0xF1,0x90)
    assert resp is not None
    assert resp.data[1] == 0x62
    

def test_unkown_sid_nrc(bus_test):
    #未知SID返回NRC 0x11 
    resp = send_and_wait(bus_test,0x88,0x01)
    assert resp is not None
    assert resp.data[1] == 0x7F
    assert resp.data[3] == 0x11

def test_write_data(bus_test):
    #0x2E F195 写数据（需要先解锁）
    send_and_wait(bus_test,0x10,0x03)
    resp = send_and_wait(bus_test,0x27,0x01)
    seed = struct.unpack('>I',resp.data[3:7])[0]
    key = calc_key(seed)
    send_and_wait(bus_test,0x27,0x02,*struct.pack('>I',key))
    resp = send_and_wait(bus_test,0x2E,0xF1,0x95,*struct.pack('>I',0x12345678))
    assert resp is not None
    assert resp.data[1] == 0x6E
   
