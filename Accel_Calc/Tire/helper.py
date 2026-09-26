import Tire.tire_constants as tc
# brixius is in metric :(

def meters(input_ft):
    return input_ft * 0.3048

def ft(input_meters):
    return input_meters / 0.3048

def newtons(input_lbs):
    return input_lbs * 4.44822

def lbs(input_newtons):
    return input_newtons / 4.44822


# basic slip calculator:
def slip(w_wheel, v_vehicle): # 0 - 1 -- 0 is rolling, 1 is spinning out with no motion
    tire_surface_speed = w_wheel * tc.tire.diameter / 2
    
    calculated_slip = (tire_surface_speed - v_vehicle) / max(tire_surface_speed, tc.tire.launch_transient_v_floor)
    return max(calculated_slip, 0)

def tangential_velocity_delta(w_wheel, v_vehicle): # tire tangential speed - vehicle speed -- another type of slip
    tire_surface_speed = w_wheel * tc.tire.diameter / 2
    return tire_surface_speed - v_vehicle