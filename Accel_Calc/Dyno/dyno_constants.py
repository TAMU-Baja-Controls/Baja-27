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

brake_ratio: float = 4.0