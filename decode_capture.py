#!/usr/bin/env python3
# Extract exported CSI records from a capture file; decode them; and 
# write out as json dicts.
from base64 import b64decode
import sys
import orjson as json
import binascii
import struct
from logging import warning, info


COLUMN_NAMES = [
    "BOM",
    "data_export_format",
    "record_length",
    "csi_export_format",
    "project_type",
    "this_mac1",
    "this_mac2",
    "this_mac3",
    "this_mac4",
    "this_mac5",
    "this_mac6",
    "tv_sec",
    "tv_usec",
    "rx_timestamp",
    "pkt_mac1",
    "pkt_mac2",
    "pkt_mac3",
    "pkt_mac4",
    "pkt_mac5",
    "pkt_mac6",
    "rssi",
    "rate",
    "sig_mode",
    "mcs",
    "cwb",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "noise_floor",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "rx_timestamp2",
    "ant",
    "sig_len",
    "rx_state",
    "csi_len",
    "csi_data",
    "rx_timestamp_guard",
]

NO_STBC_HTLTF_ROWLEN=452
# Constant prefix created by the BOM.
BASE64_LINE_PREFIX="/v"
def decode_base64(txt):
    btxt = b64decode(txt)
    bom, fmt, rlen = struct.unpack_from("<IHi", btxt)    
    row = None
    # print(f"DJF {bom}, {fmt}, {rlen}")
    if bom == 65534 and rlen == NO_STBC_HTLTF_ROWLEN:
        # print("DJF ok")
        row = struct.unpack_from("<IHiHB6BIII6Bb10Bb3BIBHBH384sI", btxt)    
        # print(f"DJF row: {row}")
        row = {k: v for k, v in zip(COLUMN_NAMES, row)}        
        # print(f"DJF dict: {row}")
        row["this_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(row.pop("this_mac1"), row.pop("this_mac2"), row.pop("this_mac3"), row.pop("this_mac4"), row.pop("this_mac5"), row.pop("this_mac6"))
        row["pkt_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(row.pop("pkt_mac1"), row.pop("pkt_mac2"), row.pop("pkt_mac3"), row.pop("pkt_mac4"), row.pop("pkt_mac5"), row.pop("pkt_mac6"))
        row["csi_data"] = struct.unpack_from("384b", row["csi_data"])    
    return row


def decode_json(txt):
    row=json.loads(txt)
    row = {k: v for k, v in zip(COLUMN_NAMES, row)}
    row["this_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(row.pop("this_mac1"), row.pop("this_mac2"), row.pop("this_mac3"), row.pop("this_mac4"), row.pop("this_mac5"), row.pop("this_mac6"))
    row["pkt_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(row.pop("pkt_mac1"), row.pop("pkt_mac2"), row.pop("pkt_mac3"), row.pop("pkt_mac4"), row.pop("pkt_mac5"), row.pop("pkt_mac6"))
    row["csi_data"] = b64decode(row["csi_data"])
    return row

def decode_somehow(txt):
    rtn=None
    try:
        if txt.startswith("[") and txt.endswith("]"):
            rtn=decode_json(txt)
        elif txt.startswith(BASE64_LINE_PREFIX):        
            rtn=decode_base64(txt)        
    except KeyboardInterrupt as e:
        raise e
    except (binascii.Error, struct.error) as e:
        print("Decoding error ",e)
        return None
    except Exception as e:
        warning(f"Failed to decode input text: {txt} => {rtn}")
        return None
    
    if not rtn:
        return None
    ok = rtn["rx_timestamp_guard"] == rtn["rx_timestamp"]
    if ok:
        return rtn
    else:
        return None


def main(args):
    for infile in args:
        info(f"infile={infile}")
        with open(infile, "r") as r:
            decoded = list(filter(lambda x: x is not None, [decode_somehow(line) for line in r ]))
            for d in decoded:                
                print(json.dumps(d))


if __name__ == "__main__":
    main(sys.argv[1:])
