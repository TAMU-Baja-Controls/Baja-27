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
class PhysicsConstants:
    g: float = 32.17405      # ft / s^2
    air_density: float = 0.0023769  # slugs / ft^3

@frozen
class CarWideConstants:
    A_frontal: float = 18.0   # ft^2
    C_drag: float = 0.563
    C_rolling: float = 0.0122
    W_car: float = 380.0 # lbs
    W_driver: float = 165.0 # lbs
    W_fuel: float = 10.0 # lbs
    W_total: float = W_car + W_driver + W_fuel
    m_total: float = W_total / PhysicsConstants.g  # mass in slugs
    idle_RPM: float = 1800.0
    max_rpm: float = 3600.0
    four_wheel_drive: bool = True
    cg_height: float = 18.25 / 12.0 # ft off the ground
    wheelbase: float = 60.0 / 12.0 # ft

@frozen
class CalcConstants:
    timestep: float = 0.0001 # s

phys: PhysicsConstants = PhysicsConstants()
car: CarWideConstants = CarWideConstants()
calc: CalcConstants = CalcConstants()
cvt: int = 1 # 0 is gaged, 1 is custom
dyno_mode: bool = False # instead of driveline and tire, it uses dyno disk + brake system
