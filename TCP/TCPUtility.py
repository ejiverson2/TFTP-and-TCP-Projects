import socket
from TCPSegment import TCPSegment
from threading import Thread, Event
import random


class SegmentTransmitter(Thread):
    def __init__(self, socket, address, byteSegment, timeout, attempts):
        Thread.__init__(self)
        self.stopEvent = Event()
        self.socket = socket
        self.address = address
        self.segment = byteSegment
        self.timeout = timeout
        self.attempts = attempts

    def run(self):
        while self.attempts > 0:
            self.socket.sendto(self.segment, self.address)
            if self.stopEvent.wait(self.timeout):
                return
            self.attempts -= 1


class WindowSegement:
    def __init__(self, socket, address, segment, expectedAck, timeout, attempts):
        self.expectedAck = expectedAck
        self.thread = SegmentTransmitter(
            socket, address, segment.to_bytes(), timeout, attempts)
        self.thread.start()
        self.isAcked = False

    def ack(self):
        self.isAcked = True
        self.thread.stopEvent.set()


class DataBlock():
    def __init__(self, expectedSeq):
        self.hasData = False
        self.data = []
        self.expectedSeq = expectedSeq

    def accept(self):
        self.hasData = True


def bytesToTCPSegment(data):
    sourcePort = int.from_bytes(data[:2], "big")
    destPort = int.from_bytes(data[2:4], "big")
    sequenceNum = int.from_bytes(data[4:8], "big")
    ackNum = int.from_bytes(data[8:12], "big")
    window = int.from_bytes(data[14:16], "big")
    isAck = data[13] & 16
    isSyn = data[13] & 2
    isFin = data[13] & 1

    return TCPSegment(data[20:], sourcePort, destPort, sequenceNum, ackNum, window, isAck, isSyn, isFin)

# Try To Receive
# Waits for response from the same address and port
# Resends packet after a timeout (3 retries)
# Returns false if fails all retries
# Returns true and the bytes if successful


def tryToReceive(sock, adrToSend, packetToResend):
    retries = 3
    msg = 0
    adr = 0
    while retries > 0:
        try:
            while True:
                msg, adr = sock.recvfrom(2000)
                if adr != adrToSend:
                    sock.sendto(msg, adr)
                    continue
                break
            break
        except socket.timeout:
            sock.sendto(packetToResend, adrToSend)
            retries -= 1

            print("Tries left: " + str(retries))
    if retries == 0:
        return False, 0, 0
    return True, msg


# Establish Connection
# Does the three-way handshake to establish a connection with the server
# returns True and windowsize if successful, false if not
def establishConnectionClientInit(socket, adrToSend, clientPort, serverPort, firstData):
    # Create the syn packet with random init seq
    sequence = random.randint(0, 2**31 - 1)
    initWindowSize = 2**15-1
    synPacket = TCPSegment(b'', clientPort, serverPort,
                           sequence, 0, initWindowSize, False, True, False)
    synPacket = synPacket.to_bytes()
    # Send it off and wait for the syn/ack packet
    socket.sendto(synPacket, adrToSend)

    print("Sent: Seq " + str(sequence) + " Ack " + str(0))

    success, msg = tryToReceive(socket, adrToSend, synPacket)
    if not success:
        print("Server didn't respond to syn request")
        return False, 0

    # Process new tcp packet
    synAckPacket = bytesToTCPSegment(msg)
    # Todo: check for seq and ack numbers
    if not (synAckPacket.is_ack and synAckPacket.is_syn):
        print("Returned packet was not ack/syn")
        return False, 0

    print("Recv: Seq " + str(synAckPacket.seq_num) +
          " Ack " + str(synAckPacket.ack_num))

    # Check if window size needs to be smaller
    if (initWindowSize > synAckPacket.window):
        initWindowSize = synAckPacket.window

    # Got ack/syn, return ack and finalize connection
    ackPacket = TCPSegment(firstData, clientPort, serverPort, sequence+1,
                           synAckPacket.seq_num+1, initWindowSize, True, False, False)
    ackPacket = ackPacket.to_bytes()
    socket.sendto(ackPacket, adrToSend)

    print("Sent: Seq " + str(sequence+1) +
          " Ack " + str(synAckPacket.seq_num+1))

    if (len(firstData) > 0):
        return True, sequence+1 + len(firstData), synAckPacket.seq_num+1, synAckPacket.window
    return True, sequence+2 + len(firstData), synAckPacket.seq_num+1, synAckPacket.window


