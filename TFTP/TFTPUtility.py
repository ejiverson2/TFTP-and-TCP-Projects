import struct
import socket

### Packets ###


def makeReadReq(fileName):
    packet = bytearray()
    # op code #1
    packet.append(0)
    packet.append(1)
    # file name
    packet += str.encode(fileName)
    packet.append(0)
    # mode
    packet += str.encode("netascii")
    packet.append(0)
    return packet


def makeWriteReq(fileName):
    packet = bytearray()
    # op code #2
    packet.append(0)
    packet.append(2)
    # file name
    packet += str.encode(fileName)
    packet.append(0)
    # mode
    packet += str.encode("netascii")
    packet.append(0)
    return packet


def makeDataPacket(blockNum, dataBlocks):
    packet = bytearray()
    # op cdoe #3
    packet.append(0)
    packet.append(3)
    # block number
    packet += struct.pack(">H", blockNum)
    # data
    packet += dataBlocks[blockNum - 1]
    return packet


def makeAck(blockNum):
    packet = bytearray()
    # opcode #4
    packet.append(0)
    packet.append(4)
    # block num
    packet += struct.pack(">H", blockNum)
    return packet

### Other Utility Functions ###


def getDataBlocks(fileName):
    # read in the file
    file = open(fileName, "rb")
    data = file.read()
    file.close()
    # package the bytes
    # make buckets
    r = []
    for i in range(len(data)//512 + 1):
        r.append(bytearray())
    # put bytes into buckets
    for i in range(len(data)):
        r[i//512].append(data[i])
    return r


def tryToReceive(sock, adrToSend, packetToResend):
    tries = 3
    msg = 0
    adr = 0
    while tries > 0:
        try:
            while True:
                msg, adr = sock.recvfrom(600)
                if adr != adrToSend:
                    #sock.sendto(msg, adr)
                    continue
                break
            break
        except socket.timeout:
            tries -= 1

            print("Tries left: " + str(tries))
    if tries == 0:
        return False, 0
    return True, msg


def clipNum(packet):
    num = bytearray()
    num.append(packet[0])
    num.append(packet[1])
    num = int.from_bytes(num, "big")
    packet.pop(0)
    packet.pop(0)
    return num, packet


def clipFileName(bArray):
    name = bytearray()
    while True:
        c = bArray.pop(0)
        if c == 0:
            break
        name.append(c)
    return name.decode(), bArray
