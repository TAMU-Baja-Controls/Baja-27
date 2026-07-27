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
namespace { // Anonymous namespace that can only be used within sensors.cpp
  void updatePrimaryRPM();
  void updateSecondaryRPM();
  void updateLoadCell();

  void IRAM_ATTR onInductivePulse();
  void IRAM_ATTR onHallPulse();

  // Primary RPM config
    const int INDUCTIVE_PIN = 4;

    const bool FOUR_STROKE = false;

    const unsigned long INDUCTIVE_TIMEOUT_MS = 1000;
    const unsigned long MINIMUM_PRIMARY_INTERVAL_US = 10000;

    volatile unsigned long lastInductiveMicros = 0;
    volatile unsigned long inductiveIntervalMicros = 0;
    volatile bool newInductivePulse = false;

    unsigned long lastInductiveMillis = 0;

    float primaryRPM = 0.0f;

  // Secondary RPM config
    const int HALL_PIN = 3;

    const float PULSES_PER_REV = 3.0f;
    const unsigned long HALL_TIMEOUT_MS = 1000;

    const float MAX_SECONDARY_RPM = 5000.0f;
    const unsigned long MINIMUM_SECONDARY_INTERVAL_US = 
      (unsigned long)(60000000.0f / (MAX_SECONDARY_RPM * PULSES_PER_REV));

    volatile unsigned long lastHallMicros = 0;
    volatile unsigned long hallIntervalMicros = 0;
    volatile bool newHallPulse = false;

    unsigned long lastHallMillis = 0;

    float secondaryRPM = 0.0f;

  // Load cell config
    const int HX711_DT_PIN = 5;
    const int HX711_SCK_PIN = 6;

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

  void IRAM_ATTR onHallPulse() {
    unsigned long now = micros();
    
    if (lastHallMicros > 0) {
      unsigned long interval = now - lastHallMicros;

      if (interval >= MINIMUM_SECONDARY_INTERVAL_US) {
        hallIntervalMicros = interval;
        newHallPulse = true;
        lastHallMicros = now;
      }
    }
    else {
      lastHallMicros = now;
    }
  }

  void updatePrimaryRPM() {
    unsigned long interval;
    bool hasNewPulse;

    noInterrupts();

    interval = inductiveIntervalMicros;
    hasNewPulse = newInductivePulse;
    newInductivePulse = false;

    interrupts();

    if (hasNewPulse && interval > 0) {
      float pulsesPerMinute = 60000000.0f / (float)interval;

      if (FOUR_STROKE) {
        primaryRPM = pulsesPerMinute * 2.0f;
      }
      else {
        primaryRPM = pulsesPerMinute;
      }

      lastInductiveMillis = millis();
    }

    if (millis() - lastInductiveMillis > INDUCTIVE_TIMEOUT_MS) {
      primaryRPM = 0.0f;
    }
  }
  
  void updateSecondaryRPM() {
    unsigned long interval;
    bool hasNewPulse;

    noInterrupts();

    interval = hallIntervalMicros;
    hasNewPulse = newHallPulse;
    newHallPulse = false;

    interrupts();

    if (hasNewPulse && interval > 0) {
      secondaryRPM = 60000000.0f / ((float)interval * PULSES_PER_REV);
      lastHallMillis = millis();
    }

    if (millis() - lastHallMillis > HALL_TIMEOUT_MS) {
      secondaryRPM = 0.0f;
    }
  }
}

// ================
// PUBLIC FUNCTIONS
// ================
bool initializeSensors() {
  pinMode(INDUCTIVE_PIN, INPUT_PULLUP);  // Change INPUT_PULLUP to INPUT for on-engine testing
  attachInterrupt(digitalPinToInterrupt(INDUCTIVE_PIN), onInductivePulse, FALLING);

  pinMode(HALL_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(HALL_PIN), onHallPulse, FALLING);

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
  updateSecondaryRPM();
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
float getSecondaryRPM() {
  return secondaryRPM;
}




