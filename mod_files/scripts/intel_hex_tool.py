#!/usr/bin/env python3
# intel_hex_tool.py
# Copyright (c) 2025 Adam Johnston
# This file is licensed under the MIT License
# License text and project information at: https://github.com/a-johnston/intel_hex_tool/

import os
import sys
from argparse import ArgumentParser
from ast import literal_eval
from contextlib import contextmanager
from difflib import SequenceMatcher
from pathlib import Path
from typing import IO, Any, Dict, Iterable, Iterator, List, NamedTuple, Optional, Tuple

__version__ = '0.1.0'

DATA_RECORD = 0
EOF_RECORD = 1
EXTENDED_LINEAR_ADDRESS_RECORD = 4
START_ADDRESS_RECORD = 5

_newlines = {'unix': '\n', 'dos': '\r\n'}
_newline_name = {v: k for k, v in _newlines.items()}


def format_newline_info(newline: str) -> str:
    name = _newline_name.get(newline, 'unknown')
    return f'{newline!r} ({name})'


def warning(text: str) -> str:
    return f'\033[93m{text}\033[0m'


def get_address_high_low(address: int) -> Tuple[int, int]:
    """Returns a 2-tuple of the upper and lower 16 bits of a 32 bit value."""
    return (address >> 16) & 0xFFFF, address & 0xFFFF


def hex_int(data: str) -> int:
    return int(data, 0x10 if data.startswith('0x') else 10)


@contextmanager
def managed_io(path: str, mode: str) -> Iterator[IO]:
    if path == '-':
        text_io = sys.stdin if 'r' in mode else sys.stdout
        yield text_io.buffer if 'b' in mode else text_io
    else:
        with open(path, mode) as fp:
            yield fp


class Instruction(NamedTuple):
    start: int
    len: int
    val: str


class IntelHexRow(NamedTuple):
    address: int
    record_type: int
    data: bytes
    warnings: List[str]

    def _get_non_checksum_bytes(self) -> bytes:
        parts = (
            len(self.data).to_bytes(1, 'big'),
            get_address_high_low(self.address)[1].to_bytes(2, 'big'),
            self.record_type.to_bytes(1, 'big'),
            self.data,
        )
        return b''.join(parts)

    @property
    def checksum(self) -> int:
        """Sums the byte values and returns the two's complement of the least significant byte."""
        return (~sum(self._get_non_checksum_bytes()) + 1) % 256

    @classmethod
    def loads(cls, line: str, extended_address: int = 0, start_code: str = ':') -> 'IntelHexRow':
        """Reads a string containing an intel hex record into this named tuple. The string should be exactly
        the intel hex row and should not contain comments or multiple start codes."""
        # Uses https://en.wikipedia.org/wiki/Intel_HEX as a reference
        _, line = map(str.strip, line.split(start_code))  # Raises if there isn't exactly one start_code
        data = bytes.fromhex(line)
        row = cls(
            address=extended_address + int.from_bytes(data[1:3], 'big'),
            record_type=data[3],
            data=data[4:-1],
            warnings=[],
        )
        # Checksum is defined such that the least significant byte of the sum should be zero
        if sum(data) & 0xFF != 0:
            row.warnings.append(f'Bad checksum for: {line} ({row.checksum:02X} != {data[-1]:02X})')
        if len(row.data) != data[0]:
            row.warnings.append(f'Bad byte count for: {line} ({len(row.data)} != {data[0]})')
        if row.record_type == EXTENDED_LINEAR_ADDRESS_RECORD and len(row.data) != 2:
            row.warnings.append(f'Bad extended address record: {line}')
        if row.record_type == START_ADDRESS_RECORD and len(row.data) != 4:
            row.warnings.append(f'Bad start address record: {line}')
        return row

    def dumps(self, start_code: str = ':') -> str:
        return start_code + (self._get_non_checksum_bytes() + self.checksum.to_bytes(1, 'big')).hex().upper()


def _parse_addr_len(s: str) -> Tuple[int, int]:
    addr, length = s.split(',')
    return int(addr[3:], 0x10), int(length)


