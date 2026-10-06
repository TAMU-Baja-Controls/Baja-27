#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include <sys/unistd.h>
#include <sys/stat.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_timer.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "driver/twai.h"

#include "racebox_ble.h"
#include "daq_types.h"
#include "udp_telemetry.h"

static const char *TAG = "ACCEL_DAQ_CAN";

// -----------------------------------------------------------------------------
// HARDWARE PIN ASSIGNMENTS (ESP32 DevKit V1)
// -----------------------------------------------------------------------------
#define PIN_TACH_PRIMARY    GPIO_NUM_4    // Inductive spark pickup circuit
#define PIN_HALL_SECONDARY  GPIO_NUM_27   // 6-PPR Hall effect sensor

// TWAI / CAN Bus Transceiver Pins (SN65HVD230 / VP230)
#define PIN_CAN_TX          GPIO_NUM_21
#define PIN_CAN_RX          GPIO_NUM_22

// -----------------------------------------------------------------------------
// CAN IDENTIFIERS & TIMING CONFIGURATION
// -----------------------------------------------------------------------------
#define CAN_ID_RPM_CVT      0x200         // Primary & Secondary RPM (100 Hz)
#define CAN_ID_RACEBOX_GPS  0x201         // Speed, Fix, SV count (25 Hz)
#define CAN_ID_RACEBOX_IMU  0x202         // X, Y, Z accelerations (25 Hz)

#define PULSES_PER_REV_PRI  1.0f
#define SEC_TEETH_COUNT     6

#define SPARK_LOCKOUT_US    8000          // 8 ms lockout (> 7,500 RPM filter)
#define SEC_LOCKOUT_US      500           // 0.5 ms lockout (> 20,000 RPM filter)

// Shared variables
static volatile float g_latest_pri_rpm = 0.0f;
static volatile float g_latest_sec_rpm = 0.0f;

// Primary shaft timing
static volatile uint32_t g_pri_pulse_count = 0;
static volatile uint32_t g_last_spark_time_us = 0;
static volatile uint32_t g_spark_period_us = 0;

// Secondary shaft circular buffer
static volatile uint32_t g_sec_tooth_times[SEC_TEETH_COUNT] = {0};
static volatile uint8_t  g_sec_tooth_idx = 0;
static volatile uint32_t g_sec_full_rev_period_us = 0;
static volatile uint32_t g_last_sec_time_us = 0;
static volatile bool     g_sec_has_pulsed = false;

static racebox_data_t g_latest_racebox = {0};

// -----------------------------------------------------------------------------
// PRIMARY SHAFT: Inductive Spark Pickup ISR
// -----------------------------------------------------------------------------
static void IRAM_ATTR tach_isr_handler(void* arg) {
    uint32_t now_us = (uint32_t)esp_timer_get_time();
    uint32_t dt_us = now_us - g_last_spark_time_us;

    if (dt_us > SPARK_LOCKOUT_US) {
        g_pri_pulse_count++;
        if (g_last_spark_time_us > 0 && dt_us < 2000000) {
            g_spark_period_us = dt_us;
        }
        g_last_spark_time_us = now_us;
    }
}

static void init_primary_tach(gpio_num_t pin) {
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << pin),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));

    esp_err_t err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "Failed to install GPIO ISR service: %s", esp_err_to_name(err));
    }
    ESP_ERROR_CHECK(gpio_isr_handler_add(pin, tach_isr_handler, NULL));
}

// -----------------------------------------------------------------------------
// SECONDARY SHAFT: 6-Tooth Circular Buffer ISR
// -----------------------------------------------------------------------------
static void IRAM_ATTR sec_hall_isr_handler(void* arg) {
    uint32_t now_us = (uint32_t)esp_timer_get_time();
    uint32_t dt_us = now_us - g_last_sec_time_us;

    if (dt_us > SEC_LOCKOUT_US) {
        uint8_t oldest_idx = (g_sec_tooth_idx + 1) % SEC_TEETH_COUNT;
        uint32_t oldest_time = g_sec_tooth_times[oldest_idx];

        if (oldest_time > 0 && (now_us - oldest_time) < 2000000) {
            g_sec_full_rev_period_us = now_us - oldest_time;
        }

        g_sec_tooth_times[g_sec_tooth_idx] = now_us;
        g_sec_tooth_idx = oldest_idx;

        g_last_sec_time_us = now_us;
        g_sec_has_pulsed = true;
    }
}

