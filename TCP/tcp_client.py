from TCPUtility import WindowSegement, DataBlock
from TCPSegment import TCPSegment
import TCPUtility
import argparse
import socket
import time

PACKET_TIMEOUT = .5  # seconds
NUM_RETRANSMISSIONS = 15
MAX_SEGMENT_SIZE = 1472  # bytes
HEADER_SIZE = 20  # bytes
MAX_PAYLOAD = MAX_SEGMENT_SIZE - HEADER_SIZE
CLIENT_WINDOW = 2**15-1


def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", action="store", type=str,
                        dest="serverIP", required=True)
    parser.add_argument("-sp", action="store", type=int,
                        dest="serverPort", required=True)
    parser.add_argument("-f", action="store", type=str,
                        dest="fileName", required=True)
    parser.add_argument("-cp", action="store", type=int,
                        dest="clientPort", required=True)
    parser.add_argument("-m", action="store", type=str,
                        dest="mode", required=True)
    args = parser.parse_args()

    # Create the UDP socket
    clientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    clientSocket.settimeout(5)  # just in case something gets hung
    clientSocket.bind(("localhost", args.clientPort))
    adr = (args.serverIP, args.serverPort)
    print(adr)

    # give some time for the server to open
    time.sleep(1)

    ###### SELECTIVE REPEAT ######
    if args.mode == 'w':
        ###### GET DATA TO SEND #####
        file = open(args.fileName, "rb")
        fileData = file.read()
        file.close()

        ###### ESTABLISH CONNECTION ######
        firstData = fileData[:MAX_PAYLOAD]
        fileData = fileData[MAX_PAYLOAD:]
        success, windowStart, ack, windowSize = TCPUtility.establishConnectionClientInit(
            clientSocket, adr, args.clientPort, args.serverPort, firstData)
        if not success:
            print("Three-way handshake failed.")
            return

        # Check if all of the data was sent in just the first ack
        if len(fileData) <= 0:
            TCPUtility.endConnectionClientInit(
                clientSocket, adr, args.clientPort, args.serverPort, windowStart, ack, windowSize)
            return

        # Prepare initial window and Trasmit first packets
        numWindowSegments = windowSize // (MAX_PAYLOAD)
        windowSegments = []
        for i in range(numWindowSegments):
            segment = TCPSegment(
                fileData[:MAX_PAYLOAD], args.clientPort, args.serverPort, windowStart + i * MAX_PAYLOAD, ack + i * MAX_PAYLOAD, windowSize, False, False, False)

            if (len(fileData) <= MAX_PAYLOAD):
                windowSegments.append(WindowSegement(
                    clientSocket, adr, segment, segment.seq_num + len(fileData), PACKET_TIMEOUT, NUM_RETRANSMISSIONS))
            else:
                windowSegments.append(WindowSegement(
                    clientSocket, adr, segment, segment.seq_num + MAX_PAYLOAD, PACKET_TIMEOUT, NUM_RETRANSMISSIONS))
            fileData = fileData[MAX_PAYLOAD:]

        #windowEnd = windowStart + windowSize
        windowEnd = windowStart + numWindowSegments * MAX_PAYLOAD
        seqAckOffset = ack - windowStart
        # Start Listening
        while True:
            # Catch an incoming packet
            msg, fromAdr = clientSocket.recvfrom(2000)

            # check if packet is from correct address, if not ignore it
            if fromAdr != adr:
                continue

            # parse and check if its a fin
            incomingSegment = TCPUtility.bytesToTCPSegment(msg)

            if (incomingSegment.is_fin):
                TCPUtility.endConnectionServerInit(
                    clientSocket, adr, incomingSegment)
                return

            # check if its an ack and its ack num is within the expected range
            if not incomingSegment.is_ack:
                continue

            # Try to ack the segment in the window
            segAcked = False
            for seg in windowSegments:
                #print("Wanted " + str(seg.expectedAck))
                if (seg.expectedAck == incomingSegment.ack_num):
                    seg.ack()
                    segAcked = True
                    #print("Acked " + str(seg.expectedAck))
                    break
            # print("")
            if not segAcked:
                # there was no valid ack number (either out of window range or not an incrment of data size)
                continue

            # Slide window if you can
            # Count acked segments in front of window
            slideBy = 0
            for seg in windowSegments:
                if not seg.isAcked:
                    break
                slideBy += 1

            # slide window by poping front and appending new segment
            for _ in range(slideBy):
                # remove first segment
                windowSegments.pop(0)
                # increment window start and ack to send
                windowStart += MAX_PAYLOAD
                ack += MAX_PAYLOAD

                # check if out of data
                if len(fileData) <= 0:
                    break

                # Check if windowStart/ack is too high (roll over)
                seqToUse = windowEnd
                if (seqToUse > 2**32-1):
                    seqToUse -= 2**32

                ackToUse = seqToUse + seqAckOffset
                if (ackToUse > 2**32-1):
                    ackToUse -= 2**32

                # check if last data, prepare to close if so
                expectedAck = seqToUse
                if len(fileData) < MAX_PAYLOAD:
                    expectedAck += len(fileData)
                else:
                    expectedAck += MAX_PAYLOAD

                #print("slide, new ack: " + str(expectedAck))
                # create and append new window segment
                segment = TCPSegment(
                    fileData[:MAX_PAYLOAD], args.clientPort, args.serverPort, seqToUse, ackToUse, windowSize, False, False, False)
                windowSegments.append(WindowSegement(
                    clientSocket, adr, segment, expectedAck, PACKET_TIMEOUT, NUM_RETRANSMISSIONS))

                # check if on the last data
                if len(fileData) < MAX_PAYLOAD:
                    windowEnd += len(fileData)
                else:
                    windowEnd += MAX_PAYLOAD

                fileData = fileData[MAX_PAYLOAD:]

            # Check if you can finish the connection
            if len(windowSegments) <= 0:
                seqToUse = windowEnd
                if (seqToUse > 2**32-1):
                    seqToUse -= 2**32

                ackToUse = seqToUse + seqAckOffset
                if (ackToUse > 2**32-1):
                    ackToUse -= 2**32

                TCPUtility.endConnectionClientInit(
                    clientSocket, adr, args.clientPort, args.serverPort, seqToUse, ackToUse, windowSize)
                return

    elif args.mode == 'r':
        ###### ESTABLISH CONNECTION ######
        success, windowStart, ack, windowSize = TCPUtility.establishConnectionClientInit(
            clientSocket, adr, args.clientPort, args.serverPort, b'')
        if not success:
            print("Three-way handshake failed.")
            return

        seqAckOffset = ack - windowStart
        windowStart = ack  # first seq expected
        # Prepare initial window and Trasmit first packets
        numWindowBlocks = windowSize // (MAX_PAYLOAD) + 1
        windowBlocks = []
        for i in range(numWindowBlocks):
            block = DataBlock(windowStart + i * MAX_PAYLOAD)
            windowBlocks.append(block)

        windowEnd = windowStart + numWindowBlocks * MAX_PAYLOAD

        file = open(args.fileName, "ab")
        # Start Listening
        while True:
            # Catch an incoming packet
            msg, fromAdr = clientSocket.recvfrom(2000)

            # check if packet is from correct address, if not ignore it
            if fromAdr != adr:
                continue

            # parse and check if its a fin
            incomingSegment = TCPUtility.bytesToTCPSegment(msg)

            if (incomingSegment.is_fin):
                file.close()
                TCPUtility.endConnectionServerInit(
                    clientSocket, adr, incomingSegment)
                return

            # Check if block is for already acked
            if incomingSegment.seq_num < windowStart:
                print("Seq is less than window start (" + str(windowStart))
                ackNum = incomingSegment.seq_num + \
                    len(incomingSegment.data)
                seqNum = ackNum - seqAckOffset
                ackSegment = TCPSegment(
                    b'\0', args.clientPort, args.serverPort, seqNum, ackNum, CLIENT_WINDOW, True, False, False)
                clientSocket.sendto(ackSegment.to_bytes(), adr)
                continue

            # Check if seq is expected, if so write down that data and ack block
            for block in windowBlocks:
                if incomingSegment.seq_num == block.expectedSeq:
                    file.write(incomingSegment.data)
                    # print("wrote")
                    block.accept()

                    # ack back
                    ackNum = incomingSegment.seq_num + \
                        len(incomingSegment.data)
                    seqNum = ackNum - seqAckOffset
                    ackSegment = TCPSegment(
                        b'\0', args.clientPort, args.serverPort, seqNum, ackNum, CLIENT_WINDOW, True, False, False)
                    clientSocket.sendto(ackSegment.to_bytes(), adr)
                    break

            # Slide window if possible
            slideBy = 0
            for block in windowBlocks:
                if not block.hasData:
                    break
                slideBy += 1

            for _ in range(slideBy):
                windowBlocks.pop(0)
                windowStart += MAX_PAYLOAD
                #print("slide start at: " + str(windowStart))
                newBlock = DataBlock(
                    windowEnd)
                windowBlocks.append(newBlock)
                windowEnd += MAX_PAYLOAD


main()
