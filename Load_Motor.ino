
#include <Arduino.h>
#include "HX711.h"
#include <math.h>

const int HALL_PIN = 0;

const int BUTTON_1_PIN = 5;
const int BUTTON_2_PIN = 6;

const int DOUT_PIN = 9;
const int SCK_PIN = 8;

const int PWM_PIN = 20;

const int BUTTON_1_PULSE_US = 1550;
const int BUTTON_2_PULSE_US = 1450;
const int NEUTRAL_PULSE_US = 1500;

const int MIN_PULSE_US = 1000;
const int MAX_PULSE_US = 2000;

const int PWM_FREQ = 50;
const int PWM_RES = 14;

const float PULSES_PER_REV = 1.0f;

volatile unsigned long hallCount = 0;

float hallRPM = 0.0f;

unsigned long lastRPMTime = 0;

const unsigned long RPM_INTERVAL = 250;

HX711 scale;

float calibrationFactor = 1839.0f;

float massKg = 0.0f;
float forceN = 0.0f;

long rawCounts = 0;

bool lbs = false;
bool firstReading = true;
bool loadCellValid = false;

unsigned long lastLoadTime = 0;
unsigned long sampleNumber = 0;

const unsigned long LOAD_TIMEOUT_MS = 300;

float targetForce = 100.0f;

float kp = 0.8f;
float ki = 0.0f;
float kd = 0.0f;

bool PidEnable = false;

const bool PID_MONITOR_ONLY = true;

float integral = 0.0f;
float previousForce = 0.0f;

unsigned long lastPidTime = 0;
unsigned long lastPidPrint = 0;
unsigned long lastPidSample = 0;

void writePulseUs(int pulseUs);
void updateButtonMotorControl();
void updateLoadCell();
void updateRPM();
void tareScale();
void checkSerialCommands();
void BrakePid();
void resetPid();

void ARDUINO_ISR_ATTR hallISR() {
    hallCount++;
}

void setup() {

    Serial.begin(115200);
    Serial.setTimeout(100);

    delay(1000);

    pinMode(BUTTON_1_PIN, INPUT_PULLUP);
    pinMode(BUTTON_2_PIN, INPUT_PULLUP);

    pinMode(HALL_PIN, INPUT_PULLUP);

    attachInterrupt(
        digitalPinToInterrupt(HALL_PIN),
        hallISR,
        RISING
    );

    lastRPMTime = millis();

    if (!ledcAttach(PWM_PIN, PWM_FREQ, PWM_RES)) {
        Serial.println("ERROR: PWM initialization failed");
    }

    writePulseUs(NEUTRAL_PULSE_US);

    scale.begin(DOUT_PIN, SCK_PIN);

    unsigned long startTime = millis();

    while (!scale.is_ready() &&
           millis() - startTime < 3000) {

        Serial.println("Waiting for HX711...");
        delay(250);
    }

    if (scale.is_ready()) {
        Serial.println("HX711 detected");

        delay(2000);
        tareScale();
    }
    else {
        Serial.println("ERROR: HX711 not detected");
    }

    Serial.println();
    Serial.println("BAJA SAE DYNO SYSTEM READY");

    Serial.println("Serial Commands:");
    Serial.println("T = Tare load cell");
    Serial.println("P = Display pounds");
    Serial.println("K = Display kilograms");
    Serial.println("F = Enable PID monitoring");
    Serial.println("M = Return to manual buttons");
}

void loop() {
    Serial.print("Button1:");
    Serial.println(digitalRead(BUTTON_1_PIN));
    Serial.print("Button2:");
    Serial.println(digitalRead(BUTTON_2_PIN));
    checkSerialCommands();

    updateLoadCell();

    updateRPM();

    if (PidEnable) {
        BrakePid();
    }
    else {
        updateButtonMotorControl();
    }

    static unsigned long lastPrint = 0;

    if (millis() - lastPrint >= 500) {

        Serial.println("========== DYNO DATA ==========");

        Serial.print("Hall RPM: ");
        Serial.println(hallRPM, 1);

        Serial.print("Load Cell Counts: ");
        Serial.println(rawCounts);

        Serial.print("Mass: ");

        if (lbs) {
            Serial.print(massKg * 2.20462f, 3);
            Serial.println(" lbs");
        }
        else {
            Serial.print(massKg, 3);
            Serial.println(" kg");
        }

        Serial.print("Force: ");
        Serial.print(forceN, 2);
        Serial.println(" N");

        Serial.print("Mode: ");
        Serial.println(PidEnable ? "PID MONITOR" : "MANUAL");

        Serial.println("===============================");

        lastPrint = millis();
    }
    delay(1000);

}

void updateRPM() {

    unsigned long now = millis();

    unsigned long elapsed = now - lastRPMTime;

    if (elapsed < RPM_INTERVAL) {
        return;
    }

    noInterrupts();

    unsigned long pulses = hallCount;
    hallCount = 0;

    interrupts();

    float dt = elapsed / 1000.0f;

    hallRPM =
        (pulses * 60.0f) /
        (dt * PULSES_PER_REV);

    lastRPMTime = now;
}

void updateButtonMotorControl() {

    bool button1Pressed =
        digitalRead(BUTTON_1_PIN) == LOW;

    bool button2Pressed =
        digitalRead(BUTTON_2_PIN) == LOW;

    static bool previousButton1 = false;
    static bool previousButton2 = false;

    if (button1Pressed != previousButton1 ||
        button2Pressed != previousButton2) {

        Serial.print("Button 1: ");
        Serial.print(button1Pressed);

        Serial.print(" | Button 2: ");
        Serial.println(button2Pressed);

        previousButton1 = button1Pressed;
        previousButton2 = button2Pressed;
    }

    if (button1Pressed && !button2Pressed) {
        writePulseUs(BUTTON_1_PULSE_US);
    }
    else if (button2Pressed && !button1Pressed) {
        writePulseUs(BUTTON_2_PULSE_US);
    }
    else {
        writePulseUs(NEUTRAL_PULSE_US);
    }

}

