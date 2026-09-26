import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from Dyno import dyno_constants as dyno_constants
from Driveline.secondary_forces import get_clamping_force_secondary
import general_constants as gc
import Driveline.driveline_constants as dc
import Tire.tire_constants as tc

class Dyno:
    def __init__(self, angular_velocity, effective_position, shift_out, cvt: int):
        self.angular_velocity = angular_velocity
        self.effective_velocity = self.convert_angular_to_effective(angular_velocity)
        self.effective_position = effective_position
        self.shift_out = shift_out
        self.cvt = cvt
        pass

    def get_resistive_clamp(self, secondary_torque):
        return get_clamping_force_secondary(secondary_torque, self.shift_out)

    def get_brake_torque(self, secondary_torque):
        return secondary_torque * dyno_constants.brake_ratio

    # can be length, velocity, or acceleration -- rad to ft
    # reflects dyno rotating to real world distance/speed/acceleration
    def convert_angular_to_effective(self, angular_unit):
        return angular_unit / dc.final_drive * (tc.tire.diameter / 2)

    def get_dyno_accels(self, secondary_torque, J_eff):
        dyno_angular_accel = secondary_torque / (J_eff / gc.phys.g)  # angular acceleration of just the dyno
        effective_accel = self.convert_angular_to_effective(dyno_angular_accel)
        return effective_accel, dyno_angular_accel

    def get_dyno_J(self):
        # input_J = sum(component.moi * component.qty for component in dyno_constants.mois.input) * (dyno_constants.final_drive ** 2)
        # inter_J = sum(component.moi * component.qty for component in dyno_constants.mois.inter) * (dyno_constants.final_drive)
        # output_J = sum(component.moi * component.qty for component in dyno_constants.mois.output)
        return 7.76