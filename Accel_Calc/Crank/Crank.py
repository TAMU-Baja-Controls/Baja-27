import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from Crank.gaged_primary_forces import get_clamping_force_primary_gaged
from Crank.engine_interpolator import get_engine_torque
from _cvts import gaged, custom
from Driveline import driveline_constants as dc

ENGINE_FLYWHEEL_INERTIA = 1.014 # lb*ft^2

class Crank:
    def __init__(self, engine_rpm, shift_in, cvt: int):
        self.engine_rpm = engine_rpm
        self.shift_in = shift_in
        self.cvt = cvt

    def primary_clamp_force(self):
        if self.cvt == 0:
            return get_clamping_force_primary_gaged(self.engine_rpm, self.shift_in)
        elif self.cvt == 1:
            return 0.0 # FIXME until custom CVT code
    
    def primary_torque(self):
        return get_engine_torque(self.engine_rpm)
    
    # lb-ft^2 from the crank POV -- either from wheel pov or not
    def crank_J(self, engaged: bool, dyno_mode: bool, ratio: float):
        if self.cvt == 0:
            moi = gaged.Primary.moi
        else:
            moi = custom.Primary.moi

        moi += ENGINE_FLYWHEEL_INERTIA

        if not engaged:
            return moi
        elif dyno_mode:
            return moi * (ratio ** 2)
        else:
            return moi * (dc.final_drive ** 2) * (ratio ** 2)