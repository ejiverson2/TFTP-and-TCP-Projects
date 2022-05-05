import socket
import TFTPUtility
import argparse
from threading import Thread
from queue import Queue
import os
import time


class ClientHandler(Thread):
    def __init__(self, name, opcode, clientAdr, socket):
        Thread.__init__(self)
        # self.socket = socket.socket(
        #     family=socket.AF_INET, type=socket.SOCK_DGRAM)
        # self.socket.settimeout(1)
        # self.socket.bind(("localhost", port))

        self.socket = socket
        self.queue = Queue()
        self.clientAdr = clientAdr
        self.fileName = name
        print("Base Name:", self.fileName)
        self.opcode = opcode

    def run(self):
        # if write req (server accepts data)
        if self.opcode == 2:
            self.fileName = os.path.basename(self.fileName)
            # # check if the file exists in storage and if so make a new file
            # if os.path.isfile(self.fileName):
            #     copyNum = 1
            #     fileNameArr = self.fileName.split(".")
            #     while True:
            #         if len(fileNameArr) == 1:
            #             self.fileName = fileNameArr[0] + "_" + str(copyNum)
            #         else:
            #             self.fileName = fileNameArr[0] + "_" + \
            #                 str(copyNum) + "." + fileNameArr[1]
            #         if not os.path.isfile(self.fileName):
            #             break
            #         copyNum += 1

            # get the packets from the client
            blockExpected = 1
            currentPacket = TFTPUtility.makeAck(0)
            self.socket.sendto(currentPacket, self.clientAdr)
            file = open(self.fileName, "ab")
            while True:
                # success, msg = TFTPUtility.tryToReceive(
                #     self.socket, self.clientAdr, currentPacket)
                # if not success:
                #     print("No repsonse from client")
                #     break
                msg = self.queue.get()

                # parse the packet
                msg = bytearray(msg)
                opcode, msg = TFTPUtility.clipNum(msg)
                blockNum, msg = TFTPUtility.clipNum(msg)

                # check for error packet
                if opcode == 5:
                    print("Error packet received")
                    file.close()
                    os.remove(self.fileName)
                    os.abort()
                    break

                if opcode != 3:
                    continue

                if blockNum != blockExpected:
                    self.socket.sendto(currentPacket, self.clientAdr)
                    continue

                # append new data to file if block num is correct
                file.write(msg)

                # ack the received packet
                currentPacket = TFTPUtility.makeAck(blockExpected)
                self.socket.sendto(currentPacket, self.clientAdr)

                # check if the last packet was received
                if len(msg) < 512:
                    print("Last packet: # " + str(blockNum) +
                          "len: " + str(len(msg)))
                    break

                if blockNum == 65535:
                    blockExpected = 0
                else:
                    blockExpected += 1

            print(self.fileName + " was received.")
            # self.socket.close()
            file.close()

        elif self.opcode == 1:  # read req (server sends data to client)
            # split up the file into 512-byte blocks
            blocks = TFTPUtility.getDataBlocks(self.fileName)

            # loop to send file packets
            ackExpected = 1
            currentPacket = TFTPUtility.makeDataPacket(1, blocks)
            self.socket.sendto(currentPacket, self.clientAdr)
            while True:
                # wait for the next ack before sending another packet
                # success, msg = TFTPUtility.tryToReceive(
                #     self.socket, self.clientAdr, currentPacket)
                # if not success:
                #     print("No response from server")
                #     break
                msg = self.queue.get()

                # Parse the new packet
                msg = bytearray(msg)
                opcode, msg = TFTPUtility.clipNum(msg)
                blockNum, msg = TFTPUtility.clipNum(msg)

                # check for error packet
                if opcode == 5:
                    print("Error packet received")
                    os.abort()
                    break

                if opcode != 4:
                    continue

                # check if the correct ack was received
                if blockNum != ackExpected:
                    self.socket.sendto(currentPacket, self.clientAdr)
                    continue

                # check if the last block was acked
                if blockNum == len(blocks):
                    print("Last block acknowledged, end the connection")
                    break

                ackExpected += 1

                # send the next packet
                currentPacket = TFTPUtility.makeDataPacket(ackExpected, blocks)
                self.socket.sendto(currentPacket, self.clientAdr)

            # self.socket.close()


def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-sp", action="store", type=int,
                        dest="serverPort", required=True)
    args = parser.parse_args()

    # check if ports are in range
    if args.serverPort <= 5000 or args.serverPort > 65535:
        print("Ports out of range (5001-65535)")
        return

    # Create the UDP socket
    serverSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    # serverSocket = socket.socket(
    # family=socket.AF_INET, type=socket.SOCK_STREAM)
    serverSocket.bind(("localhost", args.serverPort))

    # serverSocket.listen(255)
    # print("Listening")
    # Keep track of threads and available ports
    threads = {}
    # nextPort = 5000

    while True:
        incomingPacketUnaltered, adr = serverSocket.recvfrom(2048)
        #msg, adr = serverSocket.accept()
        incomingPacket = bytearray(incomingPacketUnaltered)

        # check opcode
        opcode, clippedPacket = TFTPUtility.clipNum(incomingPacket)

        if opcode == 1 or opcode == 2:
            print("Op " + str(opcode) + " received from", adr)
            # get file name
            name, clippedPacket = TFTPUtility.clipFileName(clippedPacket)
            # if fileName is "shutdown.txt" then break
            if name == "shutdown.txt":
                print("Shutdown detected, closing...")
                break

            # # prepare a port
            # if (nextPort == args.serverPort):
            #     nextPort += 1
            # if (nextPort >= 65535):
            #     nextPort = 5000
            # connectionPort = nextPort
            # nextPort += 1

            # process read/write
            print("filename in packet: ", name)
            thread = ClientHandler(
                name, opcode, adr, serverSocket)
            thread.start()
            threads[adr] = thread

        elif adr in threads.keys():
            threads[adr].queue.put(incomingPacketUnaltered)


main()
