#include <stdio.h>
#include <sstream>
#include <string>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_spi_flash.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "lwip/err.h"
#include "lwip/sys.h"

#include "../../_components/common_component.h"
#include "../../_components/nvs_component.h"
#include "../../_components/priorities.h"
#include "../../_components/wifi_component.h"
#include "../../_components/csi_component.h"
#include "../../_components/time_component.h"
#include "../../_components/input_component.h"
#include "../../_components/sockets_component.h"

void station_init()
{
    station_wifi_init();
    csi_init((uint8_t)ACTIVE_STA_WIFI_NATURE);
    xTaskCreatePinnedToCore(&vTask_socket_loop, "vTask_socket_loop",
                            10000, NULL, tskIDLE_PRIORITY, &dowork_handle, 1);     
}

void ap_init()
{
    softap_init();
    csi_init((uint8_t)ACTIVE_AP_WIFI_NATURE);
}

void passive_init()
{
    passive_wifi_init();
    csi_init((uint8_t)PASSIVE_WIFI_NATURE);
}

void one_time_init_first()
{
    nvs_init();
}

void one_time_init_last()
{
    /* Listen on console for instuctions */
    /* Disabled for the moment
    xTaskCreatePinnedToCore(&vTask_console_loop, "vTask_console_loop",
                            10000, NULL, (UBaseType_t)CONSOLE_INPUT_PRIORITY, &console_handle, 1);
    */
}

extern "C" void app_main()
{
    one_time_init_first();
    uint8_t choice = (uint8_t)WIFI_NATURE;
    if (choice == ACTIVE_AP_WIFI_NATURE)
    {
        ap_init();
    }
    else if (choice == ACTIVE_STA_WIFI_NATURE)
    {
        station_init();
    }
    else //0
    {
        passive_init();
    }
    one_time_init_last();
}