class ByteDiff(NamedTuple):
    addr_removed: int
    removed: bytes
    address_added: int
    added: bytes

    def format(self, disasm: bool = False) -> str:
        s = f'@@ -0x{self.addr_removed:08X},{len(self.removed)} +0x{self.address_added:08X},{len(self.added)} @@'
        if self.added:
            asm = (' : ' + ' / '.join(a.val for a in disasm_thumb2(self.added))) if disasm else ''
            s += f'\n+{self.added.hex().upper()}{asm}'
        if self.removed:
            asm = (' : ' + ' / '.join(a.val for a in disasm_thumb2(self.removed))) if disasm else ''
            s += f'\n-{self.removed.hex().upper()}{asm}'
        return s

    @staticmethod
    def parse(text: str) -> 'ByteDiff':
        info, added, removed = map(str.strip, text.strip().split('\n'))
        (address_removed, removed_len), (address_added, added_len) = map(_parse_addr_len, info.strip('@ ').split(' '))
        added = bytes.fromhex(added.split(' : ')[0][1:])
        removed = bytes.fromhex(removed.split(' : ')[0][1:])
        if len(added) != added_len:
            raise ValueError(f'Mismatched added length at 0x{address_added:08X}')
        if len(removed) != removed_len:
            raise ValueError(f'Mismatched removed length at 0x{address_removed:08X}')
        return ByteDiff(address_removed, removed, address_added, added)

    def apply(self, data: bytes, old_offset: int, new_offset: int) -> bytes:
        start = self.addr_removed - old_offset
        end = self.addr_removed + len(self.removed) - old_offset
        if data[start:end] != self.removed:
            raise ValueError(f'Bad diff 0x{self.addr_removed:08X}: {data[start:end]} != {self.removed}')
        return data[0:start] + self.added + data[end:]


_field_serdes = {
    'offset': (lambda i: f'0x{i:08X}', literal_eval),
    'start': (lambda i: f'0x{i:08X}', literal_eval),
    'newline': (format_newline_info, lambda s: literal_eval(s.split(' ')[0])),
}


class HexDelta(NamedTuple):
    fields: Dict[str, Tuple[Any, Any]]
    diffs: List[ByteDiff]

    def format(self, disasm: bool = False) -> str:
        s = ''
        for field, (removed, added) in self.fields.items():
            if removed != added:
                encode = _field_serdes[field][0]
                s += f'\n{field} -{encode(removed)} +{encode(added)}'
        for diff in self.diffs:
            s += '\n\n' + diff.format(disasm=disasm)
        return s.strip()

    @staticmethod
    def parse(text: str) -> 'HexDelta':
        fields = {}
        diffs = []
        sections = text.split('\n\n')
        for section in sections:
            if section.startswith('@@'):
                diffs.append(ByteDiff.parse(section))
            else:
                for field_data in section.split('\n'):
                    field, removed, added = field_data.split(' ')
                    if field in fields:
                        raise ValueError(f'Redefinition of field {field!r}')
                    decode = _field_serdes[field][1]
                    fields[field] = decode(removed[1:]), decode(added[1:])
        return HexDelta(fields, diffs)


class HexData(NamedTuple):
    data: bytes
    offset: int = 0
    start: int = -1
    type: str = 'bin'
    newline: str = ''

    def to_intel_rows(
        self, custom_offset: int = -1, custom_start: int = -1, max_data_bytes: int = 16
    ) -> Iterable[IntelHexRow]:
        extended_address, address = get_address_high_low(custom_offset if custom_offset >= 0 else self.offset)
        if extended_address > 0:
            yield IntelHexRow(0, EXTENDED_LINEAR_ADDRESS_RECORD, extended_address.to_bytes(2, 'big'), [])
        for i in range(0, len(self.data), max_data_bytes):
            row_data = self.data[i : i + max_data_bytes]
            if sum(row_data) > 0:
                row = IntelHexRow(address, DATA_RECORD, row_data, [])
                yield row
            address += len(row_data)
        start = self.start if custom_start < 0 else custom_start
        if start >= 0:
            yield IntelHexRow(0, START_ADDRESS_RECORD, start.to_bytes(4, 'big'), [])
        yield IntelHexRow(0, EOF_RECORD, b'', [])

    def get_delta(self, other: 'HexData', exact: bool = False, word_aligned: bool = False) -> HexDelta:
        diffs = []
        for tag, i1, i2, j1, j2 in SequenceMatcher(a=self.data, b=other.data, autojunk=not exact).get_opcodes():
            if tag != 'equal':
                if word_aligned:
                    i1, i2 = _align(i1, i2)
                    j1, j2 = _align(j1, j2)
                diffs.append(ByteDiff(self.offset + i1, self.data[i1:i2], other.offset + j1, other.data[j1:j2]))
        a, b = self._asdict(), other._asdict()
        if set(a) != set(b):
            raise ValueError('Mismatched field sets')
        fields = {n: (a[n], b[n]) for n in a if a[n] != b[n] and n in _field_serdes}
        return HexDelta(fields, diffs)

    def with_delta(self, delta: HexDelta) -> 'HexData':
        fields = self._asdict()
        for field, (old, new) in delta.fields.items():
            if field not in fields:
                raise ValueError(f'Unknown field {field!r}')
            current = fields[field]
            if old != current:
                raise ValueError(f'Bad diff {field!r}: {current} != {old}')
            fields[field] = new
        data = fields.pop('data')
        for diff in delta.diffs:
            data = diff.apply(data, self.offset, fields['offset'])
        return HexData(data, **fields)


