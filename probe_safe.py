#!/usr/bin/env python3
"""Phase 0 safe probe for ID-COOLING FX240 LCD (2000:3000 HOTSPOTEKUSB).

READ-ONLY by design. This script NEVER writes to the device:
  - no hid.write / send_feature_report / control OUT transfers
  - only: enumeration, sysfs descriptor dumps, device open,
    manufacturer/product strings, passive input-report reads

Exit codes: 0 = all good, 1 = device not found, 2 = permission denied
(expected before the udev rule is installed).
"""

import os
import struct
import sys

VID = 0x2000
PID = 0x3000

# ---------------------------------------------------------------- sysfs


def find_sysfs_dir():
    """Locate /sys/bus/usb/devices/<dev> for 2000:3000 via uevent files."""
    base = "/sys/bus/usb/devices"
    if not os.path.isdir(base):
        return None
    for entry in sorted(os.listdir(base)):
        uevent = os.path.join(base, entry, "uevent")
        try:
            with open(uevent, errors="ignore") as f:
                txt = f.read()
        except OSError:
            continue
        if "PRODUCT=2000/3000/" in txt:
            return os.path.join(base, entry)
    return None


def dump_sysfs(devdir):
    print(f"== sysfs: {devdir} ==")
    for name in ["idVendor", "idProduct", "bcdDevice", "speed",
                 "manufacturer", "product", "serial", "maxchild",
                 "bMaxPacketSize0", "bNumInterfaces", "configuration",
                 "bmAttributes", "bMaxPower", "urbnum", "version"]:
        p = os.path.join(devdir, name)
        try:
            with open(p, errors="ignore") as f:
                print(f"  {name} = {f.read().strip()}")
        except OSError as e:
            print(f"  {name} = <unreadable: {e}>")
    # interface + endpoints
    for sub in sorted(os.listdir(devdir)):
        if ":" in sub:  # e.g. 6-10:1.0
            print(f"  -- interface {sub} --")
            for name in ["bInterfaceClass", "bInterfaceSubClass",
                         "bInterfaceProtocol", "bNumEndpoints"]:
                p = os.path.join(devdir, sub, name)
                try:
                    with open(p, errors="ignore") as f:
                        print(f"    {name} = {f.read().strip()}")
                except OSError:
                    pass
            epdir = os.path.join(devdir, sub)
            for ep in sorted(os.listdir(epdir)):
                if ep.startswith("ep_"):
                    print(f"    endpoint {ep}:")
                    for name in ["type", "direction", "bEndpointAddress",
                                 "wMaxPacketSize", "bInterval"]:
                        p = os.path.join(epdir, ep, name)
                        try:
                            with open(p, errors="ignore") as f:
                                print(f"      {name} = {f.read().strip()}")
                        except OSError:
                            pass


# --------------------------------------------------- HID report descriptor


def parse_report_descriptor(raw: bytes):
    """Minimal HID report-descriptor walk: report sizes/counts only."""
    print(f"== HID report descriptor ({len(raw)} bytes) ==")
    print("  hex:", raw.hex(" "))
    i = 0
    size = 0
    count = 0
    while i < len(raw):
        prefix = raw[i]
        i += 1
        if prefix == 0xFE:  # long item, skip
            ln = raw[i]
            i += 2 + ln
            continue
        sizecode = prefix & 0x03
        sizecode = 4 if sizecode == 3 else sizecode
        typ = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        val = int.from_bytes(raw[i:i + sizecode], "little", signed=False)
        i += sizecode
        if typ == 1:  # global
            if tag == 7:
                size = val
            elif tag == 9:
                count = val
        elif typ == 0 and tag == 8:  # main: input
            print(f"  INPUT: report_size={size} count={count} "
                  f"-> {size * count} bits ({size * count // 8} bytes)")
        elif typ == 0 and tag == 9:  # main: output
            print(f"  OUTPUT: report_size={size} count={count} "
                  f"-> {size * count} bits ({size * count // 8} bytes)")
        elif typ == 0 and tag == 11:  # main: feature
            print(f"  FEATURE: report_size={size} count={count} "
                  f"-> {size * count} bits ({size * count // 8} bytes)")


