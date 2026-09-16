#!/usr/bin/env python3
"""One-shot calibration: replay vendor-captured packets to the pump.

Sends (byte-identical to temp/id-cooling-pump.pcapng):
  1. CRT DIS            (display on)
  2. DRA announce + continuation of frame f01 (solid red 240x240)

Run: python3 send_calibration.py
Then LOOK at the pump — it must turn solid red.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "tools"))
from usbpcap_parse import load_events  # noqa: E402

from hotspotek import Pump  # noqa: E402

PCAP = Path(__file__).parent / "temp" / "id-cooling-pump.pcapng"


def main():
    ev = load_events(str(PCAP))
    outs = [e["payload"] for e in ev
            if e["func"] == 9 and e["ep"] == 0x01 and len(e["payload"])]
    dis = outs[0]
    assert dis[:8] == b"CRT\x00\x00DIS", dis[:8]
    ann, cont = outs[3 + 2], outs[3 + 3]  # 2nd DRA pair = solid red
    assert ann[:8] == b"CRT\x00\x00DRA", ann[:8]
    assert ann[10:12] == b"\x06\x19", ann[8:14].hex(" ")

    with Pump() as pump:
        pump.send_report(dis)
        print("sent DIS (display on)")
        time.sleep(0.2)
        pump.send_report(ann)
        print("sent DRA announce (SIZE=1561, target 0xB1)")
        time.sleep(0.05)
        pump.send_report(cont)
        print("sent continuation (JPEG tail + FF D9)")
    print("done — check the pump screen (expect solid red).")


if __name__ == "__main__":
    main()
