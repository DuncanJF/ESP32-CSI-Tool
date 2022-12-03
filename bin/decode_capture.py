#!/usr/bin/env python3
# Extract exported CSI records from a capture file; decode them; and
# write out as json dicts.
import binascii
import struct
import sys
from base64 import b64decode
from logging import info, warning
import numpy as np
from typing import List, Union
from numpy.typing import ArrayLike, DTypeLike

import orjson as json


class CsiError(Exception):
    pass

class CSIDataBadLength(CsiError):
    pass

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
    "sig_mode", # signal_mode
    "mcs",
    "cwb",  # channel bandwidth
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
    "first_word_invalid",
    "csi_len",
    "csi_data",
    "rx_timestamp_guard",
]

# Constant prefix created by the BOM.
BASE64_LINE_PREFIX = "/v"


def decode_base64(txt):
    btxt = b64decode(txt)

    bom, fmt, rlen = struct.unpack_from("<IHi", btxt)
    row = None    
    if bom == 65534:        
        row = struct.unpack_from("<IHiHB6BIII6Bb10Bb3BIBHBBH384sI", btxt)
        row = {k: v for k, v in zip(COLUMN_NAMES, row)}
        row["this_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(
            row.pop("this_mac1"),
            row.pop("this_mac2"),
            row.pop("this_mac3"),
            row.pop("this_mac4"),
            row.pop("this_mac5"),
            row.pop("this_mac6"),
        )
        row["pkt_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(
            row.pop("pkt_mac1"),
            row.pop("pkt_mac2"),
            row.pop("pkt_mac3"),
            row.pop("pkt_mac4"),
            row.pop("pkt_mac5"),
            row.pop("pkt_mac6"),
        )
        row["csi_data"] = struct.unpack_from("384b", row["csi_data"])
        row["first_word_invalid"]=True if row["first_word_invalid"] else False
    return row


def decode_json(txt):
    row = json.loads(txt)
    row = {k: v for k, v in zip(COLUMN_NAMES, row)}
    row["this_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(
        row.pop("this_mac1"),
        row.pop("this_mac2"),
        row.pop("this_mac3"),
        row.pop("this_mac4"),
        row.pop("this_mac5"),
        row.pop("this_mac6"),
    )
    row["pkt_mac"] = "{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}".format(
        row.pop("pkt_mac1"),
        row.pop("pkt_mac2"),
        row.pop("pkt_mac3"),
        row.pop("pkt_mac4"),
        row.pop("pkt_mac5"),
        row.pop("pkt_mac6"),
    )
    row["csi_data"] = b64decode(row["csi_data"])
    return row