def read_hex(file: str) -> HexData:
    """Reads a hexfile, first attempting to treat it as an intel hex file but otherwise
    loads the file's literal bytes with and offset and start value of zero.
    """
    try:
        return read_intel_hex(file)
    except Exception:
        pass
    return read_bin_hex(file)


def read_bin_hex(file: str) -> HexData:
    files = list(Path('.').glob(file))
    if len(files) != 1:
        raise ValueError(f'Need exactly one file matching {file} to read binary')
    return HexData(files[0].read_bytes())


def read_intel_hex(file: str, start_code: str = ':', comment: str = '//') -> HexData:
    # Uses https://en.wikipedia.org/wiki/Intel_HEX as a reference. Does not implement all record types.
    records = []
    extended_address = 0
    start = -1
    newline = ''
    for path in Path('.').glob(file):
        with path.open('r', newline='') as fp:
            for line in fp.readlines():
                if not newline:
                    newline = line[len(line.rstrip()) :]
                # Remove comments and skip non-record lines
                line = line.split(comment, 1)[0].strip()
                if start_code not in line:
                    continue
                row = IntelHexRow.loads(line, extended_address=extended_address, start_code=start_code)
                if row.warnings:
                    print(warning('\n'.join(row.warnings)))
                if row.record_type == EXTENDED_LINEAR_ADDRESS_RECORD:
                    extended_address = int.from_bytes(row.data, 'big') << 16
                elif row.record_type == DATA_RECORD:
                    records.append(row)
                elif row.record_type == START_ADDRESS_RECORD:
                    if start != -1:
                        print(warning('Multiple start address records'))
                    start = int.from_bytes(row.data, 'big')
                elif row.record_type == EOF_RECORD:
                    break
                else:
                    print(warning(f'Ignoring record with type {row.record_type.to_bytes(1, "big")}'))
    data = b''
    records.sort(key=lambda row: row.address)
    offset = records[0].address
    for record in records:
        gap = record.address - offset - len(data)
        if gap < 0:
            raise Exception(f'Overlapping records detected at address {record.address:08X}')
        data += bytes(gap)
        data += record.data
    return HexData(data=data, offset=records[0].address, start=start, type='intel hex', newline=newline)


def _write(file: str, output: str, binary: bool, start: int, offset: int, newline: str, patch: str) -> None:
    data = read_hex(file)
    if patch:
        with managed_io(patch, 'r') as fp:
            data = data.with_delta(HexDelta.parse(fp.read()))

    with managed_io(output, 'wb' if binary else 'w') as out:
        if binary:
            out.write(data.data)
        else:
            out = sys.stdout if output == '-' else open(output, 'w', newline='')
            rows = data.to_intel_rows(custom_offset=offset, custom_start=start)
            if newline == 'auto' and data.newline:
                newline = data.newline
            else:
                newline = _newlines.get(newline, os.linesep)
            out.write(newline.join(map(IntelHexRow.dumps, rows)) + newline)


def _info(files: List[str]) -> None:
    for file in files:
        data = read_hex(file)
        print(f'\nInfo for {file}')
        print(f'  Type:\t\t{data.type}')
        print(f'  Start:\t0x{data.start:08X}')
        print(f'  Offset:\t0x{data.offset:08X}')
        print(f'  Length:\t0x{len(data.data):08X}')
        if data.newline:
            print(f'  Line endings:\t{format_newline_info(data.newline)}')


def _align(i1, i2) -> Tuple[int, int]:
    return i1 - (i1 % 2), i2 + (i2 % 2)


def _diff(a: str, b: str, exact: bool, disasm: bool, word_aligned: bool) -> None:
    old = read_hex(a)
    new = read_hex(b)

    print(old.get_delta(new, exact, word_aligned).format(disasm))


def _disasm(file: str, start: int, unaligned: bool) -> None:
    data = read_hex(file)
    for instruction in disasm_thumb2(data.data, start, not unaligned):
        print(f'{instruction.start:08X} : {instruction.val}')


