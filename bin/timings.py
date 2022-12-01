#!/usr/bin/env python3
# Extract timing information from a capture file
# and summarize the results.
import sys
import numpy as np
import orjson
def main(args):
    infile = args[0]
    times=[]
    with open(infile, "r") as r:
        for line in r:
            if "CSI_COLLECTION" in line and "{" in line:
                data=None
                jline = "{"+ line.split("{",1)[1]
                try:
                    data = orjson.loads(jline)
                except KeyboardInterrupt as e:
                    raise(e)
                except:
                    pass
                if data["msgid"] == 1:
                    times.append(data["dt since last call"])

    if times:
        t = np.array(times)
        print("N=",t.shape[0])        
        print("mean/10/50/90 percentile=",t.mean(), np.percentile(t, [10,50,90]))


if __name__ == "__main__":
    main(sys.argv[1:])