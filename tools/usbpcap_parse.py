#!/usr/bin/env python3
"""Parse a USBPcap .pcapng of the ID-COOLING pump (2000:3000) and carve
DRA image frames. Stdlib only.

Usage: python3 tools/usbpcap_parse.py <capture.pcapng> [out_dir]
Checks: DRA SIZE fields (== len(JPEG)+32), zero padding after FF D9,
command inventory. Exits non-zero on any mismatch.
"""

import struct
import sys
from pathlib import Path


def load_events(path):
    d = Path(path).read_bytes()
    off, events = 0, []
    while off + 12 <= len(d):
        typ, totlen = struct.unpack_from("<II", d, off)
        if totlen < 12 or off + totlen > len(d):
            print(f"BAD block at offset {off}")
            break
        body = d[off + 8:off + totlen - 4]
        if typ == 6:  # Enhanced Packet Block
            _if, ts_hi, ts_lo, caplen, _wire = struct.unpack_from(
                "<IIIII", body, 0)
            pkt = body[20:20 + caplen]
            hlen, = struct.unpack_from("<H", pkt, 0)
            hdr, payload = pkt[:hlen], pkt[hlen:]
            func = struct.unpack_from("<H", hdr, 14)[0]
            bus, dev = struct.unpack_from("<HH", hdr, 17)
            ep, tr = hdr[21], hdr[22]
            dlen = struct.unpack_from("<I", hdr, 23)[0]
            events.append(dict(func=func, ep=ep, tr=tr, dlen=dlen,
                               payload=payload,
                               ts=(ts_hi << 32) | ts_lo, bus=bus, dev=dev))
        off += totlen
    return events


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("out_frames")
    ev = load_events(sys.argv[1])

    # Firmware string from control IN responses
    for e in ev:
        if e["func"] == 8 and e["ep"] == 0x80 and e["payload"]:
            txt = bytes(e["payload"]).split(b"\x00")[0]
            if txt.startswith(b"V") and b"_FX_LCD_" in txt:
                print(f"firmware: {txt.decode()}")

    outs = [e["payload"] for e in ev
            if e["func"] == 9 and e["ep"] == 0x01 and len(e["payload"])]
    print(f"OUT interrupt reports: {len(outs)}")
    cmds = {}
    for p in outs:
        if p[:5] == b"CRT\x00\x00":
            cmds[bytes(p[5:8]).decode("ascii", "replace")] = \
                cmds.get(bytes(p[5:8]).decode("ascii", "replace"), 0) + 1
    print(f"CRT commands: {cmds}")

    heads = [p for p in outs if p[:8] == b"CRT\x00\x00DRA"]
    conts = [p for p in outs
             if not (p[:5] == b"CRT\x00\x00" and p[5:8].isalpha())]
    # continuations = non-CRT reports after the first 3 (DIS/LIG/LIG)
    rest = outs[3:]
    ok, fails = 0, 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(rest), 2):
        ann, cont = rest[i], rest[i + 1]
        assert ann[:8] == b"CRT\x00\x00DRA", f"frame {i//2}: no DRA announce"
        size = int.from_bytes(ann[10:12], "big")
        blob = ann[32:] + cont
        assert blob.find(b"\xff\xd8") == 0, f"frame {i//2}: no SOI at 32"
        eoi = blob.find(b"\xff\xd9")
        jpg, tail = blob[:eoi + 2], blob[eoi + 2:]
        good = len(jpg) == size - 32 and set(tail) == {0}
        ok, fails = ok + good, fails + (not good)
        (out_dir / f"f{i//2:02d}.jpg").write_bytes(jpg)
        print(f"frame{i//2}: SIZE={size} actual={len(jpg)} "
              f"{'OK' if good else 'MISMATCH'}")
    print(f"{ok} OK / {fails} bad, carved to {out_dir}/")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