def main():
    parser = ArgumentParser(description=f'Hex file conversion and comparison utilities. (version {__version__})')
    sub = parser.add_subparsers(title='commands')

    help = 'Read and write out a hex file in either intel or binary format.'
    write = sub.add_parser('write', help=help, description=help)
    write.add_argument('file', help='Input file')
    write.add_argument('output', default='-', nargs='?')
    write.add_argument('-b', '--binary', action='store_true', help='Output a binary file; strips start and offset')
    write.add_argument('-s', '--start', type=hex_int, default=-1, help='Optional custom start address')
    write.add_argument('-o', '--offset', type=hex_int, default=-1, help='Optional address offset')
    write.add_argument('-n', '--newline', choices=['auto', 'system', *_newlines], default='auto')
    write.add_argument('-p', '--patch', default='', help='Optional patch file to apply before writing output')
    write.set_defaults(func=_write)

    help = 'Print info for one or more hex files.'
    info = sub.add_parser('info', help=help, description=help)
    info.add_argument('files', nargs='+', help='Files to show information for')
    info.set_defaults(func=_info)

    help = 'Print differences between two hex files.'
    diff = sub.add_parser('diff', help=help, description=help)
    diff.add_argument('a')
    diff.add_argument('b')
    diff.add_argument('--exact', action='store_true', help='Slower but may output a smaller change')
    diff.add_argument('-d', '--disasm', action='store_true', help='Output thumb2 instructions for each diff section')
    diff.add_argument('-a', '--word-aligned', action='store_true', help='Align diff to word boundaries')
    diff.set_defaults(func=_diff)

    help = 'Show a thumb2 pseudo assembly for a given hex file.'
    disasm = sub.add_parser('disasm', help=help, description=help)
    disasm.add_argument('file', help='Input file')
    disasm.add_argument('-s', '--start', type=int, default=0, help='Starting byte offset for disassembly')
    disasm.add_argument('-u', '--unaligned', action='store_true', help='Allow instruction decoding at any byte offset')
    disasm.set_defaults(func=_disasm)

    args = parser.parse_args()
    args.__dict__.pop('func')(**args.__dict__)


if __name__ == '__main__':
    main()


# Thumb2 disassembler start


def _reg_list(value: int):
    return ', '.join((f'R{i}' for i in range(8) if (value >> i) & 1))


def _bl32(s: int, i: int, j: int) -> str:
    return f'BL label[{(((j ^ (s * 3)) << 21) + i) * ((-1) ** s):X}]'


cond = 'EQ NE CS/HS CC/LO MI PL VS VC HI LS GE LT GT LE AL UDF SVC'.split()
ops_010000 = 'AND EOR LSL LSR ASR ADC SBC ROR TST RSB CMP CMN ORR MUL BIC MVN'.split()
ops_0101 = 'STR STRH STRB LDRSB LDR LDRH LDRB LDRSH'.split()

# The following maps are written following definitions from the ARMv7-M Architecture Reference Manual. The format
# is string keys of the pattern [01a-zA-Z]+ mapped to either a callable responsible for generating the appropriate
# assembly or a nested dict of further keys to match. Keys in the nested dict omit the matched key in the outer
# dict but inherit the arguments matched by that key. Arguments must have single character names and are read as
# contiguous bits, matching both 0 and 1 from a given word. Args are then unpacked into any matched callable which
# should return a string. NB: If the returned string includes '?' it is ignored and the search continues.

