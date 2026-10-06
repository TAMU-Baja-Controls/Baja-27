#include <Arduino.h>
#include "driver/twai.h"

// ============================================================
// FAKE CT3 / WFT CAN TRANSMITTER
// ESP32 DevKit V1 + CAN transceiver
//
// Simulates the real CT3 configuration:
//
//   CAN 2.0B
//   1 Mbps
//   500 samples/sec
//
// Real CT3 DBC messages:
//
//   0x21 = Fx, Fy, Fz, Mx
//   0x22 = My, Mz, Velocity, Position
//   0x23 = Accel X, Accel Y, Accel Z
//
// Each signal is encoded exactly according to CT3.dbc.
// ============================================================


// ============================================================
// PIN CONFIGURATION
// ============================================================

constexpr gpio_num_t CAN_TX_PIN = GPIO_NUM_22;
constexpr gpio_num_t CAN_RX_PIN = GPIO_NUM_21;


// ============================================================
// REAL CT3 CAN IDs
// ============================================================

constexpr uint32_t FRAME_A_ID = 0x21;
constexpr uint32_t FRAME_B_ID = 0x22;
constexpr uint32_t FRAME_C_ID = 0x23;


// ============================================================
// SAMPLE RATE
// ============================================================

// Real CT3 setting = 500 samples/sec.
//
// Each sample contains 3 CAN frames.
//
// 500 samples/sec * 3 frames/sample
// = 1500 CAN frames/sec.

constexpr uint32_t SAMPLE_RATE_HZ = 500;

constexpr uint32_t SAMPLE_PERIOD_US =
    1000000UL / SAMPLE_RATE_HZ;


// ============================================================
// DBC SCALE FACTORS
// ============================================================
//
// From CT3.dbc:
//
// Forces:
//   physical = raw * 0.30517578125 N
//
// Moments:
//   physical = raw * 0.30517578125 Nm
//
// Velocity:
//   physical = raw * 0.06103515625 RPM
//
// Position:
//   physical = raw * 0.010986328125 degrees
//
// Acceleration:
//   physical = raw * 0.0030517578125 g
//

constexpr float FORCE_SCALE =
    0.30517578125f;

constexpr float MOMENT_SCALE =
    0.30517578125f;

constexpr float VELOCITY_SCALE =
    0.06103515625f;

constexpr float POSITION_SCALE =
    0.010986328125f;

constexpr float ACCEL_SCALE =
    0.0030517578125f;


// ============================================================
// COUNTERS
// ============================================================

uint32_t sampleNumber = 0;

uint64_t framesSent = 0;
uint64_t transmitFailures = 0;

uint32_t lastStatusTime = 0;


// ============================================================
// CONVERT PHYSICAL VALUE -> SIGNED DBC RAW VALUE
// ============================================================

int16_t physicalToRawSigned(
    float physical,
    float scale)
{
  float rawFloat = physical / scale;

  if (rawFloat > 32767.0f)
    rawFloat = 32767.0f;

  if (rawFloat < -32768.0f)
    rawFloat = -32768.0f;

  return (int16_t)roundf(rawFloat);
}


// ============================================================
// CONVERT POSITION -> UNSIGNED DBC RAW VALUE
// ============================================================

uint16_t positionToRaw(float degrees)
{
  // Keep position between 0 and 360 degrees.

  while (degrees >= 360.0f)
    degrees -= 360.0f;

  while (degrees < 0.0f)
    degrees += 360.0f;

  float rawFloat =
      degrees / POSITION_SCALE;

  if (rawFloat > 65535.0f)
    rawFloat = 65535.0f;

  return (uint16_t)roundf(rawFloat);
}


// ============================================================
// PUT SIGNED 16-BIT VALUE INTO CAN PAYLOAD
// LITTLE ENDIAN
// ============================================================
//
// CT3.dbc uses:
//
//   @1
//
// which means Intel / little-endian.
//

void putInt16LE(
    uint8_t *data,
    uint8_t offset,
    int16_t value)
{
  uint16_t raw =
      (uint16_t)value;

  data[offset] =
      raw & 0xFF;

  data[offset + 1] =
      (raw >> 8) & 0xFF;
}


// ============================================================
// PUT UNSIGNED 16-BIT VALUE INTO CAN PAYLOAD
// ============================================================

void putUInt16LE(
    uint8_t *data,
    uint8_t offset,
    uint16_t value)
{
  data[offset] =
      value & 0xFF;

  data[offset + 1] =
      (value >> 8) & 0xFF;
}


// ============================================================
// SEND ONE CAN FRAME
// ============================================================

