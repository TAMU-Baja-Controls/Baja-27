#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include <sys/unistd.h>
#include <sys/stat.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#include "esp_timer.h"
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"
#include "driver/gpio.h"
#include "driver/spi_common.h"

#include "racebox_ble.h"
#include "daq_types.h"

static const char *TAG = "MAIN_DAQ";

// Pinout for ESP32 DevKit V1
#define PIN_TACH_PRIMARY    GPIO_NUM_4   // Inductive sensor on spark plug lead
#define PIN_HALL_SECONDARY  GPIO_NUM_27  // 6-PPR Hall effect on secondary pulley

#define PIN_SD_MISO         GPIO_NUM_19
#define PIN_SD_MOSI         GPIO_NUM_13
#define PIN_SD_CLK          GPIO_NUM_18
#define PIN_SD_CS           GPIO_NUM_5
#define MOUNT_POINT         "/sdcard"
#define SD_BUF_SIZE         4096

// Firing & Tooth configuration
#define PULSES_PER_REV_PRI  1.0f
#define PULSES_PER_REV_SEC  6.0f

// Noise rejection blanking windows
#define SPARK_LOCKOUT_US    8000  // 8 ms lockout rejects ignition bounce (> 7,500 RPM)
#define SEC_LOCKOUT_US      500   // 0.5 ms lockout rejects switch bounce (> 20,000 RPM)

// FreeRTOS Handles
static QueueHandle_t daq_queue = NULL;

// Shared volatile telemetry variables
static volatile float g_latest_pri_rpm = 0.0f;
static volatile float g_latest_sec_rpm = 0.0f;

// Primary shaft timing
static volatile uint32_t g_pri_pulse_count = 0;
static volatile int64_t g_last_spark_time_us = 0;
static volatile int64_t g_spark_period_us = 0;

// Secondary shaft timing
static volatile int64_t g_last_sec_time_us = 0;
static volatile int64_t g_sec_period_us = 0;
static volatile bool g_sec_has_pulsed = false;

static racebox_data_t g_latest_racebox = {0};

