#include "udp_telemetry.h"
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include <fcntl.h>

static const char *TAG = "UDP_TELEMETRY";

#define WIFI_SSID       "DAQ_TELEMETRY"
#define WIFI_PASS       "baja2026"
#define UDP_PORT        5005
#define BROADCAST_IP    "192.168.4.255"

static int sock_fd = -1;
static struct sockaddr_in dest_addr;

void telemetry_udp_init(void) {
    ESP_ERROR_CHECK(esp_netif_init());

    esp_err_t err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }

    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid = WIFI_SSID,
            .ssid_len = strlen(WIFI_SSID),
            .channel = 1,
            .password = WIFI_PASS,
            .max_connection = 4,
            .authmode = WIFI_AUTH_WPA2_PSK,
            .pmf_cfg = { .required = false },
        },
    };

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    // Create UDP Broadcast socket
    sock_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock_fd < 0) {
        ESP_LOGE(TAG, "Failed to create socket: errno %d", errno);
        return;
    }

    int broadcast_en = 1;
    setsockopt(sock_fd, SOL_SOCKET, SO_BROADCAST, &broadcast_en, sizeof(broadcast_en));
    int flags = fcntl(sock_fd, F_GETFL, 0);
    fcntl(sock_fd, F_SETFL, flags | O_NONBLOCK);
    memset(&dest_addr, 0, sizeof(dest_addr));
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(UDP_PORT);
    dest_addr.sin_addr.s_addr = inet_addr(BROADCAST_IP);

    ESP_LOGI(TAG, "SoftAP ready. Broadcasting UDP on %s:%d", BROADCAST_IP, UDP_PORT);
}

void telemetry_udp_send_frame(const daq_frame_t *frame) {
    if (sock_fd < 0 || frame == NULL) return;

    sendto(sock_fd, frame, sizeof(daq_frame_t), 0,
           (struct sockaddr *)&dest_addr, sizeof(dest_addr));
}