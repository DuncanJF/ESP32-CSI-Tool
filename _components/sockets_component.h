#ifndef ESP32_CST_SOCKETS_COMPONENT_H
#define ESP32_CSI_SOCKETS_COMPONENT_H
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/types.h>
#include <unistd.h>
#include <signal.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include <esp_http_server.h>

#include "common_component.h"

char *data = (char *)"1\n";

#ifndef CONFIG_PACKET_RATE
#define CONFIG_PACKET_RATE 100
#endif

const TickType_t long_xDelay = pdMS_TO_TICKS(1000);
const long packet_dt_us = (long)1000000 / CONFIG_PACKET_RATE; // delay in microseconds!

auto packet_tick = std::chrono::steady_clock::now();
auto packet_tock = std::chrono::steady_clock::now();
long dt = 0;
uint32_t too_slow = 0;
uint32_t too_slow_report_interval = 1024;
TickType_t dyn_delay = 0;

void socket_transmitter_sta_loop()
{
    int socket_fd = -1;
    while (1)
    {
        close(socket_fd);
        char *ip = (char *)"192.168.4.1";
        struct sockaddr_in caddr;
        caddr.sin_family = AF_INET;
        caddr.sin_port = htons(2223);
        while (!is_wifi_connected())
        {
            // wait until connected to AP
            printf("wifi not connected. waiting...\n");
            vTaskDelay(long_xDelay);
        }
        printf("initial wifi connection established.\n");
        if (inet_aton(ip, &caddr.sin_addr) == 0)
        {
            printf("ERROR: inet_aton\n");
            continue;
        }

        socket_fd = socket(PF_INET, SOCK_DGRAM, 0);
        if (socket_fd == -1)
        {
            printf("ERROR: Socket creation error [%s]\n", strerror(errno));
            continue;
        }
        if (connect(socket_fd, (const struct sockaddr *)&caddr, sizeof(struct sockaddr)) == -1)
        {
            printf("ERROR: socket connection error [%s]\n", strerror(errno));
            continue;
        }

        printf("sending frames.\n");
        while (1)
        {
            if (!is_wifi_connected())
            {
                printf("ERROR: wifi is not connected\n");
                break;
            }
            packet_tock = std::chrono::steady_clock::now();
            dt = packet_dt_us - std::chrono::duration_cast<std::chrono::microseconds>(packet_tock - packet_tick).count();
            if (dt > 0)
            {
                /*
                 * If the required delay is 2 or more ticks use vTaskDelay.
                 * vTaskDelay(1) is too inaccuarate and unsteady to maintain a packet rate so for
                 * a delay < 2 use a microseconds delay.
                 */
                dyn_delay = pdMS_TO_TICKS(dt / 1000);
                ESP_LOGD(TAG, "# dyn_delay=%d, dt=%ld\n", dyn_delay, dt);
                if (dyn_delay >= 2)
                {
                    vTaskDelay(dyn_delay);
                }
                else if (dt > 0)
                {
                    ets_delay_us(dt);
                }
            }
            else
            {
                ++too_slow;
                if (too_slow > too_slow_report_interval)
                {
                    ESP_LOGW(TAG, "# Interval between sending frames too slow to maintain requested packet rate.  Send too late by %ld microseconds.", -dt);
                    too_slow = 0;
                }
            }
            packet_tick = packet_tock;

            if (sendto(socket_fd, &data, strlen(data), 0, (const struct sockaddr *)&caddr, sizeof(caddr)) !=
                strlen(data))
            {
                taskYIELD();
                continue;
            }
            taskYIELD();
        }
    }
}

void vTask_socket_loop(void *pvParameters)
{
    for (;;)
    {
        socket_transmitter_sta_loop();
    }
}
#endif