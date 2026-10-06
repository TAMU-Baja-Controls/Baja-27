#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_bt.h"
#include "esp_gap_ble_api.h"
#include "esp_gattc_api.h"
#include "esp_gatt_defs.h"
#include "esp_bt_main.h"
#include "nvs_flash.h"
#include "racebox_ble.h"

static const char *TAG = "RACEBOX_BLE";

#define GATTC_APP_ID 0

// Nordic UART Service & TX Characteristic (Notify) UUIDs
static uint8_t nus_service_uuid128[16] = {
    0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0,
    0x93, 0xF3, 0xA3, 0xB5, 0x01, 0x00, 0x40, 0x6E
};

static uint8_t nus_tx_char_uuid128[16] = {
    0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0,
    0x93, 0xF3, 0xA3, 0xB5, 0x03, 0x00, 0x40, 0x6E
};

static racebox_data_t latest_data = {0};
static SemaphoreHandle_t data_mutex = NULL;

static esp_gatt_if_t gattc_if_handle = ESP_GATT_IF_NONE;
static uint16_t conn_id_handle = 0;
static esp_bd_addr_t server_bda = {0};
static bool is_connected = false;

// Reassembly buffer for streaming BLE notifications
static uint8_t rx_buffer[512];
static size_t rx_buf_len = 0;

static esp_ble_scan_params_t ble_scan_params = {
    .scan_type          = BLE_SCAN_TYPE_ACTIVE,
    .own_addr_type      = BLE_ADDR_TYPE_PUBLIC,
    .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ALL,
    .scan_interval      = 0x50,
    .scan_window        = 0x30,
    .scan_duplicate     = BLE_SCAN_DUPLICATE_ENABLE
};