// -----------------------------------------------------------------------------
// PRIMARY SHAFT: Inductive Spark Pickup (Pure Integer ISR)
// -----------------------------------------------------------------------------
static void IRAM_ATTR tach_isr_handler(void* arg) {
    int64_t now_us = esp_timer_get_time();
    int64_t dt_us = now_us - g_last_spark_time_us;

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
// SECONDARY SHAFT: Microsecond Period Measurement (< 1 RPM Resolution)
// -----------------------------------------------------------------------------
static void IRAM_ATTR sec_hall_isr_handler(void* arg) {
    int64_t now_us = esp_timer_get_time();
    int64_t dt_us = now_us - g_last_sec_time_us;

    if (dt_us > SEC_LOCKOUT_US) {
        if (g_last_sec_time_us > 0 && dt_us < 2000000) {
            g_sec_period_us = dt_us;
        }
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
// RPM PROCESSING & TELEMETRY ASSEMBLY TASK (20 Hz)
// -----------------------------------------------------------------------------
static void rpm_task(void *pvParameters) {
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(50)); // 20 Hz calculation loop

        int64_t now_us = esp_timer_get_time();

        // 1. Primary RPM calculation
        int64_t time_since_spark = now_us - g_last_spark_time_us;
        if (g_last_spark_time_us == 0 || time_since_spark > 1500000) {
            g_latest_pri_rpm = 0.0f;
        } else {
            int64_t period = g_spark_period_us;
            if (period > SPARK_LOCKOUT_US) {
                g_latest_pri_rpm = (60000000.0f / (float)period) / PULSES_PER_REV_PRI;
            }
        }

        // 2. Secondary RPM calculation via period timing
        int64_t time_since_sec = now_us - g_last_sec_time_us;
        if (!g_sec_has_pulsed || time_since_sec > 1000000) {
            g_latest_sec_rpm = 0.0f;
            g_sec_has_pulsed = false;
        } else if (g_sec_period_us > SEC_LOCKOUT_US) {
            g_latest_sec_rpm = (60000000.0f / (float)g_sec_period_us) / PULSES_PER_REV_SEC;
        }

        // 3. Assemble and queue DAQ frame
        daq_frame_t frame = {
            .timestamp_ms  = (uint32_t)(now_us / 1000),
            .primary_rpm   = g_latest_pri_rpm,
            .secondary_rpm = g_latest_sec_rpm,
            .speed_kph     = g_latest_racebox.speed_kph,
            .g_force_x     = g_latest_racebox.g_force_x,
            .g_force_y     = g_latest_racebox.g_force_y,
            .g_force_z     = g_latest_racebox.g_force_z,
            .fix_status    = g_latest_racebox.fix_status,
            .num_svs       = g_latest_racebox.num_svs
        };

        if (daq_queue != NULL) {
            xQueueSend(daq_queue, &frame, 0);
        }

        // Heartbeat terminal print every 500 ms (10 loops @ 20 Hz)
        static uint8_t log_divider = 0;
        if (++log_divider >= 10) {
            log_divider = 0;
            ESP_LOGI(TAG, "Pri: %4.0f | Sec: %4.0f | Spd: %4.1f mph | Sparks: %" PRIu32,
                     g_latest_pri_rpm, g_latest_sec_rpm,
                     g_latest_racebox.speed_kph / 1.609f, g_pri_pulse_count);
        }
    }
}

// -----------------------------------------------------------------------------
// SD CARD AND FILE LOGGING
// -----------------------------------------------------------------------------
static void init_sdcard(void) {
    esp_vfs_fat_sdmmc_mount_config_t mount_config = {
        .format_if_mount_failed = false,
        .max_files = 3,
        .allocation_unit_size = 16 * 1024
    };
    sdmmc_host_t host = SDSPI_HOST_DEFAULT();
    spi_bus_config_t bus_cfg = {
        .mosi_io_num = PIN_SD_MOSI,
        .miso_io_num = PIN_SD_MISO,
        .sclk_io_num = PIN_SD_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = SD_BUF_SIZE,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(host.slot, &bus_cfg, SDSPI_DEFAULT_DMA));

    sdspi_device_config_t slot_config = SDSPI_DEVICE_CONFIG_DEFAULT();
    slot_config.gpio_cs = PIN_SD_CS;
    slot_config.host_id = host.slot;

    sdmmc_card_t *card;
    ESP_ERROR_CHECK(esp_vfs_fat_sdspi_mount(MOUNT_POINT, &host, &slot_config, &mount_config, &card));
    ESP_LOGI(TAG, "SD Card mounted successfully.");
}

static void sd_writer_task(void *pvParameters) {
    FILE *f = fopen(MOUNT_POINT "/cvt_run.csv", "a");
    if (!f) {
        ESP_LOGE(TAG, "Failed to open CSV file.");
        vTaskDelete(NULL);
    }
    
    fputs("timestamp_ms,pri_rpm,sec_rpm,speed_mph,g_x,g_y,g_z,fix_status,sat_count\n", f);
    fflush(f);
    fsync(fileno(f));

    static char write_buf[SD_BUF_SIZE];
    size_t buf_pos = 0;
    daq_frame_t frame;
    char line[128];
    uint32_t last_sync = (uint32_t)(esp_timer_get_time() / 1000);

    while (1) {
        if (xQueueReceive(daq_queue, &frame, pdMS_TO_TICKS(50)) == pdTRUE) {
            int len = snprintf(line, sizeof(line),
                            "%" PRIu32 ",%.1f,%.1f,%.2f,%.3f,%.3f,%.3f,%u,%u\n",
                            frame.timestamp_ms, frame.primary_rpm, frame.secondary_rpm,
                            frame.speed_kph / 1.609f, frame.g_force_x, frame.g_force_y, frame.g_force_z,
                            frame.fix_status, frame.num_svs);

            if (buf_pos + len >= SD_BUF_SIZE) {
                fwrite(write_buf, 1, buf_pos, f);
                buf_pos = 0;
            }
            memcpy(write_buf + buf_pos, line, len);
            buf_pos += len;
        }

        uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
        if (now - last_sync >= 1000) {
            if (buf_pos > 0) {
                fwrite(write_buf, 1, buf_pos, f);
                buf_pos = 0;
            }
            fflush(f);
            fsync(fileno(f));
            last_sync = now;
        }
    }
}

// -----------------------------------------------------------------------------
// RACEBOX BLE MONITOR TASK (Telemetry Cache Only)
// -----------------------------------------------------------------------------
static void racebox_monitor_task(void *pvParameters) {
    racebox_data_t rb = {0};

    while (1) {
        if (racebox_get_data(&rb)) {
            g_latest_racebox = rb;
        }
        vTaskDelay(pdMS_TO_TICKS(20)); // Poll at 50 Hz
    }
}

// -----------------------------------------------------------------------------
// APPLICATION ENTRY POINT
// -----------------------------------------------------------------------------
void app_main(void) {
    ESP_LOGI(TAG, "Starting DAQ system...");

    daq_queue = xQueueCreate(50, sizeof(daq_frame_t));
    if (daq_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create DAQ queue.");
        return;
    }

    // 1. Primary Tachometer (8ms Blanking ISR)
    init_primary_tach(PIN_TACH_PRIMARY);

    // 2. Secondary Tachometer (Period Timing ISR)
    init_secondary_tach(PIN_HALL_SECONDARY);

    // 3. Mount SD & Initialize BLE
    init_sdcard();
    racebox_init();

    // 4. Tasks (Core 0: Math & Calculation | Core 1: SD card flash & BLE radio)
    xTaskCreatePinnedToCore(rpm_task, "rpm_task", 4096, NULL, 5, NULL, 0);
    xTaskCreatePinnedToCore(sd_writer_task, "sd_writer", 4096, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(racebox_monitor_task, "rb_monitor", 4096, NULL, 4, NULL, 1);
}