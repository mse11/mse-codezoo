"""A small QR code encoder for the printable cards: byte mode, error level M, versions 1-6.

Enough for short card codes (up to 106 bytes). It follows ISO/IEC 18004 the way the
well-known reference encoders do: Reed-Solomon error correction, the eight masks with
the standard penalty rules, and the format bits. Standard library only.
"""

from __future__ import annotations

# error correction level M: (EC codewords per block, data codewords of each block)
BLOCKS = {
    1: (10, [16]),
    2: (16, [28]),
    3: (26, [44]),
    4: (18, [32, 32]),
    5: (24, [43, 43]),
    6: (16, [27, 27, 27, 27]),
}
FORMAT_M = 0  # the two format bits for level M
QUIET = 4  # light modules around the code


def _gf_multiply(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_multiply(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_multiply(root, 0x02)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_multiply(coef, factor)
    return result


def _codewords(data: bytes, version: int) -> list[int]:
    ec_len, block_lens = BLOCKS[version]
    capacity = sum(block_lens)
    bits: list[int] = []

    def put(value: int, length: int) -> None:
        bits.extend((value >> i) & 1 for i in range(length - 1, -1, -1))

    put(0b0100, 4)  # byte mode
    put(len(data), 8)
    for byte in data:
        put(byte, 8)
    put(0, min(4, capacity * 8 - len(bits)))  # terminator
    put(0, -len(bits) % 8)
    words = [int("".join(map(str, bits[i : i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < capacity:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    blocks, start = [], 0
    divisor = _rs_divisor(ec_len)
    for length in block_lens:
        block = words[start : start + length]
        blocks.append((block, _rs_remainder(block, divisor)))
        start += length
    out = []
    for i in range(max(block_lens)):
        out += [block[i] for block, _ in blocks if i < len(block)]
    for i in range(ec_len):
        out += [ec[i] for _, ec in blocks]
    return out


class _Grid:
    def __init__(self, version: int) -> None:
        self.size = 17 + 4 * version
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]
        self.version = version

    def set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def functions(self) -> None:
        size = self.size
        for i in range(size):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        ring = max(abs(dx), abs(dy))
                        self.set(x, y, ring not in (2, 4))
        if self.version >= 2:
            c = 4 * self.version + 10
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    self.set(c + dx, c + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)  # reserve the format areas; real bits come after masking

    def format_bits(self, mask: int) -> None:
        data = FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        size = self.size

        def bit(i: int) -> bool:
            return (bits >> i) & 1 == 1

        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, size - 15 + i, bit(i))
        self.set(8, size - 8, True)  # the dark module

    def data(self, words: list[int]) -> None:
        size, i, total = self.size, 0, len(words) * 8
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = size - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < total:
                        self.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def masked(self, mask: int) -> list[list[bool]]:
        rule = MASKS[mask]
        return [
            [self.dark[y][x] ^ (not self.fixed[y][x] and rule(x, y)) for x in range(self.size)]
            for y in range(self.size)
        ]


MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]
FINDER_LIKE = ([1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1])


def _penalty(grid: list[list[bool]]) -> int:
    size = len(grid)
    score = 0
    lines = [row for row in grid] + [[grid[y][x] for y in range(size)] for x in range(size)]
    for line in lines:
        run, last = 0, None
        for cell in line:
            if cell == last:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, last = 1, cell
        if run >= 5:
            score += run - 2
        bits = [int(c) for c in line]
        for start in range(size - 10):
            if bits[start : start + 11] in FINDER_LIKE:
                score += 40
    for y in range(size - 1):
        for x in range(size - 1):
            c = grid[y][x]
            if c == grid[y][x + 1] == grid[y + 1][x] == grid[y + 1][x + 1]:
                score += 3
    dark = sum(sum(row) for row in grid)
    total = size * size
    score += (abs(dark * 20 - total * 10) + total - 1) // total * 10 - 10
    return score


def encode(text: str, *, mask: int | None = None) -> list[list[bool]]:
    """The QR matrix for ``text`` (True = dark), without the quiet zone."""
    data = text.encode("utf-8")
    version = next((v for v, (_ec, blocks) in BLOCKS.items() if len(data) + 2 <= sum(blocks)), None)
    if version is None:
        raise ValueError("text too long for a card QR code")
    grid = _Grid(version)
    grid.functions()
    grid.data(_codewords(data, version))
    best: tuple[int, list[list[bool]]] | None = None
    for candidate in range(8) if mask is None else [mask]:
        grid.format_bits(candidate)
        result = grid.masked(candidate)
        score = _penalty(result)
        if best is None or score < best[0]:
            best = (score, result)
    assert best is not None
    return best[1]


def svg(text: str, *, module: int = 4, label: str = "QR code") -> str:
    """The QR code as an inline SVG, with its quiet zone."""
    matrix = encode(text)
    size = (len(matrix) + 2 * QUIET) * module
    path = "".join(
        f"M{(x + QUIET) * module},{(y + QUIET) * module}h{module}v{module}h-{module}z"
        for y, row in enumerate(matrix)
        for x, dark in enumerate(row)
        if dark
    )
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
        f'aria-label="{label}" shape-rendering="crispEdges"><rect width="{size}" '
        f'height="{size}" fill="#fff"/><path d="{path}" fill="#000"/></svg>'
    )
