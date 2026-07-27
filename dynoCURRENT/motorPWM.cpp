/*
  PWM .cpp file
*/

#include <Arduino.h>

#include "sensors.h"
#include "motorPWM.h"

// ========================
// PRIVATE FUNCTIONS/CONFIG
// ========================
namespace {
  // Motor PWM config
    const int PWM_PIN = 7;

    const int MIN_PULSE_US = 1000;
    const int NEUTRAL_PULSE_US = 1500;
    const int MAX_PULSE_US = 2000;

    const int PWM_FREQ = 50;
    const int PWM_RES = 14;

    int currentPulseUs = NEUTRAL_PULSE_US; // motor always starts at neutral until user request change

  // Force-to-motor control config
    const float FORCE_CONTROL_GAIN = 2.0f;
    const float FORCE_CONTROL_DEADBAND = 1.0f;

    const int FORCE_CONTROL_MIN_PULSE_US = 1500;
    const int FORCE_CONTROL_MAX_PULSE_US = 2000;

    bool forceControlEnabled = false;

  void writePulseUs(int pulseUs) { // converts the requested pulse amount to PWM signal
    pulseUs = constrain(pulseUs, MIN_PULSE_US, MAX_PULSE_US);

    const uint32_t periodUs = 20000;
    const uint32_t maxDuty = (1UL << PWM_RES) - 1;

    uint32_t duty = ((uint64_t)pulseUs * maxDuty) / periodUs;

    ledcWrite(PWM_PIN, duty);

    currentPulseUs = pulseUs;
  }
}

// ================
// PUBLIC FUNCTIONS
// ================
bool initializeMotorControl() {
  if (!ledcAttach(PWM_PIN, PWM_FREQ, PWM_RES)) {
    return false;
  }

  writePulseUs(NEUTRAL_PULSE_US);

  return true;
}

void setManualPulse(int pulseUs) {
  forceControlEnabled = false;
  writePulseUs(pulseUs);
}

void enableForceControl() {
  forceControlEnabled = true;
}

void disableForceControl() {
  forceControlEnabled = false;
  writePulseUs(NEUTRAL_PULSE_US);
}

void updateForceMotorControl() {
  if (!isForceControlEnabled()) {
    return;
  }

  if (!isLoadCellReady()) {
    writePulseUs(NEUTRAL_PULSE_US);
    return;
  }

  float controlForce = getLoadCellReading();

  if (controlForce < FORCE_CONTROL_DEADBAND) {
    controlForce = 0.0f;
  }

  int pulseOffset = (int)(controlForce * FORCE_CONTROL_GAIN);
  int outputPulse = NEUTRAL_PULSE_US + pulseOffset;

  outputPulse = constrain(outputPulse, FORCE_CONTROL_MIN_PULSE_US, FORCE_CONTROL_MAX_PULSE_US);

  writePulseUs(outputPulse);
}

// =======================
// PUBLIC GETTER FUNCTIONS
// =======================
int getCurrentPulse() { 
  return currentPulseUs;
}
bool isForceControlEnabled() { 
  return forceControlEnabled;
} 