static void init_secondary_tach(gpio_num_t pin) {
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << pin),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));
    ESP_ERROR_CHECK(gpio_isr_handler_add(pin, sec_hall_isr_handler, NULL));
}

// -----------------------------------------------------------------------------
// TWAI (CAN) INITIALIZATION (1 Mbps, Active Mode)
// -----------------------------------------------------------------------------
static void init_twai_bus(void) {
    twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(PIN_CAN_TX, PIN_CAN_RX, TWAI_MODE_NORMAL);
    twai_timing_config_t t_config = TWAI_TIMING_CONFIG_1MBITS();
    twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    // Increase transmit queue to absorb burst transmission smoothly
    g_config.tx_queue_len = 32;

    ESP_ERROR_CHECK(twai_driver_install(&g_config, &t_config, &f_config));
    ESP_ERROR_CHECK(twai_start());
    ESP_LOGI(TAG, "TWAI initialized at 1 Mbps on TX: %d, RX: %d", PIN_CAN_TX, PIN_CAN_RX);
}

// -----------------------------------------------------------------------------
// 100 Hz RPM & POWERTRAIN CAN BROADCAST (10 ms interval)
// -----------------------------------------------------------------------------
static void rpm_can_task(void *pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(10); // Exact 100 Hz loop

    twai_message_t rpm_msg = {
        .identifier = CAN_ID_RPM_CVT,
        .data_length_code = 8,
        .flags = TWAI_MSG_FLAG_NONE
    };

    while (1) {
        vTaskDelayUntil(&xLastWakeTime, xFrequency);

        uint32_t now_us = (uint32_t)esp_timer_get_time();

        // 1. Primary RPM calculation
        uint32_t time_since_spark = now_us - g_last_spark_time_us;
        if (g_last_spark_time_us == 0 || time_since_spark > 1500000) {
            g_latest_pri_rpm = 0.0f;
        } else {
            uint32_t period = g_spark_period_us;
            if (period > SPARK_LOCKOUT_US) {
                g_latest_pri_rpm = (60000000.0f / (float)period) / PULSES_PER_REV_PRI;
            }
        }

        // 2. Secondary RPM calculation
        uint32_t time_since_sec = now_us - g_last_sec_time_us;
        if (!g_sec_has_pulsed || time_since_sec > 1000000) {
            g_latest_sec_rpm = 0.0f;
            g_sec_has_pulsed = false;
        } else if (g_sec_full_rev_period_us > (SEC_LOCKOUT_US * SEC_TEETH_COUNT)) {
            g_latest_sec_rpm = 60000000.0f / (float)g_sec_full_rev_period_us;
        }

        // 3. Pack CAN Frame 0x200
        uint16_t pri_val = (g_latest_pri_rpm > 65535.0f) ? 65535 : (uint16_t)g_latest_pri_rpm;
        uint16_t sec_val = (g_latest_sec_rpm > 65535.0f) ? 65535 : (uint16_t)g_latest_sec_rpm;
        uint32_t timestamp_ms = now_us / 1000;

        // Big-endian / Network byte order
        rpm_msg.data[0] = (uint8_t)(pri_val >> 8);
        rpm_msg.data[1] = (uint8_t)(pri_val & 0xFF);
        rpm_msg.data[2] = (uint8_t)(sec_val >> 8);
        rpm_msg.data[3] = (uint8_t)(sec_val & 0xFF);
        rpm_msg.data[4] = (uint8_t)(timestamp_ms >> 24);
        rpm_msg.data[5] = (uint8_t)(timestamp_ms >> 16);
        rpm_msg.data[6] = (uint8_t)(timestamp_ms >> 8);
        rpm_msg.data[7] = (uint8_t)(timestamp_ms & 0xFF);

        twai_transmit(&rpm_msg, 0);

        // 4. Optional Live Telemetry Mirror (UDP)
        daq_frame_t frame = {
            .timestamp_ms  = timestamp_ms,
            .primary_rpm   = g_latest_pri_rpm,
            .secondary_rpm = g_latest_sec_rpm,
            .speed_kph     = g_latest_racebox.speed_kph,
            .g_force_x     = g_latest_racebox.g_force_x,
            .g_force_y     = g_latest_racebox.g_force_y,
            .g_force_z     = g_latest_racebox.g_force_z,
            .fix_status    = g_latest_racebox.fix_status,
            .num_svs       = g_latest_racebox.num_svs
        };
        telemetry_udp_send_frame(&frame);
    }
}

