\# Dyno Firmware

Firmware for the Baja dynamometer controller



Current functionality:

\- Primary RPM (Inductive sensor)

\- Secondary RPM (Hall-Effect) (2x)

\- Load-cell 

\- Motor control



\## TODO

\### Team

\- \[ ] Add ToF sensors for sheave position (2x)

\- \[ ] Make mount for ToF sensors

\- \[ ] Implement direct data collection with PuTTy or Python script

\- \[ ] Display graphs for engine performance over time

\- \[ ] Confirm final Hall-effect pulses-per-revolution value

\- \[ ] Start on dyno PCB board

\- \[ ] Implement PID controller

\- \[ ] Integrate RPM/torque target calculation

\- \[ ] Add limit switches for motor actuation

\- \[ ] Work on full dyno wiring harness

\- \[ ] Add CYD or OLED for vitals update



\## Known Issues

\- N/A



\## Notes

\- Motor neutral command: `1500 us`

