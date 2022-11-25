#ifndef ESP32_CSI_INPUT_COMPONENT_H
#define ESP32_CSI_INPUT_COMPONENT_H

#include<unistd.h>
#include "csi_component.h"

char input_buffer[256] ={0};
char* input_buffer_end=input_buffer+254;
const TickType_t input_wait = pdMS_TO_TICKS(20);

void _handle_input() {
    printf("handle input_buffer: %s\n", input_buffer);
    if (match_set_timestamp_template(input_buffer)) {
        printf("Setting local time to %s\n", input_buffer);
        time_set(input_buffer);
    } else {
        printf("Unable to handle input %s\n", input_buffer);
    }
}

void input_check() {
    char* input_buffer_pointer=input_buffer;
    uint8_t ch = fgetc(stdin);
    while (ch != 0xFF && input_buffer_pointer < input_buffer_end) {                
        if (ch == '\n') {                        
            _handle_input();
            input_buffer[0] = '\0';
        } else {            
            *(input_buffer_pointer++) = ch;
            *(input_buffer_pointer) = '\0';
        }
        ch = fgetc(stdin);
    }
    if (input_buffer[0] != '\0') {
        ESP_LOGW(TAG, "Unhandled input_buffer: %s\n", input_buffer);
        input_buffer[0] = '\0';
    }
}

void input_loop() {
    while (true) {
        input_check();
        vTaskDelay(input_wait);
    }
}

void vTask_console_loop(void *pvParameters)
{
    while(true)
    {   

        
        input_check();
        vTaskDelay(input_wait);
    }
}

#endif //ESP32_CSI_INPUT_COMPONENT_H
