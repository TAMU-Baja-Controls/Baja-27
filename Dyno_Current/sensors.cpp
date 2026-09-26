/*
  sensors .cpp file 

  Contains sensor function logic and private variables
*/

#include <Arduino.h>

#include "sensors.h"
#include "HX711.h"

// ========================
// PRIVATE FUNCTIONS/CONFIG
// ========================
namespace { 
  void updatePrimaryRPM();
  void updateSecondaryRPM1();
  void updateSecondaryRPM2();
  void updateLoadCell();

  void IRAM_ATTR onInductivePulse();
  void IRAM_ATTR onHall1Pulse();
  void IRAM_ATTR onHall2Pulse();

  // Primary RPM config
    const int INDUCTIVE_PIN = 2;

    const bool ENGINE_TYPE = false;

    const unsigned long INDUCTIVE_TIMEOUT_MS = 1000;
    const unsigned long MINIMUM_PRIMARY_INTERVAL_US = 10000;

    volatile unsigned long lastInductiveMicros = 0;
    volatile unsigned long inductiveIntervalMicros = 0;
    volatile bool newInductivePulse = false;

    unsigned long lastInductiveMillis = 0;

    float primaryRPM = 0.0f;

  // Secondary RPM config (both hall-effects)
    const int HALL_PIN_1 = 0;
    const int HALL_PIN_2 = 1;

    const float PULSES_PER_REV = 3.0f;
    const unsigned long HALL_TIMEOUT_MS = 1000;

    const float MAX_SECONDARY_RPM = 5000.0f;
    const unsigned long MINIMUM_SECONDARY_INTERVAL_US = 
      (unsigned long)(60000000.0f / (MAX_SECONDARY_RPM * PULSES_PER_REV));

    // Hall-Effect 1
    volatile unsigned long lastHall1Micros = 0;
    volatile unsigned long hall1IntervalMicros = 0;
    volatile bool newHall1Pulse = false;
    unsigned long lastHall1Millis = 0;
    float secondaryRPM1 = 0.0f;

    // Hall-Effect 2
    volatile unsigned long lastHall2Micros = 0;
    volatile unsigned long hall2IntervalMicros = 0;
    volatile bool newHall2Pulse = false;
    unsigned long lastHall2Millis = 0;
    float secondaryRPM2 = 0.0f;

  // Load cell config
    const int HX711_DT_PIN = 8;
    const int HX711_SCK_PIN = 9;

    const float HX711_CALIBRATION_FACTOR = -695.0f;
    const float LOAD_CELL_FILTER_ALPHA = 0.20f;

    const unsigned long LOAD_CELL_TIMEOUT_MS = 1000;

    HX711 loadCell;

    float loadCellReading = 0.0f;

    bool loadCellReady = false;
    bool loadCellFilterInitialized = false;

    unsigned long lastLoadCellUpdateMs = 0;

  void updateLoadCell() { // Private function
    if (loadCell.is_ready()) {
      float newReading = loadCell.get_units(1);

      if (!loadCellFilterInitialized) {
        loadCellReading = newReading;
        loadCellFilterInitialized = true;
      }
      else {
        loadCellReading = LOAD_CELL_FILTER_ALPHA * newReading +
                          (1.0f - LOAD_CELL_FILTER_ALPHA) * loadCellReading;
      }

      loadCellReady = true;
      lastLoadCellUpdateMs = millis();
    }

    if (loadCellReady && millis() - lastLoadCellUpdateMs > LOAD_CELL_TIMEOUT_MS) {
      loadCellReady = false;
    }
  }

  void IRAM_ATTR onInductivePulse() {
    /* Timestamp explanation
      1. Capture the current timestamp
      2. Compare to previous timestamp
      3. Store the resultant interval
      4. Mark that a new pulse occured
      5. Update the oldest timestamp
    */
    unsigned long now = micros();

    if (lastInductiveMicros > 0) {
      unsigned long interval = now - lastInductiveMicros;

      if (interval >= MINIMUM_PRIMARY_INTERVAL_US) {
        inductiveIntervalMicros = interval;
        newInductivePulse = true;
        lastInductiveMicros = now;
      }
    }
    else {
      lastInductiveMicros = now;
    }
  }

  void IRAM_ATTR onHall1Pulse() { // ISR 1
    unsigned long now = micros();

    if (lastHall1Micros > 0) {
      unsigned long interval = now - lastHall1Micros;

      if (interval >= MINIMUM_SECONDARY_INTERVAL_US) {
        hall1IntervalMicros = interval;
        newHall1Pulse = true;
        lastHall1Micros = now;
      }
    }
    else {
      lastHall1Micros = now;
    }
  }