def establishConnectionServerInit(socket, adrToSend, clientPort, serverPort):
    # Wait for a syn
    msg, adr = socket.recvfrom(2000)

    # parse tcp
    synReq = bytesToTCPSegment(msg)

    # respond with synack
    sequence = random.randint(0, 2**31 - 1)
    synAck = TCPSegment(b'', clientPort, serverPort,
                        sequence, synReq.seq_num+1, synReq.window, True, True, False)
    socket.sendto(synAck.to_bytes(), adrToSend)

    # wait for ack
    success = tryToReceive(socket, adrToSend, synAck.to_bytes())

    return success, sequence+1, synReq.seq_num+2, synReq.window


def endConnectionClientInit(socket, adrToSend, clientPort, serverPort, seqNum, ackNum, window):
    # Create the syn packet with random init seq
    finPacket = TCPSegment(b'', clientPort, serverPort,
                           seqNum, ackNum, window, True, False, True)
    finPacket = finPacket.to_bytes()
    # Send it off and wait for the finack packet
    socket.sendto(finPacket, adrToSend)
    success, msg = tryToReceive(socket, adrToSend, finPacket)
    if not success:
        print("Server didn't respond to Fin request")
        return False

    # Process new tcp packet
    finAck = bytesToTCPSegment(msg)
    # Todo: check for seq and ack numbers
    if not (finAck.is_ack):
        print("Returned packet was not an ack for fin")
        return False

    # Got ack, wait for fin
    success, msg = tryToReceive(socket, adrToSend, finPacket)
    if not success:
        print("Server didn't send their fin")
        return False

    # Process new tcp packet
    serverFinSeg = bytesToTCPSegment(msg)
    if not (serverFinSeg.is_fin):
        print("server sent a final packet, but it was not a fin")
        return False
    finalAck = TCPSegment(b'', clientPort, serverPort,
                          seqNum+1, ackNum+1, window, True, False, False)
    finalAck = finalAck.to_bytes()
    socket.sendto(finalAck, adrToSend)
    # final ack for fin sent, time to pack it in
    return True


def endConnectionServerInit(socket, adrToSend, finSegment):
    ack1 = TCPSegment(b'', finSegment.dest_port, finSegment.source_port,
                      finSegment.ack_num, finSegment.seq_num+1, finSegment.window, True, False, False)
    ack1 = ack1.to_bytes()
    socket.sendto(ack1, adrToSend)
    myFinSeg = TCPSegment(b'', finSegment.dest_port, finSegment.source_port,
                          finSegment.ack_num + 1, finSegment.seq_num+1, finSegment.window, False, False, True)
    myFinSeg = myFinSeg.to_bytes()
    socket.sendto(myFinSeg, adrToSend)

    retries = 3
    msg = 0
    adr = 0
    while retries > 0:
        try:
            while True:
                msg, adr = socket.recvfrom(2000)
                if adr != adrToSend:
                    socket.sendto(msg, adr)
                    continue
                break
            break
        except socket.timeout:
            socket.sendto(ack1, adrToSend)
            socket.sendto(myFinSeg, adrToSend)
            retries -= 1

            print("Tries left: " + str(retries))
    if retries == 0:
        return False

    finalSegment = bytesToTCPSegment(msg)
    if finalSegment.is_fin and not finalSegment.is_ack:
        endConnectionServerInit(socket, adrToSend, finSegment)
    return True
