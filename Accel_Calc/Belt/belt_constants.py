import numpy as np
from dataclasses import dataclass, field

def frozen(cls):
    return dataclass(frozen=True)(cls)

# schema

@frozen
class GeometryConstants:
    cc: float                      # in, center-to-center
    belt_height: float             # in
    belt_width: float              # in
    belt_pitch_length: float       # in
    belt_angle: float              # radians, groove angle on the BELT
    min_radius_primary: float
    max_radius_primary: float
    min_radius_secondary: float
    max_radius_secondary: float

@frozen
class ForceConstants:
    belt_weight_total: float       # lbs

@frozen
class Constants:
    geometry: GeometryConstants
    force: ForceConstants
    # Derived values computed from geometry/force
    belt_mass_per_length: float = field(init=False) # slugs / in

    shift_fudge_k: float = 0.0005 # units are (inches / s) / lbs i guess -- not a real physical constant, just a tuning parameter
    # positive constant that turns the secondary clamp delta into a shift_in change for a timestep

    mu: float = 0.3
    mu_k: float = 0.2

    def __post_init__(self):
        object.__setattr__(self, 'belt_mass_per_length',
            self.force.belt_weight_total / (32.174 * self.geometry.belt_pitch_length))


# configs

ENDURO_100 = Constants(
    geometry=GeometryConstants(
        cc=10.0,
        belt_height=0.56,
        belt_width=0.86,
        belt_pitch_length=38,
        belt_angle=np.radians(26.0),
        min_radius_primary=1.21, # on the gaged
        max_radius_primary=2.96,
        min_radius_secondary=2.73,
        max_radius_secondary=4.22,
    ),
    force=ForceConstants(
        belt_weight_total=0.6,
    ),
)

GATES_03G3470 = Constants(
    geometry=GeometryConstants(
        cc=10.0,
        belt_height=0.57,
        belt_width=1.02,
        belt_pitch_length=34.7,
        belt_angle=np.radians(26.0),
        min_radius_primary=1.13, # on the custom cvt
        max_radius_primary=2.96,
        min_radius_secondary=1.62,
        max_radius_secondary=3.39,
    ),
    force=ForceConstants(
        belt_weight_total=0.6,
    ),
)


# edit here to change belts

BELT_CONFIGS = {
    "enduro100": ENDURO_100,
    "gates03G3470": GATES_03G3470,
}

# Select at runtime
C = BELT_CONFIGS["enduro100"]
