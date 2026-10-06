#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t itow;
    uint8_t  fix_status;  // 0: No Fix, 2: 2D Fix, 3: 3D Fix
    uint8_t  num_svs;     // Tracked satellites
    float    latitude;    // Degrees (-90.0 to +90.0)
    float    longitude;   // Degrees (-180.0 to +180.0)
    float    altitude_msl;// Height above Mean Sea Level (m)
    float    speed_kph;   // Ground speed (km/h)
    float    heading_deg; // Heading / Course over ground (deg)
    float    g_force_x;   // Lateral acceleration (G)
    float    g_force_y;   // Longitudinal acceleration (G)
    float    g_force_z;   // Vertical acceleration (G)
    float    gyro_x;      // Roll rate (deg/s)
    float    gyro_y;      // Pitch rate (deg/s)
    float    gyro_z;      // Yaw rate (deg/s)
    bool     valid;
} racebox_data_t;

void racebox_init(void);
bool racebox_get_data(racebox_data_t *out_data);
bool racebox_is_connected(void);

#ifdef __cplusplus
}
#endif