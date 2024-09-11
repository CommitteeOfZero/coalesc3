BODY_OFFSET = 2048


def crypt(data: bytes) -> bytes:
    buffer = bytearray(data)
    key = 0x5F
    for i in range(len(data)):
        buffer[i] ^= key
        key = (key * 0x15) & 0xFF
    return bytes(buffer)
