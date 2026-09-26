import matplotlib.pyplot as plt
import numpy as np
from sympy import *
from scipy.interpolate import CubicSpline
from Tire.soil_model_brixius import brixius_coefficients
from Tire.asphalt_model_friction import calculate_asphalt_mu
from Tire.helper import slip, tangential_velocity_delta
from Tire import tire_constants as tc
import general_constants as gc

class Tire:
    def __init__(self, angular_velocity, vehicle_velocity, vehicle_position):
        self.angular_velocity = angular_velocity
        self.vehicle_velocity = vehicle_velocity
        self.vehicle_position = vehicle_position
        self.last_acceleration = 0.0

    # returns the torque loss due to rolling resistance and aerodynamic drag
    def get_external_loss(self):
        if (self.angular_velocity <= 0.0):
            return 0.0
        
        F_rr = gc.car.W_total * gc.car.C_rolling
        F_drag = 0.5 * gc.phys.air_density * gc.car.C_drag * gc.car.A_frontal * self.vehicle_velocity ** 2
        return F_rr + F_drag

    def rear_wheel_load_lbs(self, acceleration):
        # calculates the rear wheel load in lbs based on the vehicle acceleration and geometry
        W_total = gc.car.W_total
        m_total = gc.car.m_total
        cg_height = gc.car.cg_height
        wheelbase = gc.car.wheelbase

        # calculate the weight transfer due to acceleration
        weight_transfer = (m_total * cg_height * acceleration) / wheelbase

        # calculate the rear wheel load
        rear_wheel_load = (W_total * 0.54) + weight_transfer

        return rear_wheel_load

    def get_transient_accels_brixius(self, final_torque, J_eff):
        # torque exerted by the ground on the wheel through shear forces
        slip_percent: float = slip(self.angular_velocity, self.vehicle_velocity)
        tangential_velocity_difference = tangential_velocity_delta(self.angular_velocity, self.vehicle_velocity)

        gross_coefficient, net_coefficient = brixius_coefficients(slip_percent)

        if (gc.car.four_wheel_drive):
            W = gc.car.W_total
        else:
            W = gc.car.W_total * 0.5

        vehicle_acceleration = (W * net_coefficient - self.get_external_loss()) / gc.car.m_total  # linear acceleration of the vehicle
        vehicle_acceleration = max(vehicle_acceleration, 0.0)  # don't allow negative acceleration
        # the "torque left over" to spin up driveline
        net_tire_torque = final_torque - W * gross_coefficient * tc.tire.diameter / 2
        tire_angular_acceleration = net_tire_torque / (J_eff / gc.phys.g) # convert lbs-ft^2 to slugs-ft^2
        return vehicle_acceleration, tire_angular_acceleration, slip_percent, tangential_velocity_difference

    def get_transient_accels_friction(self, final_torque, J_eff, m_eff):
        # torque exerted by the ground on the wheel through shear forces
        slip_percent: float = slip(self.angular_velocity, self.vehicle_velocity)
        tangential_velocity_difference = tangential_velocity_delta(self.angular_velocity, self.vehicle_velocity)

        tire_rad = tc.tire.diameter / 2

        if (gc.car.four_wheel_drive):
            W = gc.car.W_total
        else:
            W = self.rear_wheel_load_lbs(self.last_acceleration)  # weight transfer for 2wd
            # W = m_eff * gc.phys.g  # keaton bs lol

        # maximum force to accelerate the car with
        friction_ceiling_force = W * calculate_asphalt_mu(slip_percent)

        vehicle_acceleration = (friction_ceiling_force - self.get_external_loss()) / gc.car.m_total
        vehicle_acceleration = max(vehicle_acceleration, 0.0)

        tire_angular_acceleration = (final_torque - friction_ceiling_force * tire_rad) / (J_eff / gc.phys.g)

        # the force that needs to be compared to my friction ceiling
        adjusted_tangential_force = (final_torque * gc.car.m_total * tire_rad) / (gc.car.m_total * tire_rad**2 + J_eff / gc.phys.g)
        tractive_force_difference = adjusted_tangential_force - friction_ceiling_force # negative means grip, positive means slipping

        self.last_acceleration = vehicle_acceleration
        return vehicle_acceleration, tire_angular_acceleration, slip_percent, tractive_force_difference