static void process_stream(const uint8_t *data, size_t len) {
    if (rx_buf_len + len > sizeof(rx_buffer)) {
        rx_buf_len = 0; // Prevent overflow on framing errors
    }
    memcpy(rx_buffer + rx_buf_len, data, len);
    rx_buf_len += len;

    // Full frame = 2 Sync + 2 Class/ID + 2 Length + 80 Payload + 2 Checksum = 88 bytes
    while (rx_buf_len >= 88) {
        // Fast sync: Look for 0xB5 0x62 header
        if (rx_buffer[0] != 0xB5 || rx_buffer[1] != 0x62) {
            uint8_t *next_sync = (uint8_t *)memchr(rx_buffer + 1, 0xB5, rx_buf_len - 1);
            if (next_sync) {
                size_t drop_count = next_sync - rx_buffer;
                rx_buf_len -= drop_count;
                memmove(rx_buffer, next_sync, rx_buf_len);
            } else {
                rx_buf_len = 0; // No sync byte found in the entire buffer
            }
            continue;
        }

        // Message Class (0xFF) & ID (0x01)
        if (rx_buffer[2] != 0xFF || rx_buffer[3] != 0x01) {
            memmove(rx_buffer, rx_buffer + 1, --rx_buf_len);
            continue;
        }

        uint16_t payload_len = (uint16_t)(rx_buffer[4] | (rx_buffer[5] << 8));
        if (payload_len != 80) {
            memmove(rx_buffer, rx_buffer + 1, --rx_buf_len);
            continue;
        }

        size_t total_packet_len = 6 + payload_len + 2;
        if (rx_buf_len < total_packet_len) {
            break; // Awaiting remaining notification fragments
        }

        // 8-bit Fletcher Checksum over Class, ID, Length, and Payload
        uint8_t ck_a = 0, ck_b = 0;
        for (size_t i = 2; i < total_packet_len - 2; i++) {
            ck_a += rx_buffer[i];
            ck_b += ck_a;
        }

        if (rx_buffer[total_packet_len - 2] == ck_a && rx_buffer[total_packet_len - 1] == ck_b) {
            const uint8_t *p = rx_buffer + 6;

            // Safe unpacking using aligned local variables
            uint32_t raw_itow;
            int32_t  raw_lon, raw_lat, raw_alt, raw_spd, raw_head;
            int16_t  raw_gx, raw_gy, raw_gz, raw_rx, raw_ry, raw_rz;

            memcpy(&raw_itow, p + 0,  sizeof(raw_itow));
            memcpy(&raw_lon,  p + 24, sizeof(raw_lon));
            memcpy(&raw_lat,  p + 28, sizeof(raw_lat));
            memcpy(&raw_alt,  p + 36, sizeof(raw_alt));
            memcpy(&raw_spd,  p + 48, sizeof(raw_spd));
            memcpy(&raw_head, p + 52, sizeof(raw_head));
            memcpy(&raw_gx,   p + 68, sizeof(raw_gx));
            memcpy(&raw_gy,   p + 70, sizeof(raw_gy));
            memcpy(&raw_gz,   p + 72, sizeof(raw_gz));
            memcpy(&raw_rx,   p + 74, sizeof(raw_rx));
            memcpy(&raw_ry,   p + 76, sizeof(raw_ry));
            memcpy(&raw_rz,   p + 78, sizeof(raw_rz));

            if (xSemaphoreTake(data_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
                latest_data.itow         = raw_itow;
                latest_data.fix_status   = *(p + 20); // 1-byte access: safe anywhere
                latest_data.num_svs      = *(p + 23); // 1-byte access: safe anywhere
                latest_data.longitude    = raw_lon / 1e7f;
                latest_data.latitude     = raw_lat / 1e7f;
                latest_data.altitude_msl = raw_alt / 1000.0f;
                latest_data.speed_kph    = (raw_spd / 1000.0f) * 3.6f;
                latest_data.heading_deg  = raw_head / 1e5f;
                latest_data.g_force_x    = raw_gx / 1000.0f;
                latest_data.g_force_y    = raw_gy / 1000.0f;
                latest_data.g_force_z    = raw_gz / 1000.0f;
                latest_data.gyro_x       = raw_rx / 100.0f;
                latest_data.gyro_y       = raw_ry / 100.0f;
                latest_data.gyro_z       = raw_rz / 100.0f;
                latest_data.valid        = true;

                xSemaphoreGive(data_mutex);
            }
        }

        // Shift consumed packet out of the buffer
        rx_buf_len -= total_packet_len;
        if (rx_buf_len > 0) {
            memmove(rx_buffer, rx_buffer + total_packet_len, rx_buf_len);
        }
    }
}

static void esp_gap_cb(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
    switch (event) {
    case ESP_GAP_BLE_SCAN_PARAM_SET_COMPLETE_EVT:
        esp_ble_gap_start_scanning(30);
        break;

    case ESP_GAP_BLE_SCAN_RESULT_EVT: {
        esp_ble_gap_cb_param_t *scan_result = (esp_ble_gap_cb_param_t *)param;
        if (scan_result->scan_rst.search_evt == ESP_GAP_SEARCH_INQ_RES_EVT) {
            uint8_t *adv_name = NULL;
            uint8_t adv_name_len = 0;
            adv_name = esp_ble_resolve_adv_data(scan_result->scan_rst.ble_adv,
                                                ESP_BLE_AD_TYPE_NAME_CMPL, &adv_name_len);
            if (adv_name && adv_name_len >= 7 && memcmp(adv_name, "RaceBox", 7) == 0) {
                ESP_LOGI(TAG, "Found target device: %.*s", adv_name_len, adv_name);
                esp_ble_gap_stop_scanning();
                if (!is_connected) {
                    is_connected = true;
                    memcpy(server_bda, scan_result->scan_rst.bda, sizeof(esp_bd_addr_t));
                    esp_ble_gattc_open(gattc_if_handle, scan_result->scan_rst.bda, scan_result->scan_rst.ble_addr_type, true);
                }
            }
        }
        break;
    }
    default:
        break;
    }
}

static void esp_gattc_cb(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if, esp_ble_gattc_cb_param_t *param) {
    switch (event) {
    case ESP_GATTC_REG_EVT:
        gattc_if_handle = gattc_if;
        esp_ble_gap_set_scan_params(&ble_scan_params);
        break;

    case ESP_GATTC_CONNECT_EVT:
        conn_id_handle = param->connect.conn_id;
        ESP_LOGI(TAG, "Connected to RaceBox. Requesting 256 MTU...");
        esp_ble_gattc_send_mtu_req(gattc_if, param->connect.conn_id);
        break;

    case ESP_GATTC_CFG_MTU_EVT:
        ESP_LOGI(TAG, "MTU negotiated to %d bytes. Discovering services...", param->cfg_mtu.mtu);
        esp_ble_gattc_search_service(gattc_if, conn_id_handle, NULL);
        break;

    case ESP_GATTC_SEARCH_RES_EVT: {
        if (param->search_res.srvc_id.uuid.len == ESP_UUID_LEN_128 &&
            memcmp(param->search_res.srvc_id.uuid.uuid.uuid128, nus_service_uuid128, 16) == 0) {
            ESP_LOGI(TAG, "Discovered Nordic UART Service.");
        }
        break;
    }

    case ESP_GATTC_SEARCH_CMPL_EVT: {
        esp_bt_uuid_t char_uuid = {
            .len = ESP_UUID_LEN_128,
        };
        memcpy(char_uuid.uuid.uuid128, nus_tx_char_uuid128, 16);

        esp_gattc_char_elem_t result;
        uint16_t count = 1;
        
        esp_gatt_status_t status = esp_ble_gattc_get_char_by_uuid(
            gattc_if, conn_id_handle, 0x0001, 0xffff,
            char_uuid, &result, &count);

        if (status == ESP_GATT_OK && count > 0) {
            esp_ble_gattc_register_for_notify(gattc_if, server_bda, result.char_handle);
            ESP_LOGI(TAG, "Subscribing to TX characteristic (handle: %d)", result.char_handle);
        } else {
            ESP_LOGE(TAG, "TX characteristic discovery failed: status = %d", status);
        }
        break;
    }

    case ESP_GATTC_REG_FOR_NOTIFY_EVT: {
        if (param->reg_for_notify.status != ESP_GATT_OK) {
            ESP_LOGE(TAG, "Registration for notifications failed: %d", param->reg_for_notify.status);
            break;
        }

        // Enable notifications via Client Characteristic Configuration Descriptor (CCCD)
        esp_bt_uuid_t notify_descr_uuid = {
            .len = ESP_UUID_LEN_16,
            .uuid = { .uuid16 = ESP_GATT_UUID_CHAR_CLIENT_CONFIG },
        };
        esp_gattc_descr_elem_t descr_result;
        uint16_t descr_count = 1;

        esp_gatt_status_t descr_status = esp_ble_gattc_get_descr_by_char_handle(
            gattc_if,
            conn_id_handle,
            param->reg_for_notify.handle,
            notify_descr_uuid,
            &descr_result,
            &descr_count);

        if (descr_status == ESP_GATT_OK && descr_count > 0) {
            uint16_t notify_en = 1;
            esp_ble_gattc_write_char_descr(
                gattc_if,
                conn_id_handle,
                descr_result.handle,
                sizeof(notify_en),
                (uint8_t *)&notify_en,
                ESP_GATT_WRITE_TYPE_RSP,
                ESP_GATT_AUTH_REQ_NONE);
            ESP_LOGI(TAG, "CCCD descriptor configured. RaceBox streaming active.");
        }
        break;
    }

    case ESP_GATTC_NOTIFY_EVT:
        process_stream(param->notify.value, param->notify.value_len);
        break;

    case ESP_GATTC_DISCONNECT_EVT:
        ESP_LOGW(TAG, "Disconnected from RaceBox. Resuming BLE scan...");
        is_connected = false;
        rx_buf_len = 0;
        esp_ble_gap_start_scanning(30);
        break;

    default:
        break;
    }
}

void racebox_init(void) {
    data_mutex = xSemaphoreCreateMutex();

    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT));
    esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_bt_controller_init(&bt_cfg));
    ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_BLE));
    ESP_ERROR_CHECK(esp_bluedroid_init());
    ESP_ERROR_CHECK(esp_bluedroid_enable());

    ESP_ERROR_CHECK(esp_ble_gap_register_callback(esp_gap_cb));
    ESP_ERROR_CHECK(esp_ble_gattc_register_callback(esp_gattc_cb));
    ESP_ERROR_CHECK(esp_ble_gattc_app_register(GATTC_APP_ID));
}

bool racebox_is_connected(void) {
    return is_connected;
}

bool racebox_get_data(racebox_data_t *out_data) {
    if (!out_data || !data_mutex) return false;
    if (xSemaphoreTake(data_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
        if (!latest_data.valid) {
            xSemaphoreGive(data_mutex);
            return false;
        }
        *out_data = latest_data;
        latest_data.valid = false; // Reset single-read flag
        xSemaphoreGive(data_mutex);
        return true;
    }
    return false;
}