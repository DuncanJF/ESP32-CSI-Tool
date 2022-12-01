#!/bin/bash
ssid=CSI$(openssl rand -base64 16 | tr -dc A-Za-z0-9 | head -c8)
password=$(openssl rand -base64 32 | tr -dc A-Za-z0-9 | head -c16)
CSI_SSID=${1:-${CSI_SSID:-$ssid}}
CSI_PASSWORD=${2:-${CSI_PASSWORD:-$password}}
echo "${CSI_SSID}:${CSI_PASSWORD}"
sed -i -e"s/CONFIG_ESP_WIFI_SSID=\".\+\"/CONFIG_ESP_WIFI_SSID=\"${CSI_SSID}\"/" sdkconfig
sed -i -e"s/CONFIG_ESP_WIFI_PASSWORD=\".\+\"/CONFIG_ESP_WIFI_PASSWORD=\"${CSI_PASSWORD}\"/" sdkconfig
grep CONFIG_ESP_WIFI_SSID sdkconfig
grep CONFIG_ESP_WIFI_PASSWORD sdkconfig
