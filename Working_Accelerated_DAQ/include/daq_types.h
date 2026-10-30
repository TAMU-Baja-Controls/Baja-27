#pragma once

#include <stdint.h>
#include <stdbool.h>

typedef struct __attribute__((packed)) {
    uint32_t timestamp_ms;
    float    primary_rpm;
    float    secondary_rpm;
    float    speed_kph;
    float    g_force_x;
    float    g_force_y;
    float    g_force_z;
    uint8_t  fix_status;
    uint8_t  num_svs;
} daq_frame_t;