bool sendFrame(
    uint32_t id,
    const uint8_t *data)
{
  twai_message_t message = {};

  message.identifier = id;

  // Standard 11-bit CAN ID.
  message.extd = 0;

  // Normal data frame.
  message.rtr = 0;

  // CT3 frames are 8 bytes.
  message.data_length_code = 8;

  memcpy(
    message.data,
    data,
    8
  );


  // Wait up to 10 ms for transmission.

  esp_err_t result =
      twai_transmit(
        &message,
        pdMS_TO_TICKS(10)
      );


  if (result == ESP_OK)
  {
    framesSent++;
    return true;
  }


  transmitFailures++;

  return false;
}


// ============================================================
// GENERATE ONE FAKE CT3 SAMPLE
// ============================================================

void sendFakeWFTSample()
{
  uint8_t frameA[8] = {};
  uint8_t frameB[8] = {};
  uint8_t frameC[8] = {};


  // Time since simulator started in seconds.

  float t =
      (float)sampleNumber /
      (float)SAMPLE_RATE_HZ;


  // ==========================================================
  // GENERATE FAKE SENSOR VALUES
  // ==========================================================
  //
  // These aren't supposed to perfectly model Baja physics.
  //
  // They're smooth, predictable signals so we can verify:
  //
  // Fake CT3
  //     ->
  // CAN
  //     ->
  // WFT logger
  //     ->
  // .BIN
  //     ->
  // Python decoder
  //
  // without just sending random bytes.


  // ----------------------------------------------------------
  // FORCES [N]
  // ----------------------------------------------------------

  float fx =
      1000.0f *
      sinf(
        2.0f * PI *
        0.5f * t
      );


  float fy =
      500.0f *
      cosf(
        2.0f * PI *
        0.5f * t
      );


  // Simulate vertical load around 2000 N.

  float fz =
      2000.0f +
      250.0f *
      sinf(
        2.0f * PI *
        1.0f * t
      );


  // ----------------------------------------------------------
  // MOMENTS [Nm]
  // ----------------------------------------------------------

  float mx =
      100.0f *
      sinf(
        2.0f * PI *
        0.25f * t
      );


  float my =
      150.0f *
      cosf(
        2.0f * PI *
        0.25f * t
      );


  float mz =
      75.0f *
      sinf(
        2.0f * PI *
        0.75f * t
      );


  // ----------------------------------------------------------
  // WHEEL VELOCITY [RPM]
  // ----------------------------------------------------------

  float velocity =
      300.0f +
      50.0f *
      sinf(
        2.0f * PI *
        0.2f * t
      );


  // ----------------------------------------------------------
  // WHEEL POSITION [degrees]
  // ----------------------------------------------------------
  //
  // Fake wheel makes one revolution per second.

  float position =
      fmodf(
        t * 360.0f,
        360.0f
      );


  // ----------------------------------------------------------
  // ACCELERATION [g]
  // ----------------------------------------------------------

  float accelX =
      0.5f *
      sinf(
        2.0f * PI *
        2.0f * t
      );


  float accelY =
      0.25f *
      cosf(
        2.0f * PI *
        2.0f * t
      );


  // Roughly 1 g vertical with a little oscillation.

  float accelZ =
      1.0f +
      0.1f *
      sinf(
        2.0f * PI *
        1.0f * t
      );


  // ==========================================================
  // FRAME 0x21
  // ==========================================================
  //
  // Bytes 0-1 = Fx
  // Bytes 2-3 = Fy
  // Bytes 4-5 = Fz
  // Bytes 6-7 = Mx
  //

  putInt16LE(
    frameA,
    0,
    physicalToRawSigned(
      fx,
      FORCE_SCALE
    )
  );


  putInt16LE(
    frameA,
    2,
    physicalToRawSigned(
      fy,
      FORCE_SCALE
    )
  );


  putInt16LE(
    frameA,
    4,
    physicalToRawSigned(
      fz,
      FORCE_SCALE
    )
  );


  putInt16LE(
    frameA,
    6,
    physicalToRawSigned(
      mx,
      MOMENT_SCALE
    )
  );


  // ==========================================================
  // FRAME 0x22
  // ==========================================================
  //
  // Bytes 0-1 = My
  // Bytes 2-3 = Mz
  // Bytes 4-5 = Velocity
  // Bytes 6-7 = Position
  //

  putInt16LE(
    frameB,
    0,
    physicalToRawSigned(
      my,
      MOMENT_SCALE
    )
  );


  putInt16LE(
    frameB,
    2,
    physicalToRawSigned(
      mz,
      MOMENT_SCALE
    )
  );


  putInt16LE(
    frameB,
    4,
    physicalToRawSigned(
      velocity,
      VELOCITY_SCALE
    )
  );


  putUInt16LE(
    frameB,
    6,
    positionToRaw(
      position
    )
  );


  // ==========================================================
  // FRAME 0x23
  // ==========================================================
  //
  // Bytes 0-1 = Accel X
  // Bytes 2-3 = Accel Y
  // Bytes 4-5 = Accel Z
  //
  // Bytes 6-7 are unused by the downloaded DBC.
  // They remain zero.
  //

  putInt16LE(
    frameC,
    0,
    physicalToRawSigned(
      accelX,
      ACCEL_SCALE
    )
  );


  putInt16LE(
    frameC,
    2,
    physicalToRawSigned(
      accelY,
      ACCEL_SCALE
    )
  );


  putInt16LE(
    frameC,
    4,
    physicalToRawSigned(
      accelZ,
      ACCEL_SCALE
    )
  );


  // ==========================================================
  // TRANSMIT ALL THREE CT3 FRAMES
  // ==========================================================

  sendFrame(
    FRAME_A_ID,
    frameA
  );

  sendFrame(
    FRAME_B_ID,
    frameB
  );

  sendFrame(
    FRAME_C_ID,
    frameC
  );


  sampleNumber++;
}


