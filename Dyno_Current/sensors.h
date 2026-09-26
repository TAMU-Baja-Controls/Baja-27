/*
  sensors .h file

  (Before adding anything, think about should code OUTSIDE 
  of sensors.cpp be allowed to call the added function?)
*/

#ifndef SENSORS_H
#define SENSORS_H

bool initializeSensors();
void updateSensors();

bool tareLoadCell();
bool isLoadCellReady();

// Getter functions: allow for files outside of sensors.cpp to access a read-only version of the value
float getPrimaryRPM();
float getSecondaryRPM1();
float getSecondaryRPM2();
float getLoadCellReading();

#endif