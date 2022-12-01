# ESP32 CSI Tool

[ESP32 CSI Tool Website](https://github.com/DuncanJF/ESP32-CSI-Tool)

This is a fork and modification of original code by [Steven M. Hernandez](https://stevenmhernandez.github.io/ESP32-CSI-Tool/)

The purpose of this project is to allow for the collection of Channel State Information (CSI) from the ESP32 family of Wi-Fi enabled microcontroller. 
By collecting this data rich signal source, we can use this information for tasks such as Wi-Fi Sensing and Device-free Localization directly from the small, self contained ESP32 microcontroller.  

This project has been reogranized (compared to the original) into a single tool with build time switching between different elements of a deployment (access point, transmitting station or passive receiver) configured at build time.  The SD card option of the original project has been removed. For this project (atm) all data export is over the serial port.  
Settings can be configured as described below.

## ESP32 Devices

There are lots of ESP32 devices out there.  The code in this repo has been succeasfully run with a serial port (UART/Console) BAUD of 4000000:

  * [FireBeetle 2](https://www.dfrobot.com/product-2195.html) -- 8MB Flash, No PSRAM
  * [ESP32-S3 DevKitC](https://www.dfrobot.com/product-2587.html) -- 4MB Flash, No PSRAM
  * [FeatherS3](https://shop.pimoroni.com/products/feathers3-esp32-s3?variant=39762596298835) -- (16MB Flash, 8MB PSRAM)
  * [Adafruit ESP32S3](https://shop.pimoroni.com/products/adafruit-esp32-s3-feather-with-4mb-flash-2mb-psram-stemma-qt-qwiic?variant=40017517215827) -- (4MB Flash, 2MB PSRAM)

## Installation

First, Install Espressif IoT Development Framework (ESP-IDF) by following their [step by step installation guide](https://docs.espressif.com/projects/esp-idf/en/release-v4.4/esp32/get-started/index.html).
Notice, this project assumes **version (v4.4) of ESP-IDF**.  

**Important:** It is important that you are able to successfully build and flash the example project from the esp-idf guide onto your own esp32.
If you have issues building the example project on your hardware, **do not create an issue in this github repo**.
We will not be able to assist with general ESP32 issues (those issues that are unrelated to this project).  

Next, clone this repository:

```
git clone https://github.com/DuncanJF/ESP32-CSI-Tool
cd  ESP32-CSI-Tool
```
or
```
git clone https://github.com/DuncanJF/ESP32-CSI-Tool local_folder_name
cd  local_folder_name
```

We can now begin configuring and flashing your ESP32.

**NB:** I typically make a clone the repo for each ESP32 device which I name from the devices mac address (see below). 

## Configuration (ESP-IDF)

### Preliminaries

The ESP-IDF provides great control over project configuration. 
This configuration can be updated by running the following commands from your terminal.

For these instructions it is assuming the ESP32 is connected to a device over USB as a serial port (tty).  If this is not the case then you will have to adapt the instructions accordingly.  

Identify the tty used to communicate with the ESP32 device.  On Linux this will typically be `/dev/ttyUSB0` or `/dev/ttyACM0` depending on ESP32 device.

```
export ESP_TTY="/dev/ttyUSB0"
```

Identiy the target ESP32 device.  Run the following command and look for the line with "--chip".  This will show the acceptable target names.
```
esptool.py -h
...  --chip {auto,esp8266,esp32,esp32s2,esp32s3beta2,esp32s3,esp32c3,esp32c6beta,esp32h2beta1,esp32h2beta2,esp32c2}, -c {auto,esp8266,esp32,esp32s2,esp32s3beta2,esp32s3,esp32c3,esp32c6beta,esp32h2beta1,esp32h2beta2,esp32c2} ...
```

Once the appropriate target device name has been identified set the build target.  For an ESP32S3 this would be:

```
idf.py set-target esp32s3
```

The same `esptool.py` can be used retrieve details of an ESP32 device. The following commands:

```
esptool.py -p $ESP_TTY flash_id
esptool.py -p $ESP_TTY chip_id
```

Can be used to get the device MAC address(+), amount of available flash and other retails.

(+) I have one device where the MAC address reported by esptool.py is different from the MAC address set on transmitted WiFi packets.

### Software configuration

```
idf.py menuconfig
```

The file `sdkconfig.ESP32S3` contains the settings I use for testing with ESP32S3 devices.  This includes various tweaks to maximize the WiFi throughput.
It also defaults to a baud rate of 4000000 which works for me over USB3.0.  YMMV.

The tool `set_wifi_password.sh` can be used to set the WiFi SSID and password.  The values will be taken from the environment variables CSI_SSID and CSI_PASSWORD or generated randomly if those are not set.

`CONFIG_PACKET_RATE`: Is only used by a device operating as a station.  In testing I have achieved close to but not quite 1000 packets per second with a single station.  If deploying multiple stations remember they are competing for the same over-the-air bandwidth.  An excessive packet rate will cause significant contention and the CSI capture rate will plummet.

`CONFIG_ENABLE_STBC_HTLTF`: STBC requires multiple transmit antennae.  In my deployments all devices have a single antenna so no STBC data will be seen.   The default configuration is to optimize data export for no STBC.  If you are interested in observing STBC CSI data then enable this (but it hasn't been widely tested).

### Build

```
idf.py build
```

### Flash ESP32

Run the following command:

```
idf.py -p $ESP_TTY flash
```

This will flash the ESP32 and once completed the device will be restarted and the code run.

Output from the device can be monitored with:

```
idf.py -p $ESP_TTY monitor
```
To exit monitoring, use `ctrl+]`

**NB.** Monitoring and data capture at the same time doesn't work.  Do one or the other.


## Collecting CSI Data

The script `python_utils/capture.py` is an example python script which can be used to capture data to a file.

## Analysing CSI Data


Three helper tools `capture.py`, `decode_capture.py` and `timings.py` can be found in the top level directory.

  *  `capture.py`: Depends on pyserial and simply (on linux) captures from tty and writes it to file.
  *  `decode_capture.py`: Depends on orjson and decodes base64 and JSON exported data to JSON which can be piped elsewhere for further analysis.
  *  `timings.py`: With ENABLE_SUMMARY_STATS enabled timing data around CSI extraction is logged, specifically time between CSI captures.  This tool extracts that data and summarizes it.

Different ESP32 have different antenna radiation patterns.  Even for devices with similar looking meandered-invereted-F antennae there can be significant variations.  If you are installing devices where directionality is important (eg. "facing" into a room) then mapping the radiation pattern is a necessary step.  The simplest way is to setup an access point and a station.  Keep one fixed and rotate the other while at a fixed distance to measure the RSSI at different angles. 


### Misc.

[ESP32 CSI Tool](https://stevenmhernandez.github.io/ESP32-CSI-Tool/) developed by [Steven M. Hernandez](https://github.com/StevenMHernandez)

[Cite this Tool with BibTeX](https://raw.githubusercontent.com/StevenMHernandez/ESP32-CSI-Tool/master/docs/bibtex/esp32_csi_tool_wowmom.bib)