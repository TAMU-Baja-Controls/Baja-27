# Texas A&M Baja SAE — Controls & Data Acquisition

**2026–2027 | Texas A&M University**

This repository contains software and engineering tools used by the Texas A&M Baja SAE team to collect, process, and analyze off-road vehicle data. It includes work from the 2026 car as well as ongoing development for the 2026–2027 season.

## Repository contents

| Directory | Contents |
|---|---|
| `26_Accelerated_DAQ/` | 2026 accelerated data acquisition |
| `Working_Accelerated_DAQ/` | DAQ implementation labeled as working |
| `Untested_DAQ_code/` | Experimental, unvalidated DAQ code |
| `Wheel Force Transducer/` | Wheel-force-transducer work |
| `Data_Tools/` | Data processing utilities |
| `Dyno_Current/` | Dynamometer-related work |
| `Accel_Calc/` | Acceleration calculations |
| `2 Ft Drop 1/` | Drop-test materials |
| `generaldata/` | General data files |
| `Old_Files/` | Archived or previous work |

The repository also contains `Load_Motor.ino`, an Arduino sketch.

## 2026–2027 Development

The Controls team is developing hardware and software for more comprehensive vehicle data acquisition and communication.

Current development areas include:

- **CAN Sensor Nodes:** STM32-based hardware for acquiring suspension, wheel-speed, RPM, and other vehicle measurements.
- **Data Acquisition & Logging:** CAN-based data collection, storage, and post-processing for vehicle analysis.
- **Wireless Telemetry:** A LoRa-based system intended to transmit selected vehicle measurements to a ground station.
- **Testing & Validation:** Bench testing, CAN communication testing, and simulated sensor-input testing.

Not all current projects are represented by dedicated folders in this repository yet. New implementations will be documented as they are added.

## Getting Started

Clone the repository:

`git clone https://github.com/TAMU-Baja-Controls/Baja-27.git`

Open the directory corresponding to your subsystem. Hardware requirements, software dependencies, and setup instructions vary by project.

Before running firmware on the vehicle, verify the target hardware, pin assignments, CAN configuration, and test status. Code labeled as untested or archived should not be treated as production-ready.

## Contributing

When adding or modifying a subsystem:

1. Create a descriptive branch and submit a pull request.
2. Document the required hardware, wiring, dependencies, and configuration.
3. Include relevant test results and distinguish simulated, bench, and vehicle validation.
4. Add a README within new project folders explaining setup, functionality, and known limitations.

---

*Maintained by the Texas A&M Baja SAE Controls team. This repository is actively developed throughout the season.*