// ============================================================
// SETUP
// ============================================================

void setup()
{
  Serial.begin(115200);

  delay(1500);


  Serial.println();

  Serial.println(
    "=============================="
  );

  Serial.println(
    " BAJA FAKE CT3"
  );

  Serial.println(
    "=============================="
  );


  Serial.println();

  Serial.println(
    "CAN:         1 Mbps"
  );

  Serial.println(
    "Sample rate: 500 Hz"
  );

  Serial.println(
    "Frames:      3/sample"
  );

  Serial.println(
    "Expected:    1500 frames/sec"
  );

  Serial.println(
    "IDs:         0x21 0x22 0x23"
  );

  Serial.println();


  // ==========================================================
  // TWAI CONFIGURATION
  // ==========================================================

  twai_general_config_t g_config =
      TWAI_GENERAL_CONFIG_DEFAULT(
        CAN_TX_PIN,
        CAN_RX_PIN,
        TWAI_MODE_NORMAL
      );


  // Give transmitter a reasonable queue.

  g_config.tx_queue_len = 32;


  // Simulator doesn't really need received frames.

  g_config.rx_queue_len = 16;


  // ==========================================================
  // 1 Mbps
  // ==========================================================

  twai_timing_config_t t_config =
      TWAI_TIMING_CONFIG_1MBITS();


  twai_filter_config_t f_config =
      TWAI_FILTER_CONFIG_ACCEPT_ALL();


  // ==========================================================
  // INSTALL DRIVER
  // ==========================================================

  esp_err_t result =
      twai_driver_install(
        &g_config,
        &t_config,
        &f_config
      );


  if (result != ESP_OK)
  {
    Serial.print(
      "TWAI install FAILED: "
    );

    Serial.println(result);


    while (true)
      delay(1000);
  }


  // ==========================================================
  // START DRIVER
  // ==========================================================

  result = twai_start();


  if (result != ESP_OK)
  {
    Serial.print(
      "TWAI start FAILED: "
    );

    Serial.println(result);


    while (true)
      delay(1000);
  }


  Serial.println(
    "CAN started."
  );

  Serial.println(
    "Beginning fake CT3 transmission..."
  );
}


// ============================================================
// LOOP
// ============================================================

void loop()
{
  /*
      500 Hz:

      1,000,000 us / 500
      =
      2000 us/sample

      Each sample sends:

          0x21
          0x22
          0x23

      Therefore:

          500 * 3
          =
          1500 CAN frames/sec
  */


  static uint32_t nextSampleTime =
      micros();


  uint32_t now =
      micros();


  // Signed subtraction handles micros() rollover.

  if ((int32_t)(
        now -
        nextSampleTime
      ) >= 0)
  {
    sendFakeWFTSample();


    nextSampleTime +=
        SAMPLE_PERIOD_US;
  }


  // ==========================================================
  // STATUS ONCE PER SECOND
  // ==========================================================

  uint32_t nowMs =
      millis();


  if ((uint32_t)(
        nowMs -
        lastStatusTime
      ) >= 1000)
  {
    Serial.println();

    Serial.println(
      "------ FAKE CT3 ------"
    );


    Serial.print(
      "Samples generated: "
    );

    Serial.println(
      sampleNumber
    );


    Serial.print(
      "Frames sent:       "
    );

    Serial.println(
      (unsigned long)framesSent
    );


    Serial.print(
      "TX failures:       "
    );

    Serial.println(
      (unsigned long)transmitFailures
    );


    Serial.println(
      "Expected rate:      1500 frames/sec"
    );


    Serial.println(
      "----------------------"
    );


    lastStatusTime =
        nowMs;
  }
}