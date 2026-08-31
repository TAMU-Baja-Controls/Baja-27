/* READ ME
  TAMU 2027-2028 Dynamometer Brake Actuation Script

  Pinout (currently using ESP32-C3-SuperMini)
    GPIO 0: Hall-effect secondary RPM (1)
    GPIO 1: Hall-effect secondary RPM (2)
    GPIO 2: Inductive primary RPM
    GPIO 5: HX711 DT
    GPIO 6: HX711 SCK
    GPIO 7: PWM signal

  Motor roation relative to PWM signal
    1000 us = Max clockwise
    1500 us = Neutral
    2000 us = Max counterclockwise

  Commands entered through the Serial Monitor
    1000 to 2000 = Manual PWM command
    t = Tare load cell
    f = Enable force-to-motor control
    m = Return to manual motor control
  
  Setup process (assuming connections are correct)
  *Wait 3-5 min. if load cell was used recently to allow it to settle
    1. Power on system
    2. Enter "t" into serial monitor to tare system
    3. Enter either "f" or "m" depending on control method desired
      a. If "m" is selected, enter desired PWM output
      b. If "f" is selected, monitor system for failure
    4. Enter either "f" or "m" to switch between modes
    5. Enter "t" to tare system again if needed
*/

#include <Arduino.h>

#include "sensors.h"
#include "motorPWM.h"

void readSerialInput() {
  if (Serial.available() <= 0) {
    return;
  }

  String input = Serial.readStringUntil('\n');
  input.trim();

  if (input.length() == 0) {
    return;
  }

  if (input.equalsIgnoreCase("t")) {
    disableForceControl();
    tareLoadCell();
    return;
  }

  if (input.equalsIgnoreCase("f")) {
    if (!isLoadCellReady()) {
      disableForceControl();

      Serial.println("Force-to-motor control failed: load cell not ready.");
      return;
    }
    enableForceControl();
    
    Serial.println("Force-to-motor control enabled.");
    return;
  }

  if (input.equalsIgnoreCase("m")) {
    disableForceControl();

    Serial.println("Manual motor control enabled.");
    return;
  }

  int requestedPulse = input.toInt(); // set user input to int requestedPulse

  if (requestedPulse == 0) {
    Serial.println("Invalid input.");
    return;
  }

  setManualPulse(requestedPulse);

  Serial.print("Requested PWM: ");
  Serial.print(requestedPulse);
  Serial.print(" us | Output PWM: ");
  Serial.print(getCurrentPulse());
  Serial.println(" us");
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);

  delay(1000);

  bool motorInitialized = initializeMotorControl();
  bool sensorInitialized = initializeSensors();

  Serial.println();
  Serial.println("STARTING DYNO CONTROLLER...");
  Serial.println();

  if (motorInitialized) {
    Serial.println("PWM initialization status: PASSED");
  } 
  else {
    Serial.println("PWM initialization status: FAILED");
  }

  if (sensorInitialized) {
    Serial.println("Sensor initialization status: PASSED");
  }
  else {
    Serial.println("Sensor initialization status: FAILED");
  }

  Serial.println();

  if (motorInitialized && sensorInitialized) {
    Serial.println("Dyno controller initialization status: PASSED");
  }
  else {
    Serial.println("Dyno controller initialization status: FAILED");
  }

  Serial.println();

  Serial.println("Serial commands:");
  Serial.println("  t: tare the load cell.");
  Serial.println("  f: enables force-to-motor control.");
  Serial.println("  m: enables manual motor control.");
}

void loop() {
  static unsigned long lastPrintMs = 0;

  readSerialInput();
  updateSensors();
  // updateForceMotorControl(); // disabled for button testing
  updateButtonMotorControl();

  if (millis() - lastPrintMs >= 100) {
    lastPrintMs = millis();

    Serial.print("Primary RPM: ");
    Serial.print(getPrimaryRPM(), 1);

    Serial.print(" | Secondary RPM 1: ");
    Serial.print(getSecondaryRPM1(), 1);

    Serial.print(" | Secondary RPM 2: ");
    Serial.print(getSecondaryRPM2(), 1);

    Serial.print(" | Load cell: ");

    if (isLoadCellReady()) {
      Serial.print(getLoadCellReading(), 3);
    }
    else {
      Serial.print("LOAD CELL NOT READY");
    }

    Serial.print(" | PWM: ");
    Serial.print(getCurrentPulse());
    Serial.print(" us");

    Serial.print(" | Control mode: ");

    if (isForceControlEnabled()) {
      Serial.println("FORCE");
    }
    else {
      Serial.println("MANUAL");
    }
  }
}