import socket
import TFTPUtility
import argparse
import os.path
import time


def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", action="store", type=str,
                        dest="serverIP", required=True)
    parser.add_argument("-sp", action="store", type=int,
                        dest="serverTID", required=True)
    parser.add_argument("-f", action="store", type=str,
                        dest="fileName", required=True)
    parser.add_argument("-p", action="store", type=int,
                        dest="clientTID", required=True)
    parser.add_argument("-m", action="store", type=str,
                        dest="mode", required=True)
    args = parser.parse_args()

    # check if ports are in range
    if args.serverTID <= 5000 or args.serverTID > 65535:
        print("Ports out of range (5001-65535)")
        return
    if args.clientTID <= 5000 or args.clientTID > 65535:
        print("Ports out of range (5001-65535)")
        return

    # Create the UDP socket
    clientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    clientSocket.settimeout(1)  # just in case something gets hung
    clientSocket.bind(("localhost", args.clientTID))
    adr = (args.serverIP, args.serverTID)
    print(adr)

    # give some time for the server to open
    time.sleep(1)

    if args.mode == 'r':
        # send the initial read req
        request = TFTPUtility.makeReadReq(args.fileName)
        clientSocket.sendto(request, adr)

        # check if the file exists in storage and if so make a new file
        if os.path.isfile(args.fileName):
            copyNum = 1
            fileNameArr = args.fileName.split(".")
            while True:
                if len(fileNameArr) == 1:
                    args.fileName = fileNameArr[0] + "_" + str(copyNum)
                else:
                    args.fileName = fileNameArr[0] + "_" + \
                        str(copyNum) + "." + fileNameArr[1]
                if not os.path.isfile(args.fileName):
                    break
                copyNum += 1

        # get the packets from the server
        blockExpected = 1
        currentPacket = request

        file = open(args.fileName, "ab")
        while True:
            success, msg = TFTPUtility.tryToReceive(
                clientSocket, adr, currentPacket)
            if not success:
                print("No repsonse from server")
                break

            # parse the packet
            msg = bytearray(msg)
            opcode, msg = TFTPUtility.clipNum(msg)
            blockNum, msg = TFTPUtility.clipNum(msg)

            # check for error packet
            if opcode == 5:
                print("Error packet received")
                file.close()
                os.remove(args.fileName)
                os.abort()
                break

            if blockNum != blockExpected:
                clientSocket.sendto(currentPacket, adr)
                continue

            # append new data to file if block num is correct
            file.write(msg)

            # ack the received packet
            currentPacket = TFTPUtility.makeAck(blockExpected)
            clientSocket.sendto(currentPacket, adr)

            # check if the last packet was received
            if len(msg) < 512:
                print("Last packet: # " + str(blockNum) +
                      "len: " + str(len(msg)))
                break

            if blockNum == 65535:
                blockExpected = 0
            else:
                blockExpected += 1

        print(args.fileName + " was received.")
        file.close()

    elif args.mode == "w":
        # split up the file into 512-byte blocks
        blocks = TFTPUtility.getDataBlocks(args.fileName)
        # send the write request
        request = TFTPUtility.makeWriteReq(args.fileName)
        clientSocket.sendto(request, adr)

        # loop to send file packets
        ackExpected = 0
        currentPacket = request
        while True:
            # wait for the next ack before sending another packet
            success, msg = TFTPUtility.tryToReceive(
                clientSocket, adr, currentPacket)
            if not success:
                print("No response from server")
                break

            # Parse the new packet
            msg = bytearray(msg)
            opcode, msg = TFTPUtility.clipNum(msg)
            blockNum, msg = TFTPUtility.clipNum(msg)

            # check for error packet
            if opcode == 5:
                print("Error packet received")
                os.abort()
                break

            # check if the correct ack was received
            if blockNum != ackExpected:
                clientSocket.sendto(currentPacket, adr)
                continue

            # check if the last block was acked
            if blockNum == len(blocks):
                print("Last block acknowledged, end the connection")
                break

            ackExpected += 1

            # send the next packet
            currentPacket = TFTPUtility.makeDataPacket(ackExpected, blocks)
            clientSocket.sendto(currentPacket, adr)

        clientSocket.close()


main()