def remap_csi_indices(
    row : dict,
    missing_iq : complex = complex(0,0),
    fixed_record=True
) -> dict:
    """
    Convert the WiFi device configuration and ESP32 CSI data into a numerically ordered subindex array.

    See https://docs.espressif.com/projects/esp-idf/en/v4.4.2/esp32/api-guides/wifi.html?highlight=ht%20ltf#wi-fi-channel-state-information
    
    CSI data from an ESP32 is in 8bit signed, QIQIQI format.
    The data from the legacy, high-throughput and STBC CSI are returned in the same array.
    The mapping of IQ values to individual sub-carrier indices depends on the secondary channel,
    signal mode, channel bandwidth and stbc.
    If first_word_invalid is Ture then the first 4 bytes of the QIQI data are inavlid.  In this case these bytes are set to missing_iq 

    This method:
      *  Separates the CSI into to three arrays - legacy, high-throughput and STBC high-throughput.
      *  Swaps the QI pairs to IQ pairs.
      *  Reorders the IQ pairs so the data is in order of increasing subindex.
      *  Absent IQ values are given the value from missing_iq (default 0+j0)
    
    This way each index of each CSI array refers to the same subchannel.
    
    NOTES:
    802.11n transmits on 20MHz wide channels.  Each 20MHz channel is subdivided into 64 subchannels. There are normally indexed (k=) -32,-31, ... ,30, 31 (inclusive).
    To make a 40MHz channel 2 20 MHz wide channels are used, a primary and a secondary.  In this case the subchannels are indexed (k=) from -64,-63, ... ,62, 33 (inclusive).
    Where the primary channel is in the middle of the 2.4GHz wifi band the secondary channel can be either below or above the primary channel ie. PS or SP.
    In the PS case the primary channel is mapped onto subchannel indexes -64 .. -1 and the secondary channel is mapped onto subindixes 0 .. 63.
    In the SP case the primary channel is mapped onto subchannel indexes 0 .. 63 and the secondary channel is mapped onto subindixes -64 .. -1.
    The Legacy symbol CSI comes from just the primary channel and only ever covers the primary 64 subchannels (20MHz bandwidth)

    In performing the subchannel index remapping the CSI data is copied to numpy arrays such that array index position 0 is the lowest subchannel index (-32 or -64 )
    Where there is no secondary channel the array is fixed at size 64.
    Where there is a secondary channel the array is fixed at size 128 and the lower frequency channel is mapped to subchannel indeces -64 ... -1 while the higher
    frequency subchannel is mapped to subchannel indeces 0 .. 63.
    Where there are not 64 CSI values then the absent channels are padded with 0+j0

    """
    first_word_invalid:int = row["first_word_invalid"]
    secondary_channel:int = row["secondary_channel"] # secondary channel on which this packet is received. 0: none; 1: above; 2: below 
    signal_mode :int = row["sig_mode"]   # 0: non HT(11bg) packet; 1: HT(11n) packet; 3: VHT(11ac) packet
    stbc  :int = row["stbc"] # Space Time Block Code(STBC). 0: non STBC packet; 1: STBC packet 
    channel_bandwidth :int = row["cwb"]  # Channel Bandwidth of the packet. 0: 20MHz; 1: 40MHz 

    csi_data : ArrayLike = np.array(row["csi_data"])
    if csi_data.shape[0] & 1:
        raise CsiError(f"Odd number of CSI values, should be even: {csi_data.shape}")

    # NOTE: QI swapped to IQ here!
    csi_data = 1j * csi_data[0::2] + csi_data[1::2]
    if first_word_invalid:
        csi_data[0]=missing_iq
        csi_data[1]=missing_iq
    csi_dtype : DTypeLike = csi_data.dtype
    actual_length :int = csi_data.shape[0]

    # Capture the CSI from the legacy long training field (LLTF), high troughput training field (HTLTF) and the "space time block code" high troughput training field separately.
    np_legacy_csi : Union[None,ArrayLike] = None
    np_ht_csi = None
    np_stbc_csi = None
    expected_length = 0

    wifi_config=f"{secondary_channel}{signal_mode}{channel_bandwidth}{stbc}"
    row["wifi_config"]=wifi_config
    
    if secondary_channel == 0:
        # No secondary channel.
        # Returned arrays are 64 elements long.
        ltf_idx= np.hstack([np.arange(32, 64), np.arange(0, 32)])            
        np_legacy_csi = np.full((64,), missing_iq, dtype=csi_dtype)
        np_ht_csi = np.full((64,), missing_iq, dtype=csi_dtype)
        np_stbc_csi = np.full((64,), missing_iq, dtype=csi_dtype)

        if signal_mode == 0 and channel_bandwidth == 0 and stbc == 0:
            # No secondary channel, bandwidth 20MHz, legacy only, no STBC
            # 128 bytes == 64 IQ pairs
            # LLTF 0~31, -32~-1
            expected_length = 64
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            ltf_idx= np.hstack([np.arange(32, 64), np.arange(0, 32)])
            np_legacy_csi = csi_data[ltf_idx]            
        elif signal_mode == 1 and channel_bandwidth == 0 and stbc == 0:
            # No secondary channel, bandwidth 20MHz, legacy and HT, no STBC
            # 256 bytes == 2 x 64 IQ pairs
            # LLTF 0~31, -32~-1
            # HT-LTF 0~31, -32~-1
            expected_length = 128
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            idx= np.hstack([np.arange(32, 64), np.arange(0, 32)])            
            np_legacy_csi = csi_data[ltf_idx]
            np_ht_csi = csi_data[ltf_idx+64]

        elif signal_mode == 1 and channel_bandwidth == 0 and stbc == 1:
            # No secondary channel, bandwidth 20MHz, legacy and HT, with STBC
            # 384 bytes == 3 x 64 IQ pairs
            # LLTF 0~31, -32~-1
            # HT-LTF 0~31, -32~-1
            # STBC HT-LTF 0~31, -32~-1
            expected_length = 192
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            np_legacy_csi = csi_data[ltf_idx]
            np_ht_csi = csi_data[ltf_idx+64]
            np_stbc_csi = csi_data[ltf_idx+128]
        else:            
            raise CsiError(
                f"Unsupported signal mode: secondary_channel={secondary_channel}, signal_mode={signal_mode}, channel_bandwidth={channel_bandwidth}, stbc={stbc}"
            )

    elif secondary_channel == 2:
        # Secondary channel below primary channel
        # Returned arrays are 128 elements long.        
        np_legacy_csi = np.full((128,), missing_iq, dtype=csi_dtype)
        np_ht_csi = np.full((128,), missing_iq, dtype=csi_dtype)
        np_stbc_csi = np.full((128,), missing_iq, dtype=csi_dtype)

        if signal_mode == 0 and channel_bandwidth == 0 and stbc == 0:
            # secondary channel below primary, bandwidth 20MHz, legacy only, no STBC
            # 128 bytes == 64 IQ pairs
            # LLTF 0~63
            expected_length = 64
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            idx = np.arange(0, 64) + 64
            np_legacy_csi[idx] = csi_data

        elif signal_mode == 1 and channel_bandwidth == 0 and stbc == 0:
            # secondary channel below primary, bandwidth 20MHz, legacy only, no STBC
            # 256 bytes == 2 x 64 IQ pairs
            # LLTF 0~63
            # HT-LLTF 0~63
            expected_length = 128
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            idx = np.arange(0, 64) + 64
            np_legacy_csi[idx] = csi_data[0:64]
            np_ht_csi[idx] = csi_data[64:]

        elif signal_mode == 1 and channel_bandwidth == 0 and stbc == 1:
            # secondary channel below primary, bandwidth 20MHz, legacy only, no STBC
            # 380 bytes == 1 x 64 IQ pairs (Legacy), 2 x 63 IQ pairs)
            # LLTF 0~64,
            # HT-LTF 0~62
            # STBC HT-LTF 0~62
            expected_length = 190
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            idx64 = np.arange(0, 64) + 64
            np_legacy_csi[idx64] = csi_data[0:64]
            idx63 = np.arange(0, 63) + 64
            np_ht_csi[idx63] = csi_data[64:127]
            np_stbc_csi[idx63] = csi_data[127:190]
        elif signal_mode == 1 and channel_bandwidth == 1 and stbc == 0:
            # secondary channel below primary, bandwidth 40MHz, legacy and HT,no STBC
            # 384 bytes == 1 x 64 IQ pairs + 1 x 128 IQ pairs
            # LLTF 0~63
            # HT-LLTF 0~63, -64~-1
            expected_length = 192
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            idx64 = np.arange(0, 64) + 64
            np_legacy_csi[idx64] = csi_data[0:64]
            ht_idx= np.hstack([np.arange(64, 128), np.arange(0, 64)]) + 64
            np_ht_csi =  csi_data[ht_idx]
        elif signal_mode == 0 and channel_bandwidth == 1 and stbc == 1:
            # secondary channel below primary, bandwidth 40MHz, legacy and HT, and STBC
            # 612 bytes == 1 x 64 IQ pairs + 2 x 121 IQ pairs
            # LLTF 0~63
            # HT-LLTF 0~60, -60~-1
            # STBC HT-LLTF 0~60, -60~-1
            expected_length = 306
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            idx64 = np.arange(0, 64) + 64
            np_legacy_csi[idx64] = csi_data[0:64]

            idx128 = np.hstack([np.arange(0, 61), np.arange(-60, 0)]) + 64
            np_ht_csi[idx128] = csi_data[64:185]
            np_stbc_csi[idx128] = csi_data[185:306]
        else:
            raise CsiError(
                f"Unsupported signal mode: secondary_channel={secondary_channel}, signal_mode={signal_mode}, channel_bandwidth={channel_bandwidth}, stbc={stbc}"
            )
    elif secondary_channel == 1:
        # Secondary channel above primary channel
        # Returned arrays are 128 elements long.
        np_legacy_csi = np.full((128,), missing_iq, dtype=csi_dtype)
        np_ht_csi = np.full((128,), missing_iq, dtype=csi_dtype)
        np_stbc_csi = np.full((128,), missing_iq, dtype=csi_dtype)
        if signal_mode == 0 and channel_bandwidth == 0 and stbc == 0:
            # secondary channel above primary, bandwidth 20MHz, legacy only, no STBC
            # 128 bytes == 64 IQ pairs
            # LLTF -64~-1
            expected_length = 64
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            np_legacy_csi[0:64] = csi_data[0:64]

        elif signal_mode == 1 and channel_bandwidth == 0 and stbc == 0:
            # secondary channel above primary, bandwidth 20MHz, legacy and HT, no STBC
            # 256 bytes == 2 x 64 IQ pairs
            # LLTF -64~-1
            # HT LTF -64~-1
            expected_length = 128
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            np_legacy_csi[0:64] = csi_data[0:64]
            np_ht_csi[0:64] = csi_data[64:128]

        elif signal_mode == 1 and channel_bandwidth == 0 and stbc == 1:
            # secondary channel above primary, bandwidth 20MHz, legacy and HT, STBC
            # 376 bytes == 1 x 64 IQ pairs + 2 x 62 IQ Pairs
            # LLTF -64~-1
            # HT LTF -62~-1
            # STBC HT LTF -62~-1
            expected_length = 188
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            np_legacy_csi[0:64] = csi_data[0:64]
            np_ht_csi[2:64] = csi_data[64:126]
            np_stbc_csi[2:64] = csi_data[126:]

        elif signal_mode == 1 and channel_bandwidth == 1 and stbc == 0:
            # secondary channel above primary, bandwidth 40MHz, legacy and HT, no STBC
            # 384 bytes == 1 x 64 IQ pairs, 1 x 128 IQ pairs
            # LLTF -64~-1
            # HT LTF 0-63, -64~-1            
            expected_length = 192
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            np_legacy_csi[0:64] = csi_data[0:64]
            ht_idx= np.hstack([np.arange(64, 128), np.arange(0, 64)]) + 64
            np_ht_csi = csi_data[ht_idx]
        elif signal_mode == 1 and channel_bandwidth == 1 and stbc == 1:
            # secondary channel above primary, bandwidth 40MHz, legacy and HT, and STBC
            # 612 bytes == 1 x 64 IQ pairs, 2 x 121 IQ pairs
            # LLTF -64~-1
            # HT-LLTF 0~60, -60~-1
            # STBC HT-LLTF 0~60, -60~-1
            expected_length = 192
            if not fixed_record and actual_length != expected_length:
                raise CSIDataBadLength(f"CSIDataBadLength: wifi_config={wifi_config}, expected={expected_length}, actual={actual_length}")
            np_legacy_csi[0:64] = csi_data[0:64]


            idx128 = np.hstack([np.arange(0, 61), np.arange(-60, 0)]) + 64
            np_ht_csi[idx128] = csi_data[64:185]
            np_stbc_csi[idx128] = csi_data[185:306]
        else:
            raise CsiError(
                f"Unsupported signal mode: secondary_channel={secondary_channel}, signal_mode={signal_mode}, channel_bandwidth={channel_bandwidth}, stbc={stbc}"
            )
    else:
        raise CsiError(
            f"Unsupported signal mode: secondary_channel={secondary_channel}, signal_mode={signal_mode}, channel_bandwidth={channel_bandwidth}, stbc={stbc}"
        )
    row["ltf_csi"]= np_legacy_csi    
    row["ht_csi"]=np_ht_csi
    row["stbcht_csi"]=np_stbc_csi
    return row