thumb2_single = {  # Section A5.2, pA5-129
    '00': {
        '011fommmnnnddd': lambda f, o, m, n, d: f'{["ADD", "SUB"][o]} R{d}, R{n}, {"R#"[f]}{m}',
        '0ooiiiiimmmddd': lambda o, i, m, d: f'{["LSL", "LSR", "ASR", "?"][o]} R{d}, R{m}, #{i}',
        '1oonnniiiiiiii': lambda o, n, i: f'{["MOV", "CMP", "ADD", "SUB"][o]} R{n}, #{i}',
    },
    '010000oooommmnnn': lambda o, m, n: f'{ops_010000[o]} R{n}, R{m}{ {9: ", #0", 13: f", R{n}"}.get(o, "") }',
    '010001': {
        '11ommmm000': lambda o, m: f'B{"L" * o}X R{m}',
        'oonmmmmnnn': lambda o, m, n: f'{["ADD", "CMP", "MOV", "?"][o]} R{n}, R{m}',
    },
    '0101ooommmnnnttt': lambda o, m, n, t: f'{ops_0101[o]} R{t}, R{n}, R{m}',
    '011foiiiiinnnttt': lambda f, o, i, n, t: f'{["STR", "LDR"][o]}{"B" * f} R{t}, R{n}, #{i}',
    '1000oiiiiinnnttt': lambda o, i, n, t: f'{["STR", "LDR"][o]}H R{t}, R{n}, #{i}',
    '1001otttiiiiiiii': lambda o, t, i: f'{["STR", "LDR"][o]} R{t}, SP, #{i}',
    '1010odddiiiiiiii': lambda o, d, i: f'{["ADR", "ADD"][o]} R{d},{" SP," * o} label[{i:X}]',
    '1011': {
        '0110011m00if': lambda m, i, f: f'CPS {["ENABLE", "DISABLE"][m]} PRIMASK={i} FAULTMASK{f}',
        '0000oiiiiiii': lambda o, i: f'{["ADD", "SUB"][o]} SP, SP, #{i}',
        'o0i1iiiiinnn': lambda o, i, n: f'CB{"N" * o}Z R{n}, label[{i:X}]',
        '0010fgmmmddd': lambda f, g, m, d: f'{"SU"[f]}XT{"HB"[g]} R{d}, R{m}',
        '10100ommmddd': lambda o, m, d: f'REV{"16" * o} R{d}, R{m}',
        '101011mmmddd': lambda m, d: f'REVSH R{d}, R{m}',
        '110prrrrrrrr': lambda p, r: f'POP P={p} {_reg_list(r)}',
        '1110iiiiiiii': lambda i: f'BKPT #{i}',
        '1111': {
            '0ooo0000': lambda o: f'{["NOP", "YIELD", "WFE", "WFI", "SEV", *["?"] * 3][o]}',
            'xxxxyyyy': lambda x, y: f'IT firstcond={x} mask={y}',
        },
    },
    '1100fnnnrrrrrrrr': lambda f, n, r: f'{["ST", "LD"][f]}M R{n}{"!" * (r >> f & 1 or not f)}, {_reg_list(r)}',
    '1101cccciiiiiiii': lambda c, i: f'B{cond[c]} label[{i:X}]',
    '11100iiiiiiiiiii': lambda i: f'B label[{i:X}]',
}

thumb2_double = {  # Section A5.3, pA5-137
    '11101': {},
    '11110': {
        'i01101snnnn0iiiddddiiiiiiii': lambda i, s, n, d: f'SUBS.W R{d}, R{n}, #{i} (S={s})',
        'i101010nnnn0iiiddddiiiiiiii': lambda i, n, d: f'SUBW R{d}, R{n}, #{i}',
        'siiiiiiiiii11j1jiiiiiiiiiii': _bl32,
        '011101111111000111101fgoooo': lambda f, g, o: f'{"DI"[f]}{"SM"[g]}B {o:b}',
    },
    '11111': {},
}


def try_match_word(word: str, pattern: str, args: Dict[str, int]) -> bool:
    for p, w in zip(pattern, word):
        if p in '01':
            if p != w:
                return False
        else:
            args[p] = args.get(p, 0) * 2 + int(w)
    return True


def try_match_any(word: str, ref: Dict[str, Any], args: Dict[str, int]) -> Optional[str]:
    for key in ref:
        new_args = dict(args)
        if try_match_word(word, key, new_args):
            if isinstance(ref[key], dict):
                result = try_match_any(word[len(key) :], ref[key], new_args)
                if result is not None:
                    return result
            else:
                result = ref[key](**new_args)
                if '?' not in result:
                    return result
    return None


def decode_thumb2_chunk(data: bytes, index: int, step) -> Instruction:
    left = len(data) - index
    default = Instruction(index, step, '?' * step)
    if left < 2:
        return Instruction(index, left, '?' * left)
    op16 = int.from_bytes(data[index : index + 2], 'little')
    if op16 >> 11 in {0b11101, 0b11110, 0b11111}:
        if left < 4:
            return Instruction(index, left, '?' * left)
        op32 = int.from_bytes(data[index : index + 4], 'little')
        match = try_match_any(bin(op32)[2:].zfill(32), thumb2_double, {})
        return Instruction(index, 4, match) if match else default
    else:
        match = try_match_any(bin(op16)[2:].zfill(16), thumb2_single, {})
        return Instruction(index, 2, match) if match else default


def disasm_thumb2(data: bytes, index: int = 0, aligned: bool = True) -> Iterable[Instruction]:
    while index < len(data):
        chunk = decode_thumb2_chunk(data, index, 2 if aligned else 1)
        index += chunk.len
        yield chunk


# Thumb disassembler end
