from typing import BinaryIO, Iterator

from lib.codecutils import read_any_bytes, read_any_le_u, read_bytes


def decode(fp: BinaryIO) -> bytes:
    read_bytes(fp, b"CRILAYLA")
    size = read_any_le_u(fp, 4)
    encoded_size = read_any_le_u(fp, 4)
    encoded_data = read_any_bytes(fp, encoded_size)
    prefix = read_any_bytes(fp, 256)
    data = _decode(encoded_data, size)
    if len(data) != size:
        raise ValueError("size mismatch")
    return prefix + data


def _decode(encoded: bytes, size: int) -> bytes:
    stream = _BitStream(encoded)
    buffer = bytearray()
    while len(buffer) < size:
        if not stream.read(1):
            buffer.append(stream.read(8))
        else:
            offset = 3 + stream.read(13)
            length = 3
            for chunk_length in _chunk_lengths():
                chunk = stream.read(chunk_length)
                length += chunk
                if chunk != (1 << chunk_length) - 1:
                    break
            _copy(buffer, len(buffer) - offset, length)
    if len(buffer) != size:
        raise ValueError("size mismatch")
    buffer.reverse()
    return bytes(buffer)


def _copy(buffer: bytearray, start: int, length: int) -> None:
    data = bytes(buffer[start:])
    data_length = len(data)
    while length:
        chunk_length = min(length, data_length)
        buffer += data[:chunk_length]
        length -= chunk_length


def _chunk_lengths() -> Iterator[int]:
    yield from (2, 3, 5)
    while True:
        yield 8


class _BitStream:
    def __init__(self, data: bytes) -> None:
        self._data = int.from_bytes(data, "little")
        self._remaining = 8 * len(data)

    def read(self, count: int) -> int:
        bits = self._data >> (self._remaining - count)
        bits &= (1 << count) - 1
        self._remaining -= count
        return bits
