"""RLCD_1_5 pump profile (ID-COOLING FX240 LCD): packet builders.

Pure functions, no hardware access — safe to unit-test. Wire format
verified against temp/id-cooling-pump.pcapng, see docs/PROTOCOL.md.
"""

WIDTH = 240
HEIGHT = 240
TARGET = 0xB1          # screen target-ID, constant for RLCD_1_5
REPORT_LEN = 1024
JPEG_OFFSET = 32       # JPEG starts at byte 32 of the DRA announce report
ANN_JPEG_CAP = REPORT_LEN - JPEG_OFFSET  # 992 B of JPEG in announce
CONT_CAP = REPORT_LEN                    # 1024 B of JPEG per continuation


def crt(command: bytes, args: bytes = b"") -> bytes:
    """Build a 1024 B CRT command report (zero-padded)."""
    assert len(command) == 3
    return (b"CRT\x00\x00" + command + args).ljust(REPORT_LEN, b"\x00")


def cmd_dis() -> bytes:
    return crt(b"DIS")


def cmd_brightness(value: int) -> bytes:
    """Vendor app sends 0x64 (100). Scale above 100 untested — keep ≤100."""
    assert 0 <= value <= 100, value
    return crt(b"LIG", bytes([0x00, 0x00, value, 0x00]))


def frame_reports(jpeg: bytes) -> list:
    """Split a JPEG into DRA announce + continuation reports.

    Byte-identical layout to the vendor app: 14 B header, 18 B zero
    padding, JPEG from offset 32; SIZE = len(JPEG) + 32.
    """
    size = len(jpeg) + JPEG_OFFSET
    assert size <= 0xFFFF, "JPEG too large for u16 SIZE field"
    head = (b"CRT\x00\x00DRA" + b"\x00\x00"
            + size.to_bytes(2, "big") + bytes([TARGET, 0x00]))
    assert len(head) == 14
    announce = (head + b"\x00" * (JPEG_OFFSET - len(head))
                + jpeg[:ANN_JPEG_CAP]).ljust(REPORT_LEN, b"\x00")
    rest = jpeg[ANN_JPEG_CAP:]
    chunks = [announce]
    while rest:
        chunks.append(rest[:CONT_CAP].ljust(REPORT_LEN, b"\x00"))
        rest = rest[CONT_CAP:]
    return chunks
