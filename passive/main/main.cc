#include <stdio.h>
#include <chrono>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_spi_flash.h"
#include "freertos/event_groups.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "../../_components/nvs_component.h"
#include "../../_components/csi_component.h"
#include "../../_components/time_component.h"
#include "../../_components/input_component.h"

#ifdef CONFIG_WIFI_CHANNEL
#define WIFI_CHANNEL CONFIG_WIFI_CHANNEL
#else
#define WIFI_CHANNEL 6
#endif

TaskHandle_t xHandle = NULL;

auto epoch_zero_timestamp = std::chrono::steady_clock::now();

void passive_init()
{
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_NULL));
    ESP_ERROR_CHECK(esp_wifi_start());

    const wifi_promiscuous_filter_t filt = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_DATA};

    int curChannel = WIFI_CHANNEL;

    esp_wifi_set_promiscuous(true);
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_channel(curChannel, WIFI_SECOND_CHAN_ABOVE);
}

extern "C" void app_main(void)
{
    nvs_init();
    passive_init();
    csi_init(PASSIVE);

    xTaskCreatePinnedToCore(&vTask_passive_loop, "vTask_passive_loop",
                            10000, NULL, tskIDLE_PRIORITY, &xHandle, 1);
}
