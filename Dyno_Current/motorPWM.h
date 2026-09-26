/*
  PWM .h file
*/

#ifndef MOTOR_PWM_H
#define MOTOR_PWM_H

bool initializeMotorControl();

void updateForceMotorControl();
void updateButtonMotorControl();

void enableForceControl();
void disableForceControl();

bool isForceControlEnabled();

void setManualPulse(int pulseUs);
int getCurrentPulse();

#endif