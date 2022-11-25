#!/usr/bin/env python3
import serial
import time
import sys
import os
import orjson as json


def main(args):
    # args: tty device, destination file, baud rate, duration
    default_baud = 4000000
    default_duration=10

    start = time.time_ns()
    largs = len(args)
    if largs:
        tty_name = args[0]
    else:
        found = [f for f in ["/dev/ttyUSB0", "/dev/ttyACM0"] if os.path.exists(f)]
        if found:
            tty_name = found[0]        
        else:
            print("Unable to identify a suitable tty to read.")
            sys.exit()        
    
    if largs > 1:
        outfile=args[1]
    else:
        dev_name = os.path.basename(tty_name)
        outfile = f"{start}_{dev_name}"

    if largs > 2:
        baud = int(args[2])
    else:
        baud = default_baud

    if largs > 3:
        duration = int(args[4])
    else:
        duration = default_duration

    ser = serial.Serial(tty_name, baud)
    
    dt = 0

    start = time.time_ns()
    with open(outfile, "w") as w:
        while dt < duration * 1000_000_000:
            data = ser.readline()
            if data:
                w.write(data.decode("utf-8"))
            dt = time.time_ns() - start


if __name__ == "__main__":
    main(sys.argv[1:])
