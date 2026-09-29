from dataclasses import dataclass
from enum import Enum
import numpy as np

@dataclass(frozen=True)
class _Frozen:
    pass

def frozen(cls):
    return dataclass(frozen=True)(cls)

@frozen
class TireConstants:
    diameter: float = 23.0 / 12.0  # ft
    width: float = 7.0 / 12.0    # ft
    deflection: float = 1.0 / 12.0  # ft -- how much radius is lost to squish
    section_height: float = 5.5 / 12.0  # ft -- edge of rim bead to edge of tire

    launch_transient_v_floor: float = 2.0 # ft / s helps make slip calculations sane at launch
@frozen
class SurfaceConstants:
    cone_index_kPa: float

# surface configs

LOOSE_SAND = 200.0

SANDY_LOAM = 900.0

FIRM_DIRT = 1500.0

HARD_PACK_DIRT = 3000.0

ASPHALT = 7000.0

tire = TireConstants()
cone_index_kPa = FIRM_DIRT  # edit here before runtime