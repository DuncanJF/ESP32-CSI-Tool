#!/usr/bin/env python3
# Threaded capture of one or more tty.
# Captures to file in /tmp, assuming /tmp is in-memory (must faster)
# then copies to the final destination after capute is complete.
#
#
import os
import re
import sys
import threading
import time
from tempfile import mkdtemp
import logging
from logging import info, error
from typing import List, Dict, Union

import orjson as json
import serial
from math import ceil
import shutil


def default_timeout(duration: int, offset: float = 0.1):
    return offset + ceil(float(duration) / 1_000_000_000.0)


def parse_duration(duration: Union[str, int, float], want_seconds: bool = False) -> int:
    if isinstance(duration, str):
        m = re.match("^\s*(\d*\.\d+|\d+)\s*([mnu]?s)?", duration)
        if m is None:
            return None
        g = m.groups()
        num = g[0]
        if "." in num:
            num = float(num)
        else:
            num = int(num)
        unit = g[1]
    else:
        num = float(duration)
        unit = "s" if want_seconds else "ns"

    if unit:
        unit = unit.lower()
    if unit == "s":
        rtn = int(num * 1_000_000_000)
    elif unit == "ms":
        rtn = int(num * 1_000_000)
    elif unit == "us":
        rtn = int(num * 1_000)
    elif unit == "ns":
        rtn = int(num)
    elif want_seconds:
        # if want_seconds true then default units taken as seconds
        unit = "s"
        rtn = int(num * 1_000_000_000)
    else:
        # if want_seconds true then default units taken as seconds
        unit = "ns"
        rtn = int(num)

    if want_seconds:
        return float(rtn) / 1_000_000_000
    else:
        return rtn


def read_tty(opts: Dict):
    run_id = opts["run_id"]
    info(f"Begin action {run_id}.")
    info(f"thread opts={opts}")
    tty_dev: str = opts["tty_device"]
    baud = opts["baud"]
    duration: int = opts["duration"]
    timeout = opts.get("timeout", default_timeout(duration))
    tmpfile: str = opts["tmpfile"]
    os.makedirs(os.path.dirname(tmpfile), exist_ok=True)
    if not os.path.exists(tty_dev):
        return None

    ser = serial.Serial(tty_dev, baud, timeout=timeout)
    dt: int = 0
    start: int = time.time_ns()
    info(f"{run_id}: tmpfile={tmpfile}")
    with open(os.path.join(tmpfile), "wb") as wb:
        while dt < duration:
            data = ser.read()
            if data:
                wb.write(data)
            dt = time.time_ns() - start
    info(f"End action {run_id}.")


def capture_data(tty_opts):
    info("Begin capture data.")
    threads = []

    for tty, opts in tty_opts.items():
        info(f"Creating thread for {tty}.")
        threads.append(threading.Thread(target=read_tty, args=[opts]))

    for t in threads:
        tid = t.ident
        info(f"Starting thread {tid}.")
        t.start()

    for t in threads:
        tid = t.ident
        info(f"Joining thread {tid}.")
        t.join()
    info("End capture data.")


def copy_data(tty_opts):
    info("Begin copy data.")
    for tty, opts in tty_opts.items():
        tmpfile = opts["tmpfile"]
        destfile = opts["destfile"]
        os.makedirs(os.path.dirname(destfile), exist_ok=True)
        if tmpfile != destfile and os.path.exists(tmpfile):
            try:
                shutil.copy(tmpfile, destfile)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                error(e)
                continue
        os.unlink(tmpfile)
    info("End copy data.")


def main(args):
    timestamp: int = time.time_ns()
    default_baud: int = 4000000
    default_duration: str = "1s"
    run_name = [x[5:] for x in args if x.startswith("name:")]
    run_name = "_".join(run_name) if run_name else None
    run_id = f"{timestamp:016X}"

    # Allow mapping between tty names and more meaningful names.
    # ttymap file is JSON with the following format:
    # defaults are optional, anything unpecified assumes the default value if used.
    # {  "defaults": { "baud":4000000, "duration": "10s", "destdir": "/a/directory/path"},
    #    "/dev/ttyUSB0" : { "dev_name":"STATION1", "baud": 4000000,"macaddr":"00:11:22:33:44:55" , "destfile": "/a/file/path"},
    #    "/dev/ttyACM0" : { "dev_name":"ACCESS_POINT", "baud": 2000000}, "macaddr":"AA:BB:CC:DD:EE:FF", },
    #    ... }

    ttymap: Dict[str, Dict[str, Union[str, float, int]]] = {}
    ttymap_file: str = "ttymap.json"
    if os.path.exists(ttymap_file):
        with open(ttymap_file, "rb") as rb:
            jtxt = rb.read()
        ttymap = json.loads(jtxt)

    ttymap_defaults: Dict[str, Dict[str, Union[str, float, int]]] = ttymap.pop(
        "defaults", {}
    )
    if ttymap_defaults:
        if "baud" in ttymap_defaults:
            default_baud: int = ttymap_defaults.get("baud", default_baud)
        if "duration" in ttymap_defaults:
            default_duration: str = ttymap_defaults.get("duration", default_duration)

    if "tmpdir" in ttymap_defaults:
        tmpdir = ttymap_defaults
    else:
        tmpdir = mkdtemp(run_id, "CSI_", )

    if "destdir" in ttymap_defaults:
        destdir = ttymap_defaults
    else:
        destdir = os.getcwd()

    tty_args=[x for x in args if not x.startswith("name:")]
    if not tty_args:
        ttys: List[str] = [
            f"/dev/{x}" for x in os.listdir("/dev") if "ttyUSB" in x or "ttyACM" in x
        ]
    else:
        ttys: List[str] = [x for x in tty_args if os.path.exists(t)]

    info(f"Available tty: {ttys}")
    if ttys:
        run_prefix = f"{run_id}_{run_name}" if run_name else run_id
        tty_opts: Dict[str, Dict[str, Union[str, float, int]]] = {
            tty: ttymap.get(tty, {}) for tty in ttys
        }
        info(f"{(run_prefix)} Initial TTY options: {tty_opts}")

        for tty, opts in tty_opts.items():
            opts["run_id"] = run_id
            opts["run_name"] = run_name
            opts["run_prefix"] = run_prefix
            opts["tty_device"] = tty
            if "dev_name" not in opts:
                if "macaddr" in opts:
                    opts["dev_name"] = "_".join([opts["macaddr"], os.path.basename(tty)])
                else:
                    opts["dev_name"] = os.path.basename(tty)
            opts["duration"] = parse_duration(opts.get("duration", default_duration))
            if "timeout" not in opts:
                opts["timeout"] = default_timeout(opts["duration"])
            else:
                opts["timeout"] = parse_duration(opts["timeout"], want_seconds=True)

            if "baud" not in opts:
                opts["baud"] = default_baud

            filename = "_".join([run_prefix, opts["dev_name"]])
            opts["tmpfile"] = os.path.join(tmpdir, filename)
            if not "destfile" in opts:
                opts["destfile"] = os.path.join(destdir, filename)

        info(f"{(run_prefix)} Resolved TTY options: {tty_opts}")
        capture_data(tty_opts)
        copy_data(tty_opts)


if __name__ == "__main__":
    logging.basicConfig(encoding="utf-8", level=logging.DEBUG)
    main(sys.argv[1:])