void writePulseUs(int pulseUs) {

    pulseUs = constrain(
        pulseUs,
        MIN_PULSE_US,
        MAX_PULSE_US
    );

    const uint32_t periodUs = 20000;

    const uint32_t maxDuty =
        (1UL << PWM_RES) - 1;

    uint32_t duty =
        ((uint64_t)pulseUs * maxDuty) / periodUs;

    ledcWrite(PWM_PIN, duty);
}

void updateLoadCell() {

    if (!scale.is_ready()) {
        return;
    }

    rawCounts = scale.get_value(1);

    float newMass =
        (float)rawCounts / calibrationFactor;

    if (firstReading) {

        massKg = newMass;
        firstReading = false;
    }
    else {

        massKg =
            0.80f * massKg +
            0.20f * newMass;
    }

    forceN = massKg * 9.81f;

    loadCellValid = isfinite(forceN);

    lastLoadTime = millis();

    sampleNumber++;
}

void tareScale() {

    PidEnable = false;

    writePulseUs(NEUTRAL_PULSE_US);

    loadCellValid = false;

    if (!scale.is_ready()) {
        Serial.println("Cannot tare: HX711 not ready");
        return;
    }

    Serial.println("Taring...");

    scale.tare(50);

    massKg = 0.0f;
    forceN = 0.0f;
    rawCounts = 0;

    firstReading = true;

    resetPid();

    Serial.println("Tare complete");
}

void resetPid() {

    integral = 0.0f;
    previousForce = forceN;

    lastPidTime = 0;
    lastPidPrint = 0;
    lastPidSample = sampleNumber;
}

void checkSerialCommands() {

    if (Serial.available() <= 0) {
        return;
    }

    char command = Serial.read();

    if (command == 't' || command == 'T') {

        tareScale();
    }
    else if (command == 'p' || command == 'P') {

        lbs = true;
        Serial.println("Displaying pounds");
    }
    else if (command == 'k' || command == 'K') {

        lbs = false;
        Serial.println("Displaying kilograms");
    }
    else if (command == 'f' || command == 'F') {

        bool sensorFresh =
            loadCellValid &&
            millis() - lastLoadTime <= LOAD_TIMEOUT_MS;

        if (sensorFresh) {

            writePulseUs(NEUTRAL_PULSE_US);

            resetPid();

            PidEnable = true;

            Serial.println("PID MONITOR ENABLED");
            Serial.println("Motor output held neutral");
        }
        else {

            Serial.println("Cannot enable PID: HX711 not ready");
        }
    }
    else if (command == 'm' || command == 'M') {

        PidEnable = false;

        writePulseUs(NEUTRAL_PULSE_US);

        resetPid();

        Serial.println("MANUAL BUTTON MODE ENABLED");
    }
}

void BrakePid() {

    unsigned long now = millis();

    if (!loadCellValid ||
        now - lastLoadTime > LOAD_TIMEOUT_MS) {

        writePulseUs(NEUTRAL_PULSE_US);

        PidEnable = false;

        resetPid();

        Serial.println("PID DISABLED: LOAD CELL TIMEOUT");
        return;
    }

    if (sampleNumber == lastPidSample) {
        return;
    }

    if (lastPidTime != 0 &&
        now - lastPidTime < 50) {
        return;
    }

    float dt = 0.0f;

    if (lastPidTime != 0) {
        dt = (now - lastPidTime) / 1000.0f;
    }

    lastPidTime = now;
    lastPidSample = sampleNumber;

    float error = targetForce - forceN;

    float P = kp * error;

    if (dt > 0.0f && fabsf(error) >= 2.0f) {

        integral += error * dt;

        integral = constrain(
            integral, -50.0f, 50.0f
        );
    }

    float I = ki * integral;

    float derivative = 0.0f;

    if (dt > 0.0f) {
        derivative =
            -(forceN - previousForce) / dt;
    }

    float D = kd * derivative;

    previousForce = forceN;

    float rawOutput = P + I + D;

    float output = constrain(
        rawOutput, -50.0f, 50.0f
    );

    int proposedPulse =
        NEUTRAL_PULSE_US + (int)output;

    if (fabsf(error) < 2.0f) {
        proposedPulse = NEUTRAL_PULSE_US;
    }

    if (PID_MONITOR_ONLY) {
        writePulseUs(NEUTRAL_PULSE_US);
    }

    if (now - lastPidPrint >= 500) {

        Serial.println("---------- PID DATA ----------");

        Serial.print("Target Force: ");
        Serial.println(targetForce, 2);

        Serial.print("Measured Force: ");
        Serial.println(forceN, 2);

        Serial.print("Error: ");
        Serial.println(error, 2);

        Serial.print("P: ");
        Serial.println(P, 3);

        Serial.print("I: ");
        Serial.println(I, 3);

        Serial.print("D: ");
        Serial.println(D, 3);

        Serial.print("Integral: ");
        Serial.println(integral, 3);

        Serial.print("Derivative: ");
        Serial.println(derivative, 3);

        Serial.print("Raw Output: ");
        Serial.println(rawOutput, 3);

        Serial.print("Limited Output: ");
        Serial.println(output, 3);

        Serial.print("Proposed Motor Pulse: ");
        Serial.print(proposedPulse);
        Serial.println(" us");

        Serial.println("------------------------------");

        lastPidPrint = now;
    }
}