# ------------------------------------------------------------------- main


def main():
    print("ID-COOLING FX240 LCD — Phase 0 safe probe (READ ONLY, no writes)")
    print(f"target {VID:04x}:{PID:04x}")
    print()

    devdir = find_sysfs_dir()
    if devdir is None:
        print("FATAL: USB device 2000:3000 not found. Check pump USB cable.")
        return 1
    dump_sysfs(devdir)
    print()

    # hidraw node + report descriptor (world-readable via sysfs)
    hidraw = None
    for root, _dirs, files in os.walk(devdir):
        for fn in files:
            if fn == "report_descriptor":
                rp = os.path.join(root, fn)
                try:
                    with open(rp, "rb") as f:
                        parse_report_descriptor(f.read())
                except OSError as e:
                    print(f"report_descriptor unreadable: {e}")
        # find hidraw child: <dev>:1.0/.../hidraw/hidrawN
    import glob
    matches = (glob.glob(os.path.join(devdir, "*/hidraw/hidraw*"))
               + glob.glob(os.path.join(devdir, "*/*/hidraw/hidraw*")))
    if matches:
        hidraw = os.path.basename(matches[0])
        print(f"== hidraw node: /dev/{hidraw} ==")
        try:
            st = os.stat(f"/dev/{hidraw}")
            print(f"  mode={oct(st.st_mode & 0o777)} uid={st.st_uid}")
        except OSError as e:
            print(f"  stat failed: {e}")
    else:
        print("WARNING: no hidraw node found under sysfs (driver unbound?)")
    print()

    # hidapi enumeration (no open yet)
    try:
        import hid
    except ImportError:
        print("SKIP: python 'hid' package not installed")
        return 0
    print("== hid.enumerate(0x2000, 0x3000) ==")
    devs = hid.enumerate(VID, PID)
    if not devs:
        print("  <empty> — device invisible to hidapi (permissions?)")
    for d in devs:
        for k in ["path", "vendor_id", "product_id", "serial_number",
                  "release_number", "manufacturer_string", "product_string",
                  "usage_page", "usage",
                  "input_report_length", "output_report_length",
                  "feature_report_length"]:
            print(f"  {k} = {d.get(k)!r}")
    print()

    # open + passive reads only
    print("== open (read-only intent) + passive reads ==")
    try:
        h = hid.Device(vid=VID, pid=PID)
    except Exception as e:  # PermissionError / HIDException before udev rule
        print(f"  open FAILED (expected before udev rule): {type(e).__name__}: {e}")
        print("  fix: sudo cp 99-fx-lcd.rules /etc/udev/rules.d/ && "
              "sudo udevadm control --reload-rules && sudo udevadm trigger")
        return 2
    try:
        print(f"  manufacturer = {h.manufacturer!r}")
        print(f"  product      = {h.product!r}")
        print(f"  serial       = {h.serial!r}")
        # Firmware-version query path: GET_REPORT(Input, id 0), same as the
        # official software issues on open. Control IN transfer = read-only.
        try:
            fw = h.get_input_report(0, 512)
            print(f"  get_input_report(0,512) -> {len(fw)} bytes")
            txt = bytes(fw).split(b"\x00")[0]
            print(f"    as text: {txt!r}")
            print(f"    hex head: {bytes(fw[:64]).hex(' ')}")
        except Exception as e:
            print(f"  get_input_report FAILED (non-fatal): "
                  f"{type(e).__name__}: {e}")
        h.read(512, timeout=300)  # warm-up; hidapi read takes timeout in ms
        print("  passive input reads (5 x 300ms, device talks first):")
        for n in range(5):
            data = h.read(512, timeout=300)
            if data:
                print(f"    [{n}] {len(data)} bytes: {bytes(data).hex(' ')}")
            else:
                print(f"    [{n}] <silence>")
    finally:
        h.close()
        print("  closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
