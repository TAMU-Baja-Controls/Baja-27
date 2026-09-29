from dataclasses import dataclass, field
import numpy as np

def frozen(cls):
    return dataclass(frozen=True)(cls)

@frozen
class Primary:
    counterspring_rate: float = 3.0 * 4       # lbs/in
    counterspring_preload: float = 0.1     # in, based on gaged

    moi: float = 0.06 # lb*ft^2, from CAD
    engagement_shift_in: float = 0.0    # in, based on gaged, the amount of shift to engage the belt
    max_shift_in: float = 0.83
    groove_angle: float = np.radians(26)

    # friction_fudge_factor: float = 1.0  # lbs constant offset that puts the 0 clamp force right at the measured engagement RPM

@frozen
class Secondary:
    compression_spring_rate: float = 20  # lbs/in
    torsional_spring_rate: float = 0.0   # in-lbs/rad
    helix_angle: float = np.radians(60.0)             # radians
    helix_radius: float = 2.0            # in
    compression_preload: float = 0.3      # in
    torsional_preload: float = np.radians(60.0)        # radians, tunable parameter

    groove_angle: float = np.radians(26)

primary = Primary()
secondary = Secondary()