  void IRAM_ATTR onHall2Pulse() { // ISR 2
    unsigned long now = micros();

    if (lastHall2Micros > 0) {
      unsigned long interval = now - lastHall2Micros;

      if (interval >= MINIMUM_SECONDARY_INTERVAL_US) {
        hall2IntervalMicros = interval;
        newHall2Pulse = true;
        lastHall2Micros = now;
      }
    }
    else {
      lastHall2Micros = now;
    }
  }

  void updatePrimaryRPM() { // Check this later if inductive sensor is acting up
    unsigned long interval;
    bool hasNewPulse;

    noInterrupts();

    interval = inductiveIntervalMicros;
    hasNewPulse = newInductivePulse;
    newInductivePulse = false;

    interrupts();

  if (hasNewPulse && interval > 0) {
      float pulsesPerMinute = 60000000.0f / (float)interval;
      primaryRPM = ENGINE_TYPE ? (pulsesPerMinute * 2.0f) : pulsesPerMinute;

      lastInductiveMillis = millis();
    }
    if (millis() - lastInductiveMillis > INDUCTIVE_TIMEOUT_MS) {
      primaryRPM = 0.0f; // set RPM to 0 if timeout value has been passed
    }
  }
  
  void updateSecondaryRPM1() {
    unsigned long interval;
    bool hasNewPulse;

    noInterrupts();

    interval = hall1IntervalMicros;
    hasNewPulse = newHall1Pulse;
    newHall1Pulse = false;

    interrupts();

    if (hasNewPulse && interval > 0) {
      secondaryRPM1 =
        60000000.0f / ((float)interval * PULSES_PER_REV);

      lastHall1Millis = millis();
    }

    if (millis() - lastHall1Millis > HALL_TIMEOUT_MS) {
      secondaryRPM1 = 0.0f;
    }
  }


  void updateSecondaryRPM2() {
    unsigned long interval;
    bool hasNewPulse;

    noInterrupts();

    interval = hall2IntervalMicros;
    hasNewPulse = newHall2Pulse;
    newHall2Pulse = false;

    interrupts();

    if (hasNewPulse && interval > 0) {
      secondaryRPM2 =
        60000000.0f / ((float)interval * PULSES_PER_REV);

      lastHall2Millis = millis();
    }

    if (millis() - lastHall2Millis > HALL_TIMEOUT_MS) {
      secondaryRPM2 = 0.0f;
    }
  }
}

// ================
// PUBLIC FUNCTIONS
// ================
bool initializeSensors() {
  pinMode(INDUCTIVE_PIN, INPUT_PULLUP);  // Change INPUT_PULLUP to INPUT for on-engine testing
  attachInterrupt(digitalPinToInterrupt(INDUCTIVE_PIN), onInductivePulse, FALLING);

  pinMode(HALL_PIN_1, INPUT);
  attachInterrupt(digitalPinToInterrupt(HALL_PIN_1), onHall1Pulse, FALLING);

  pinMode(HALL_PIN_2, INPUT);
  attachInterrupt(digitalPinToInterrupt(HALL_PIN_2), onHall2Pulse, FALLING);

  loadCell.begin(HX711_DT_PIN, HX711_SCK_PIN);
  loadCell.set_scale(HX711_CALIBRATION_FACTOR);

  unsigned long loadCellStartTime = millis();

  while (!loadCell.is_ready() && millis() - loadCellStartTime < 2000) {
    delay(10);
  }

  if (!loadCell.is_ready()) {
    loadCellReady = false;
    return false;
  }

  loadCell.tare();

  loadCellReading = 0.0f;
  loadCellReady = true;
  loadCellFilterInitialized = false;
  lastLoadCellUpdateMs = millis();

  return true;
}
void updateSensors() {
  updatePrimaryRPM();
  updateSecondaryRPM1();
  updateSecondaryRPM2();
  updateLoadCell();
}
bool tareLoadCell() { // Public because called by main.ino file during user input
                      // This is a definition because it contains braces and actual code
  Serial.println("Taring load cell. Remove all load.");

  if (!loadCell.wait_ready_timeout(2000)) {
    loadCellReady = false;
    Serial.println("Load cell tare failed: HX711 not ready.");
    return false;
  }

  loadCell.tare();

  loadCellReading = 0.0f;
  loadCellReady = true;
  loadCellFilterInitialized = false;
  lastLoadCellUpdateMs = millis();

  Serial.println("Load cell tare complete.");

  return true;
}

// =======================
// PUBLIC GETTER FUNCTIONS
// =======================
bool isLoadCellReady() { // Getter functions expose read-only access to typically private values
  return loadCellReady;
}
float getLoadCellReading() {
  return loadCellReading;
}
float getPrimaryRPM() {
  return primaryRPM;
}
float getSecondaryRPM1() {
  return secondaryRPM1;
}
float getSecondaryRPM2() {
  return secondaryRPM2;
}




