#ifndef ESP32_CST_COMMON_COMPONENTS_H
#define ESP32_CST_COMMON_COMPONENTS_H

#include "freertos/event_groups.h"

#define ESP_WIFI_SSID CONFIG_ESP_WIFI_SSID
#define ESP_WIFI_PASS CONFIG_ESP_WIFI_PASSWORD
#define MAX_STA_CONN 16

#ifdef CONFIG_WIFI_CHANNEL
#define WIFI_CHANNEL CONFIG_WIFI_CHANNEL
#else
#define WIFI_CHANNEL 6
#endif

#define PASSIVE_WIFI_NATURE 0
#define ACTIVE_STA_WIFI_NATURE 1
#define ACTIVE_AP_WIFI_NATURE 2
#define APSTA_WIFI_NATURE 3

#ifdef CONFIG_WIFI_NATURE
#define WIFI_NATURE CONFIG_WIFI_NATURE
#else
#define WIFI_NATURE PASSIVE_WIFI_NATURE
#endif

#define DATA_EXPORT_FORMAT CONFIG_DATA_EXPORT_FORMAT
#define EXPORT_NOP 0
#define EXPORT_CSV 1
#define EXPORT_JSON 2
#define EXPORT_BASE64 3


#ifdef CONFIG_ENABLE_STBC_HTLTF
#define ENABLE_STBC_HTLTF 1
#define MAX_CSI_BYTES 612
#else
#define ENABLE_STBC_HTLTF 0
#define MAX_CSI_BYTES 384
#endif

#ifdef CONFIG_ENABLE_SUMMARY_STATS
#define ENABLE_SUMMARY_STATS
#else
#undef ENABLE_SUMMARY_STATS
#endif

static const char *TAG = "CSI_COLLECTION";
static EventGroupHandle_t s_wifi_event_group;
const int WIFI_CONNECTED_BIT = BIT0;

TaskHandle_t console_handle = NULL;
TaskHandle_t dowork_handle = NULL;


bool is_wifi_connected()
{
    return (xEventGroupGetBits(s_wifi_event_group) & WIFI_CONNECTED_BIT);
}
#endif