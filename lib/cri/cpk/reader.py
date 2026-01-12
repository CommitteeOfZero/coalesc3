from dataclasses import dataclass
from operator import itemgetter
from io import BytesIO
from typing import BinaryIO

from lib.codecutils import (
    read_any_bytes,
    read_any_le_u,
)
from lib.cri.cpk._common import crypt
from lib.cri.crilayla import decode as decode_crilayla
from lib.cri.utf import (
    Table,
    decode as decode_table,
)


@dataclass(frozen=True)
class Entry:
    index: int
    id_: int


class Reader:
    def __init__(self, fp: BinaryIO):
        self._fp = fp
        self._read_info()

    def get_by_id(self, id_: int) -> Entry:
        return self._by_id[id_]

    def read_file(self, index: int) -> bytes:
        entry = self._ranges[index]
        self._fp.seek(entry.offset)
        data = read_any_bytes(self._fp, entry.encoded_size)
        if entry.encoded_size != entry.size:
            data = decode_crilayla(BytesIO(data))
            if len(data) != entry.size:
                raise ValueError("size mismatch")
        return data

    def _read_info(self) -> None:
        header_table = self._read_table(self._fp, b"CPK ")
        [header] = header_table.rows

        if header["ItocSize"] == 0:
            raise NotImplementedError

        staging : list[_StagingEntry] = []
        match header["CpkMode"]:
            case 0:
                [itoc] = self._read_span_table(
                    header["ItocOffset"], header["ItocSize"], b"ITOC"
                ).rows
                itoc_l = decode_table(itoc["DataL"])
                itoc_h = decode_table(itoc["DataH"])

                for table in (itoc_l, itoc_h):
                    for row in table.rows:
                        staging.append(
                            _StagingEntry(
                                id_ = row["ID"],
                                encoded_size = row["FileSize"],
                                size = row["ExtractSize"],
                            )
                        )

                staging.sort(key = lambda x : x.id_)

            case 2:
                toc = self._read_span_table(header["TocOffset"], header["TocSize"], b"TOC ").rows
                itoc = sorted(self._read_span_table(header["ItocOffset"], header["ItocSize"], b"ITOC").rows, key = itemgetter("TocIndex"))

                toc = tuple(zip(*sorted(zip(itoc, toc), key = lambda x : x[0]['ID'])))[1]

                for i, row in enumerate(toc):
                    staging.append(
                        _StagingEntry(
                            id_ = i,
                            encoded_size = row["FileSize"],
                            size = row["ExtractSize"]
                        )
                    )

            case _:
                raise NotImplementedError


        ranges: list[_Range] = []
        entries: list[Entry] = []
        self._by_id: dict[int, Entry] = {}
        alignment = header["Align"]
        offset = header["ContentOffset"]
        for staging_entry in staging:
            offset += -offset % alignment
            index = len(ranges)
            ranges.append(
                _Range(
                    offset=offset,
                    encoded_size=staging_entry.encoded_size,
                    size=staging_entry.size,
                ),
            )
            entry = Entry(
                index=index,
                id_=staging_entry.id_,
            )
            entries.append(entry)
            self._by_id[staging_entry.id_] = entry
            offset += staging_entry.encoded_size
        self._ranges = tuple(ranges)
        self.entries = tuple(entries)

    def _read_span_table(self, offset: int, size: int, tag: bytes) -> Table:
        self._fp.seek(offset)
        data = read_any_bytes(self._fp, size)
        return self._read_table(BytesIO(data), tag)

    def _read_table(self, fp: BinaryIO, tag: bytes) -> Table:
        actual_tag = read_any_bytes(fp, 4)
        if actual_tag != tag:
            raise ValueError(f"expected {tag!r}, got {actual_tag!r}")
        encrypted = read_any_le_u(fp, 4) == 0
        size = read_any_le_u(fp, 8)
        data = read_any_bytes(fp, size)
        if encrypted:
            data = crypt(data)
        return decode_table(data)


@dataclass(frozen=True)
class _StagingEntry:
    id_: int
    encoded_size: int
    size: int


@dataclass(frozen=True)
class _Range:
    offset: int
    encoded_size: int
    size: int
