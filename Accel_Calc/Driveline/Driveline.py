import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from Driveline import driveline_constants as dc
import general_constants as gc
from Tire import tire_constants as tc
from Driveline.secondary_forces import get_clamping_force_secondary
from efficiency_helper import get_gear_efficiency, get_rzeppa_efficiency

class Driveline:
    def __init__(self, angular_velocity, shift_out, cvt: int):
        self.angular_velocity = angular_velocity
        self.shift_out = shift_out
        self.cvt = cvt
        pass

    def get_resistive_clamp(self, secondary_torque):
        return get_clamping_force_secondary(secondary_torque, self.shift_out)
    
    def get_output_torque(self, secondary_torque):
        return secondary_torque * dc.final_drive * get_gear_efficiency(gc.car.four_wheel_drive) * get_rzeppa_efficiency(10, gc.car.four_wheel_drive)
    
    # lb-ft^2 from the wheels POV -- not including crank
    def get_driveline_J(self):
        input_J = sum(component.moi * component.qty for component in dc.mois.input) * (dc.final_drive ** 2)
        inter_J = sum(component.moi * component.qty for component in dc.mois.inter) * (dc.final_drive)
        output_J = sum(component.moi * component.qty for component in dc.mois.output)
        return input_J + inter_J + output_J

    def get_effective_mass(self):
        return gc.car.m_total + self.get_driveline_J() / (gc.phys.g * (tc.tire.diameter / 2) ** 2)

