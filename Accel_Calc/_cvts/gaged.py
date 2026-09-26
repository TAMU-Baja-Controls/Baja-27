from dataclasses import dataclass, field
import numpy as np

def frozen(cls):
    return dataclass(frozen=True)(cls)

@frozen
class Primary:
    counterspring_rate: float = 64.19       # lbs/in
    counterspring_preload: float = 0.875     # in, based on gaged
    w_weights: float = 1.4                 # lbs, based on Gaged
    w_links: float = 0.2                   # lbs, based on Gaged
    link_length: float = 1.3              # in
    hinge_radius: float = 1.65            # in
    roller_radius: float = 0.25             # in

    moi: float = 0.1514 # lb*ft^2, from CAD
    # moi: float = 0.075 # testing new effect
    engagement_shift_in: float = 0.0    # in, based on gaged, the amount of shift to engage the belt -- simplification for immediate shift-in
    max_shift_in: float = 0.75
    groove_angle: float = np.radians(16.44)

    fudged_engagement_rpm: float = 2100
     

@frozen
class Ramp:
    ramp_x_offset: float = 0.4875 # ramp start to hinge center
    ramp_length: float = 0.944
    ramp_coords: list = field(default_factory=lambda: [
        (0.0, 0.175),
        (0.2, 0.258),
        (0.4, 0.352),
        (0.6, 0.457),
        (0.8, 0.574),
        (0.944, 0.665)
    ])
    ramp_base_radius: float = 2.568

@frozen
class Secondary:
    compression_spring_rate: float = 22.75  # lbs/in
    torsional_spring_rate: float = 0.592 * (180 / np.pi)   # in-lbs/rad
    helix_angle: float = np.radians(32.0)              # radians
    helix_radius: float = 1.635            # in
    compression_preload: float = 0.83      # in
    torsional_preload: float = np.radians(70.0)        # radians, tunable parameter

    groove_angle: float = np.radians(28.59)

primary = Primary()
ramp = Ramp()
secondary = Secondary()
