import can
import time

# 创建虚拟CAN总线
bus = can.Bus(interface='virtual', channel='can0', receive_own_messages=False)

# 构造 0x22 读数据请求：03 22 F1 90 00 00 00 00
# 03是长度，22是SID，F1 90是DID（vin码）
request = can.Message(
    arbitration_id=0x701,# 诊断请求id
    data=[0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00], 
    is_extended_id=False
    )
bus.send(request)
print(f"已发送请求: {request}")

# 等待响应
response = bus.recv(timeout=1.0)
if response:
    print(f"收到响应: {response}")
    if response.data[1] == 0x62:
        print("肯定响应,DID:",hex(response.data[2]),hex(response.data[3]))
    elif response.data[1] == 0x7F:
        print("否定响应,NRC:",hex(response.data[2]))
else:
    print("超时，未收到响应")

# 关闭总线
bus.shutdown()



#---------------要点-----------------
#0x03：单帧长度，表示后面有3个有效字节（22 F1 90）

#0x22：SID，读数据服务

#0xF1 0x90：DID，VIN码

#请求ID 0x701，响应ID 0x709（请求ID + 0x08）

#肯定响应 0x62 = 0x22 + 0x40"""