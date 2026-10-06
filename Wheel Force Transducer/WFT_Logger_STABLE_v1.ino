/*
  BAJA WFT RAW CAN LOGGER
  -----------------------
  Hardware:
    ESP32 DevKit V1
    CAN transceiver / Adafruit CAN Pal
    Adafruit #4682 microSD breakout

  CAN:
    TX = GPIO 22
    RX = GPIO 21

  microSD SPI:
    CS   = GPIO 5
    SCK  = GPIO 18
    MISO = GPIO 19
    MOSI = GPIO 32

  DESIGN GOAL:
    Be boring.
    Receive CAN as fast as possible.
    Put frames into RAM immediately.
    Write raw binary records to SD in large batches.
    Do NOT parse WFT data while logging.
*/

#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include "driver/twai.h"

// ============================================================
// PIN CONFIGURATION
// ============================================================

constexpr gpio_num_t CAN_TX_PIN = GPIO_NUM_22;
constexpr gpio_num_t CAN_RX_PIN = GPIO_NUM_21;

constexpr int SD_CS   = 5;
constexpr int SD_SCK  = 18;
constexpr int SD_MISO = 19;
constexpr int SD_MOSI = 32;


// ============================================================
// CONFIGURATION
// ============================================================

// IMPORTANT:
// Must match the bitrate configured in the CT3.
#define CAN_1_MBPS

// ESP32 TWAI driver's own receive queue.
// This catches frames before our task moves them to the big buffer.
constexpr uint32_t TWAI_RX_QUEUE_SIZE = 256;

// Main application buffer.
//
// Each record is intentionally fixed-size.
// 4096 records gives substantial protection against an SD stall.
constexpr uint32_t RING_SIZE = 4096;

// Number of records copied out before doing an SD write.
//
// 256 records x 20 bytes = 5120-byte write.
constexpr uint32_t WRITE_BATCH = 256;

// Flush filesystem periodically.
// DO NOT flush every frame.
constexpr uint32_t FLUSH_INTERVAL_MS = 1000;

// Print status once per second.
constexpr uint32_t STATUS_INTERVAL_MS = 1000;


// ============================================================
// BINARY RECORD FORMAT
// ============================================================
//
// Exactly 20 bytes.
//
// Python can decode this easily later.
//
// timestamp_us : 4 bytes
// can_id       : 4 bytes
// dlc          : 1 byte
// flags        : 1 byte
// reserved     : 2 bytes
// data[8]      : 8 bytes
//

struct __attribute__((packed)) CanRecord {
  uint32_t timestamp_us;
  uint32_t can_id;

  uint8_t dlc;
  uint8_t flags;

  uint16_t reserved;

  uint8_t data[8];
};

static_assert(sizeof(CanRecord) == 20,
              "CanRecord must be exactly 20 bytes");


// ============================================================
// RAM RING BUFFER
// ============================================================

static CanRecord ringBuffer[RING_SIZE];

static volatile uint32_t ringHead = 0;
static volatile uint32_t ringTail = 0;
static volatile uint32_t ringCount = 0;

portMUX_TYPE ringMux = portMUX_INITIALIZER_UNLOCKED;


// ============================================================
// COUNTERS
// ============================================================

static volatile uint64_t framesReceived = 0;
static volatile uint64_t framesWritten  = 0;

// Frames lost because OUR 4096-frame buffer filled.
static volatile uint32_t ringDrops = 0;

static volatile uint32_t ringHighWater = 0;

static volatile bool fatalError = false;


// ============================================================
// SD
// ============================================================

File logFile;

uint32_t lastFlush = 0;
uint32_t lastStatus = 0;


// ============================================================
// ADD FRAME TO RING BUFFER
// ============================================================

bool pushRecord(const CanRecord &record)
{
  bool success = false;

  portENTER_CRITICAL(&ringMux);

  if (ringCount < RING_SIZE)
  {
    ringBuffer[ringHead] = record;

    ringHead++;

    if (ringHead >= RING_SIZE)
      ringHead = 0;

    ringCount++;

    if (ringCount > ringHighWater)
      ringHighWater = ringCount;

    success = true;
  }
  else
  {
    ringDrops++;
  }

  portEXIT_CRITICAL(&ringMux);

  return success;
}


// ============================================================
// CAN RECEIVER TASK
// ============================================================
//
// This task has ONE JOB:
//
//   CAN -> RAM
//
// It NEVER:
//   writes SD
//   prints CAN frames
//   parses WFT data
//   does floating-point math
//

void canReceiverTask(void *parameter)
{
  twai_message_t message;

  while (true)
  {
    // Block here until a CAN frame arrives.
    if (twai_receive(&message, portMAX_DELAY) == ESP_OK)
    {
      CanRecord record = {};

      record.timestamp_us = (uint32_t)micros();
      record.can_id = message.identifier;

      // CAN 2.0 payload is maximum 8 bytes.
      uint8_t dlc = message.data_length_code;

      if (dlc > 8)
        dlc = 8;

      record.dlc = dlc;

      // Store useful frame information.
      record.flags = 0;

      if (message.extd)
        record.flags |= 0x01;

      if (message.rtr)
        record.flags |= 0x02;

      // Copy CAN payload.
      if (!message.rtr)
      {
        memcpy(record.data,
               message.data,
               dlc);
      }

      pushRecord(record);

      framesReceived++;
    }
  }
}


