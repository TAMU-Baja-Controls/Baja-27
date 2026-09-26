import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from Belt.belt_geometry import solve_geometry_state
from Belt.belt_forces import mu_effective, propagate_clamp_forward
from Belt.geometry_state import GeometryState
from Belt import belt_constants
from _cvts import gaged, custom
from efficiency_helper import get_belt_efficiency

class Belt:
    def __init__(self, angular_velocity, shift_in, cvt: int):
        self.angular_velocity = angular_velocity
        self.shift_in = shift_in
        self.cvt = cvt

    def get_geometry_state(self) -> GeometryState:
        return solve_geometry_state(self.shift_in, self.cvt)

    # finds the torque transfer of the belt
    # uses the effective torque from the primary as an input (after taking engagement slip into account)
    # also takes in the axial clamp force from primary
    # also applies a fudge-y belt efficiency factor from Messick's paper
    def calculate_output_torque_clamp(self, input_torque, input_clamp, geometryState: GeometryState):
        sec_clamp, sec_torque, slipping = propagate_clamp_forward(input_torque, self.angular_velocity, input_clamp, geometryState, self.cvt)
        sec_torque = sec_torque * get_belt_efficiency(geometryState.ratio)
        return sec_torque, sec_clamp, slipping
    
    def primary_sliding_torque(self, input_clamp, geometryState: GeometryState):
        if self.cvt == 0:
            groove_angle = gaged.Primary.groove_angle
        else:
            groove_angle = custom.Primary.groove_angle

        normal_on_sheaves = (2 * input_clamp) / np.cos(groove_angle / 2) # need to check my math here -- and on belt stuff overall now ig
        force_sliding = belt_constants.C.mu_k * normal_on_sheaves
        return force_sliding * geometryState.rad_prim / 12 # convert from in-lbs to ft-lbs 
    
    def shift_from_delta(self, shift_force_delta, timestep):

        if self.cvt == 0:
            max_shift_in = gaged.Primary.max_shift_in
        else:
            max_shift_in = custom.Primary.max_shift_in

        self.shift_in += belt_constants.C.shift_fudge_k * shift_force_delta * timestep
        # clamping the shift-in
        self.shift_in = max(0.0, min(self.shift_in, max_shift_in))
        new_geometry_state = solve_geometry_state(self.shift_in, self.cvt)
        return new_geometry_state