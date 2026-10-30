#pragma once
#include "daq_types.h"

void telemetry_udp_init(void);
void telemetry_udp_send_frame(const daq_frame_t *frame);