// ============================================================
// COPY RECORDS OUT OF RING BUFFER
// ============================================================
//
// We do NOT hold the critical section while writing the SD card.
//
// Instead:
//
// ring buffer -> temporary RAM buffer
//
// Then release the ring buffer immediately.
//
// temporary RAM -> SD
//

uint32_t getWriteBatch(CanRecord *destination,
                       uint32_t maxRecords)
{
  uint32_t copied = 0;

  portENTER_CRITICAL(&ringMux);

  copied = ringCount;

  if (copied > maxRecords)
    copied = maxRecords;

  for (uint32_t i = 0; i < copied; i++)
  {
    destination[i] = ringBuffer[ringTail];

    ringTail++;

    if (ringTail >= RING_SIZE)
      ringTail = 0;
  }

  ringCount -= copied;

  portEXIT_CRITICAL(&ringMux);

  return copied;
}


// ============================================================
// CREATE UNIQUE LOG FILE
// ============================================================

bool createLogFile()
{
  char filename[24];

  for (uint32_t i = 0; i < 10000; i++)
  {
    snprintf(filename,
             sizeof(filename),
             "/WFT%04lu.BIN",
             (unsigned long)i);

    if (!SD.exists(filename))
    {
      logFile = SD.open(filename, FILE_WRITE);

      if (!logFile)
        return false;

      Serial.print("Logging to: ");
      Serial.println(filename);

      return true;
    }
  }

  return false;
}


// ============================================================
// INITIALIZE SD
// ============================================================

bool initializeSD()
{
  Serial.println("Initializing SD...");

  SPI.begin(
    SD_SCK,
    SD_MISO,
    SD_MOSI,
    SD_CS
  );

  // Conservative SPI speed.
  //
  // We don't need extreme SD bandwidth.
  // Reliability > benchmark numbers.
  if (!SD.begin(SD_CS, SPI, 10000000))
  {
    Serial.println("ERROR: SD initialization failed.");
    return false;
  }

  Serial.println("SD initialized.");

  uint64_t cardSize =
      SD.cardSize() / (1024ULL * 1024ULL);

  Serial.print("SD size: ");
  Serial.print(cardSize);
  Serial.println(" MB");

  if (!createLogFile())
  {
    Serial.println("ERROR: Could not create log file.");
    return false;
  }

  return true;
}


// ============================================================
// INITIALIZE CAN
// ============================================================

bool initializeCAN()
{
  Serial.println("Initializing CAN...");

  twai_general_config_t g_config =
      TWAI_GENERAL_CONFIG_DEFAULT(
        CAN_TX_PIN,
        CAN_RX_PIN,
        TWAI_MODE_NORMAL
      );

  // We are only receiving.
  // No application TX queue needed.
  g_config.tx_queue_len = 0;

  // Increase driver's internal RX queue.
  g_config.rx_queue_len = TWAI_RX_QUEUE_SIZE;

  // Alerts we actually care about.
  g_config.alerts_enabled =
      TWAI_ALERT_RX_QUEUE_FULL |
      TWAI_ALERT_BUS_ERROR |
      TWAI_ALERT_BUS_OFF |
      TWAI_ALERT_ERR_PASS;

#ifdef CAN_1_MBPS

  twai_timing_config_t t_config =
      TWAI_TIMING_CONFIG_1MBITS();

#else

  twai_timing_config_t t_config =
      TWAI_TIMING_CONFIG_500KBITS();

#endif

  // Accept every CAN ID.
  twai_filter_config_t f_config =
      TWAI_FILTER_CONFIG_ACCEPT_ALL();

  esp_err_t result =
      twai_driver_install(
        &g_config,
        &t_config,
        &f_config
      );

  if (result != ESP_OK)
  {
    Serial.print("ERROR: CAN driver install failed: ");
    Serial.println(result);

    return false;
  }

  result = twai_start();

  if (result != ESP_OK)
  {
    Serial.print("ERROR: CAN start failed: ");
    Serial.println(result);

    twai_driver_uninstall();

    return false;
  }

  Serial.println("CAN started.");

#ifdef CAN_1_MBPS
  Serial.println("CAN bitrate: 1 Mbps");
#else
  Serial.println("CAN bitrate: 500 kbps");
#endif

  return true;
}


// ============================================================
// PRINT STATUS
// ============================================================