def isRecordOk(rec):
    ok = rec["rx_timestamp_guard"] == rec["rx_timestamp"]
    if ok:
        return rec
    else:
        raise CsiError("Record failed validity test.")

def npcmplx_to_list(arr):
    tmp = np.zeros([arr.shape[0]*2], dtype=np.int16)
    tmp[0::2] = np.real(arr)
    tmp[1::2] = np.imag(arr)
    return tmp.tolist()

def export_record(rec):
    """
    Numpy arrays cannot be serialized as JSON.
    Turn them into IQIQIQ lists.
    """
    if rec is None:
        return None
    rec["ltf_csi"]= npcmplx_to_list(rec["ltf_csi"])
    rec["ht_csi"]=npcmplx_to_list(rec["ht_csi"])
    rec["stbcht_csi"]=npcmplx_to_list(rec["stbcht_csi"])
    return rec

def decode_somehow(txt):
    missing_iq=complex(0,0)
    rec = None
    try:
        if txt.startswith("[") and txt.endswith("]"):
            rec = decode_json(txt)
        elif txt.startswith(BASE64_LINE_PREFIX):
            rec = decode_base64(txt)
        isRecordOk(rec)
        rec = remap_csi_indices(rec, missing_iq)
    except KeyboardInterrupt as e:
        raise e
    except (binascii.Error, struct.error) as e:
        warning(f"Decoding error: {e}")
        return None
    except Exception as e:
        warning(f"Failed to decode input text:\ntxt={txt}\nrec={rec}\nerr={e}.")
        return None
   
    return rec

def main(args):
    for infile in args:
        info(f"infile={infile}")
        with open(infile, "r") as r:
            decoded = list(
                filter(lambda x: x is not None, [export_record(decode_somehow(line)) for line in r])
            )       
            for d in decoded:
                print(d)

if __name__ == "__main__":
    main(sys.argv[1:])

