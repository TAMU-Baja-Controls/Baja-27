from dataclasses import dataclass
from enum import Enum
import numpy as np

@dataclass(frozen=True)
class _Frozen:
    pass

def frozen(cls):
    return dataclass(frozen=True)(cls)

@frozen
class MOI_Component:
    name: str
    moi: float  # Moment of inertia, lb*ft^2
    qty: int

@frozen
class MOIConstants:
    input: tuple[MOI_Component, ...] = (
        MOI_Component(name="CVT_SECONDARY", moi=0.05, qty=1), # 0.05 for 27, 0.1 for 26
        MOI_Component(name="GB_INPUT_SHAFT", moi=0.00055, qty=1),
        MOI_Component(name="GB_INPUT_GEAR",  moi=0.00084, qty=1),
    )
    inter: tuple[MOI_Component, ...] = (
        MOI_Component(name="GB_INTERMEDIATE_SHAFT",  moi=0.000497, qty=1),
        MOI_Component(name="GB_INTERMEDIATE_GEAR_1", moi=0.0174,   qty=1),
        MOI_Component(name="GB_INTERMEDIATE_GEAR_2", moi=0.0016,   qty=1),
    )
    output: tuple[MOI_Component, ...] = (
        MOI_Component(name="GB_OUTPUT_SHAFT",  moi=0.00239,  qty=1),
        MOI_Component(name="GB_OUTPUT_GEAR",   moi=0.08596,  qty=2),
        MOI_Component(name="REAR_ROTOR",       moi=0.00772,  qty=1),
        MOI_Component(name="REAR_ROTOR_MOUNT", moi=0.00074,  qty=1),
        MOI_Component(name="FRONT_ROTOR",      moi=0.01897,  qty=2),
        MOI_Component(name="INBOARD_CV",       moi=0.01,     qty=4),
        MOI_Component(name="OUTBOARD_CV",      moi=0.01,     qty=4),
        MOI_Component(name="REAR_HUB",         moi=0.00786,  qty=2),
        MOI_Component(name="FRONT_HUB",        moi=0.00831,  qty=2),
        MOI_Component(name="DRIVE_AXLE",       moi=0.001,    qty=4),
        MOI_Component(name="TIRE_ASSEMBLY",    moi=7.2685,   qty=4),
    )

mois: MOIConstants = MOIConstants()
final_drive: float = 9.0