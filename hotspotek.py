"""Minimal HID transport for the ID-COOLING FX240 pump (2000:3000).

Report layout (see docs/PROTOCOL.md): 1024-byte output reports, no
ReportID on the wire. python-hid's write() takes the report ID as the
first byte; our descriptor declares no numbered reports, so hidapi
strips a leading 0x00 and exactly 1024 bytes reach the device.
"""

import time

import hid

import rlcd15

VID = 0x2000
PID = 0x3000
OUT_LEN = 1024
FRAME_GAP = 0.05  # >=50 ms between reports (vendor streams ~19 fps)


class Pump:
    def __init__(self):
        self.dev = hid.Device(vid=VID, pid=PID)

    def send_report(self, report: bytes):
        assert len(report) == OUT_LEN, f"report must be {OUT_LEN} B"
        # Leading 0x00 = report ID 0 (stripped by hidapi, not sent).
        n = self.dev.write(b"\x00" + report)
        # hidapi counts the report-ID prefix: 1025 == 1 + 1024 on the wire.
        assert n in (OUT_LEN, OUT_LEN + 1), f"short write: {n}"

    def send_frame(self, jpeg: bytes):
        """Upload one JPEG frame (DRA announce + chunks, paced)."""
        for rep in rlcd15.frame_reports(jpeg):
            self.send_report(rep)
            time.sleep(FRAME_GAP)

    def display_on(self):
        self.send_report(rlcd15.cmd_dis())

    def set_brightness(self, value: int):
        self.send_report(rlcd15.cmd_brightness(value))

    def close(self):
        self.dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