// -----------------------------------------------------------------------------
// 25 Hz RACEBOX BLE & CAN BROADCAST (40 ms interval)
// -----------------------------------------------------------------------------
static void racebox_can_task(void *pvParameters) {
    racebox_data_t rb = {0};
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(40); // 25 Hz loop

    twai_message_t gps_msg = {
        .identifier = CAN_ID_RACEBOX_GPS,
        .data_length_code = 8,
        .flags = TWAI_MSG_FLAG_NONE
    };

    twai_message_t imu_msg = {
        .identifier = CAN_ID_RACEBOX_IMU,
        .data_length_code = 6,
        .flags = TWAI_MSG_FLAG_NONE
    };

    while (1) {
        vTaskDelayUntil(&xLastWakeTime, xFrequency);

        if (racebox_get_data(&rb)) {
            g_latest_racebox = rb;
        }

        // CAN Frame 0x201: Speed (0.1 km/h resolution), Satellites, Fix
        uint16_t speed_scaled = (uint16_t)(g_latest_racebox.speed_kph * 10.0f);
        gps_msg.data[0] = (uint8_t)(speed_scaled >> 8);
        gps_msg.data[1] = (uint8_t)(speed_scaled & 0xFF);
        gps_msg.data[2] = g_latest_racebox.fix_status;
        gps_msg.data[3] = g_latest_racebox.num_svs;
        gps_msg.data[4] = 0;
        gps_msg.data[5] = 0;
        gps_msg.data[6] = 0;
        gps_msg.data[7] = 0;
        twai_transmit(&gps_msg, 0);

        // CAN Frame 0x202: Signed Accelerations (0.001 G resolution)
        int16_t gx = (int16_t)(g_latest_racebox.g_force_x * 1000.0f);
        int16_t gy = (int16_t)(g_latest_racebox.g_force_y * 1000.0f);
        int16_t gz = (int16_t)(g_latest_racebox.g_force_z * 1000.0f);
        imu_msg.data[0] = (uint8_t)(gx >> 8);
        imu_msg.data[1] = (uint8_t)(gx & 0xFF);
        imu_msg.data[2] = (uint8_t)(gy >> 8);
        imu_msg.data[3] = (uint8_t)(gy & 0xFF);
        imu_msg.data[4] = (uint8_t)(gz >> 8);
        imu_msg.data[5] = (uint8_t)(gz & 0xFF);
        twai_transmit(&imu_msg, 0);
    }
}

// -----------------------------------------------------------------------------
// APPLICATION ENTRY POINT
// -----------------------------------------------------------------------------
void app_main(void) {
    ESP_LOGI(TAG, "Booting Accelerated DAQ CAN Node...");

    // 1. Tachometer Hardware ISRs
    init_primary_tach(PIN_TACH_PRIMARY);
    init_secondary_tach(PIN_HALL_SECONDARY);

    // 2. Transceiver Initialization
    init_twai_bus();

    // 3. Wireless Services
    racebox_init();
    telemetry_udp_init();

    // 4. Threading Architecture
    // Core 0: Exact-timed 100 Hz RPM & Telemetry calculations
    xTaskCreatePinnedToCore(rpm_can_task, "rpm_can", 4096, NULL, 6, NULL, 0);

    // Core 1: BLE GATT Client + 25 Hz GPS/IMU CAN Transmit
    xTaskCreatePinnedToCore(racebox_can_task, "rb_can", 4096, NULL, 5, NULL, 1);
}