from bitstring import Bits, BitArray


class TCPSegment:
    SEGMENT_LEN = 1500 - 20 - 8  # Number of bytes in header and data
    HEADER_WORDS = 5  # Number of 32-bit words in header
    HEADER_LEN = HEADER_WORDS * 4
    DATA_LEN = SEGMENT_LEN - HEADER_LEN  # Number of bytes in data

    def __init__(self, data, source_port, dest_port, seq_num=0, ack_num=0,
                 window=0, is_ack=False, is_syn=False, is_fin=False):
        if len(data) > self.DATA_LEN:
            raise ValueError("Data length of " + str(len(data)) +
                             " exceeds max of " + str(self.DATA_LEN))
        if source_port >= 2 ** 16:
            raise ValueError("Source port too high")
        if dest_port >= 2 ** 16:
            raise ValueError("Destination port too high")
        if window >= 2 ** 16:
            raise ValueError("Window too large")
        if source_port < 0 or dest_port < 0 or seq_num < 0 or ack_num < 0 or window < 0:
            raise ValueError("Negative values not allowed")
        self.data = data
        self.source_port, self.dest_port = source_port, dest_port
        self.seq_num, self.ack_num = seq_num % (2 ** 32), ack_num % (2 ** 32)
        self.window = window
        self.is_ack, self.is_syn, self.is_fin = is_ack, is_syn, is_fin

    """Returns bytes equivalent"""

    def to_bytes(self):
        array = BitArray(self.source_port.to_bytes(2, "big") + self.dest_port.to_bytes(2, "big")
                         + self.seq_num.to_bytes(4, "big") +
                         self.ack_num.to_bytes(4, "big")
                         + b"\0\0" + self.window.to_bytes(2, "big") + b"\0\0\0\0" + self.data)  # Assemble segment.
        # Set data offset bits.
        array[96:100] = Bits(self.HEADER_WORDS.to_bytes(1, "big"))[4:8]
        # Set control bits.
        array[107], array[110], array[111] = self.is_ack, self.is_syn, self.is_fin
        # if IS_CHECKSUM:
        #     # Set checksum.
        #     array[128:144] = Bits(Checksum16.calc(
        #         array.tobytes()).to_bytes(2, "big"))
        return array.tobytes()
