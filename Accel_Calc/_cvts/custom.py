from dataclasses import dataclass, field
import numpy as np

def frozen(cls):
    return dataclass(frozen=True)(cls)

@frozen
class Primary:
    counterspring_rate: float = 64.19       # lbs/in
    counterspring_preload: float = 1.0     # in, based on gaged
    w_weights: float = 1.4                 # lbs, based on Gaged
    w_links: float = 0.2                   # lbs, based on Gaged
    link_length: float = 1.3              # in
    hinge_radius: float = 1.65            # in
    roller_radius: float = 0.25             # in

    moi: float = 0.1514 # lb*ft^2, from CAD
    engagement_shift_in: float = 0.0    # in, based on gaged, the amount of shift to engage the belt

    groove_angle: float = np.radians(24)

    # friction_fudge_factor: float = 1.0  # lbs constant offset that puts the 0 clamp force right at the measured engagement RPM

@frozen
class Secondary:
    compression_spring_rate: float = 22.75  # lbs/in
    torsional_spring_rate: float = 0.0 * (180 / np.pi)   # in-lbs/rad
    helix_angle: float = np.radians(30.0)             # radians
    helix_radius: float = 1.635            # in
    compression_preload: float = 0.83      # in
    torsional_preload: float = np.radians(60.0)        # radians, tunable parameter

    groove_angle: float = np.radians(25.5)

primary = Primary()
secondary = Secondary()
