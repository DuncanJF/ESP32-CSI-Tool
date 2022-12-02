#!/usr/bin/env python3
import os
import re
import sys
import threading
import time
from tempfile import mkdtemp

import orjson as json
import serial


def runid():
    t = time.time_ns()
    return f"{t:016X}"


def parse_duration(duration):
    parts = re.split(r"(?<=\d)(\s*)(?=\D)", duration.strip())
    if not parts:
        return 0

    num = float(parts[0])
    if len(parts) == 2:
        unit = "s"
    else:
        unit = parts[-1]

    if unit == "s":
        return num * 1_000_000_000
    if unit == "ms":
        return num * 1_000_000
    if unit == "us":
        return num * 1_000
    if unit == "ns":
        return num


def capture(opts):
    tty_dev = opts["tty_dev"]
    baud = opts["baud"]
    duration = opts["duration"]
    name = opts["name"]
    outfile = opts["outfile"]

    if not os.path.exists(tty_dev):
        return None

    ser = serial.Serial(tty_dev, baud)
    dt = 0
    start = time.time_ns()
    with open(os.path.join(outfile), "wb") as wb:
        while (time.time_ns() - start) < duration:
            data = ser.read()
            if data:
                wb.write(data)


def main(args):
    timestamp = time.time_ns()
    default_baud = 4000000
    default_duration = 10
    rid = f"{timestamp:016X}"

    # Allow mapping between tty names and more meaningful names.
    # ttymap file is JSON with the following format:
    # defaults are optional, anything unpecified assumes the default value if used.
    # {  "defaults": { "baud":4000000, "duration": 10,},
    #    "/dev/ttyUSB0" : { "name":"STATION1", "baud": 4000000,"macaddr":"00:11:22:33:44:55"},
    #    "/dev/ttyACM0" : { "name":"ACCESS_POINT", "baud": 2000000}, "macaddr":"AA:BB:CC:DD:EE:FF", },
    #    ... }

    ttymap = {}
    ttymap_file = "ttymap.json"
    if os.path.exists(ttymap_file):
        with open(ttymap_file, "rb") as rb:
            jtxt = rb.read()
        ttymap = json.loads(jtxt)

    ttymap_defaults = ttymap.pop("defaults", {})
    if ttymap_defaults:
        if "baud" in ttymap_defaults:
            default_baud = ttymap_defaults.get("baud", default_baud)
        if "duration" in ttymap_defaults:
            default_duration = ttymap_defaults.get("duration", default_duration)

    if not args:
        ttys = [
            f"/dev/{x}" for x in os.listdir("/dev") if "ttyUSB" in x or "ttyACM" in x
        ]
    else:
        ttys = [x for x in args if os.path.exists(x)]

    tty_opts = {tty: ttymap.get(tty, {}) for tty in ttys}
    if tty_opts:
        tdir = mkdtemp("CSI_", rid)
        for tty, opts in tty_opts.items():
            opts["tty_dev"] = tty
            if "name" not in opts:
                if "macaddr" in opts:
                    opts["name"] = "_".join(opts["macaddr"], os.path.basename(tty))
                else:
                    opts["name"] = os.path.basename(tty)
            if "duration" not in opts:
                opts["duration"] = default_duration
            opts["duration"] = parse_duration(op["duration"])

            if "baud" not in op:
                op["baud"] = default_baud

            op["outfile"] = os.path.join(tdir, opts["name"])

        threads = []

        for tty, opts in tty_opts.items():
            threads.append(
                threading.Thread(
                    taget=capture,
                    args=(
                        rid,
                        opts,
                    ),
                )
            )
        for t in threads:
            t.start()
        for t in threads:
            t.join()


if __name__ == "__main__":
    main(sys.argv[1:])