void printStatus()
{
  twai_status_info_t status;

  if (twai_get_status_info(&status) != ESP_OK)
  {
    Serial.println("WARNING: Could not read CAN status.");
    return;
  }

  uint32_t currentBuffer;

  portENTER_CRITICAL(&ringMux);
  currentBuffer = ringCount;
  portEXIT_CRITICAL(&ringMux);

  Serial.println();
  Serial.println("---------- LOGGER ----------");

  Serial.print("RX frames:       ");
  Serial.println((unsigned long)framesReceived);

  Serial.print("Written:         ");
  Serial.println((unsigned long)framesWritten);

  Serial.print("RAM buffer:      ");
  Serial.print(currentBuffer);
  Serial.print("/");
  Serial.println(RING_SIZE);

  Serial.print("Buffer max:      ");
  Serial.println(ringHighWater);

  Serial.print("Ring drops:      ");
  Serial.println(ringDrops);

  Serial.print("TWAI missed:     ");
  Serial.println(status.rx_missed_count);

  Serial.print("TWAI overruns:   ");
  Serial.println(status.rx_overrun_count);

  Serial.print("CAN RX errors:   ");
  Serial.println(status.rx_error_counter);

  Serial.print("CAN TX errors:   ");
  Serial.println(status.tx_error_counter);

  Serial.println("----------------------------");
}


// ============================================================
// CHECK CAN ALERTS
// ============================================================

void checkCANAlerts()
{
  uint32_t alerts = 0;

  if (twai_read_alerts(&alerts, 0) != ESP_OK)
    return;

  if (alerts & TWAI_ALERT_RX_QUEUE_FULL)
  {
    Serial.println(
      "WARNING: TWAI RX QUEUE FULL - FRAME LOST"
    );
  }

  if (alerts & TWAI_ALERT_BUS_ERROR)
  {
    Serial.println(
      "WARNING: CAN BUS ERROR"
    );
  }

  if (alerts & TWAI_ALERT_ERR_PASS)
  {
    Serial.println(
      "WARNING: CAN ERROR PASSIVE"
    );
  }

  if (alerts & TWAI_ALERT_BUS_OFF)
  {
    Serial.println(
      "ERROR: CAN BUS OFF"
    );
  }
}


// ============================================================
// SETUP
// ============================================================

void setup()
{
  Serial.begin(115200);

  delay(1500);

  Serial.println();
  Serial.println("============================");
  Serial.println(" BAJA WFT RAW CAN LOGGER");
  Serial.println("============================");

  // ----------------------------------------
  // SD FIRST
  // ----------------------------------------

  if (!initializeSD())
  {
    Serial.println();
    Serial.println("FATAL: SD FAILED.");
    Serial.println("Logging will NOT start.");

    fatalError = true;

    return;
  }

  // ----------------------------------------
  // CAN SECOND
  // ----------------------------------------

  if (!initializeCAN())
  {
    Serial.println();
    Serial.println("FATAL: CAN FAILED.");
    Serial.println("Logging will NOT start.");

    logFile.close();

    fatalError = true;

    return;
  }

  // ----------------------------------------
  // START CAN RECEIVER TASK
  // ----------------------------------------

  BaseType_t result =
      xTaskCreatePinnedToCore(
        canReceiverTask,
        "CAN_RX",
        4096,
        nullptr,
        20,
        nullptr,
        1
      );

  if (result != pdPASS)
  {
    Serial.println(
      "FATAL: Could not create CAN receiver task."
    );

    fatalError = true;

    return;
  }

  lastFlush = millis();
  lastStatus = millis();

  Serial.println();
  Serial.println("LOGGER RUNNING.");
  Serial.println("Do not remove SD card while powered.");
}


// ============================================================
// LOOP
// ============================================================

void loop()
{
  if (fatalError)
  {
    delay(1000);
    return;
  }

  // Temporary write buffer.
  //
  // Static = allocated once.
  // No heap allocation during logging.
  static CanRecord writeBuffer[WRITE_BATCH];

  // ----------------------------------------
  // RAM -> TEMP BUFFER
  // ----------------------------------------

  uint32_t count =
      getWriteBatch(
        writeBuffer,
        WRITE_BATCH
      );

  // ----------------------------------------
  // TEMP BUFFER -> SD
  // ----------------------------------------

  if (count > 0)
  {
    size_t bytesToWrite =
        count * sizeof(CanRecord);

    size_t bytesWritten =
        logFile.write(
          (uint8_t *)writeBuffer,
          bytesToWrite
        );

    if (bytesWritten != bytesToWrite)
    {
      Serial.println();
      Serial.println(
        "FATAL: SD WRITE FAILED!"
      );

      Serial.print("Wanted: ");
      Serial.println(bytesToWrite);

      Serial.print("Wrote:  ");
      Serial.println(bytesWritten);

      fatalError = true;

      return;
    }

    framesWritten += count;
  }

  // ----------------------------------------
  // PERIODIC FLUSH
  // ----------------------------------------

  uint32_t now = millis();

  if ((uint32_t)(now - lastFlush)
      >= FLUSH_INTERVAL_MS)
  {
    logFile.flush();

    lastFlush = now;
  }

  // ----------------------------------------
  // CAN ERROR CHECK
  // ----------------------------------------

  checkCANAlerts();

  // ----------------------------------------
  // STATUS
  // ----------------------------------------

  if ((uint32_t)(now - lastStatus)
      >= STATUS_INTERVAL_MS)
  {
    printStatus();

    lastStatus = now;
  }

  // Let FreeRTOS schedule other work.
  delay(1);
}
