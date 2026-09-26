import matplotlib.pyplot as plt
import numpy as np
from sympy import *
from scipy.interpolate import CubicSpline
from Belt import belt_constants
from _cvts import gaged, custom
from Belt.geometry_state import GeometryState


def test_radii_combo(rad_prim: float, rad_sec: float):
    CC = belt_constants.C.geometry.cc
    L = belt_constants.C.geometry.belt_pitch_length

    term1 = (2 * CC / L) * np.sqrt(1 - ((rad_prim - rad_sec) / CC) ** 2)
    term2 = (np.pi * (rad_prim + rad_sec)) / L
    term3 = (2 * (rad_prim - rad_sec) / L) * np.asin((rad_prim - rad_sec) / CC)

    return abs((term1 + term2 + term3) - 1)

rad_prim_range = np.linspace(belt_constants.C.geometry.min_radius_primary, belt_constants.C.geometry.max_radius_primary, 1000)
rad_sec_range = np.linspace(belt_constants.C.geometry.min_radius_secondary, belt_constants.C.geometry.max_radius_secondary, 1000)

# find optimal secondary radius for each primary radius
# test_radii_combo is all elementwise numpy, so feeding it a column of primary
# radii against a row of secondary radii broadcasts into the full 1000x1000
# error grid in one shot -- no Python-level loop over the million combinations.
belt_length_error = test_radii_combo(rad_prim_range[:, None], rad_sec_range[None, :])

# best secondary radius per primary radius = argmin across each row.
# argmin resolves ties to the lowest index, matching what min() did before.
final_sec_radii = rad_sec_range[np.argmin(belt_length_error, axis=1)]

# interpolate cubic for all the final combinations
interp_radius_spline = CubicSpline(rad_prim_range, final_sec_radii)

# shift in includes engagement empty space
# shift out assumes zero is highest belt ride, so 0 is max radius

def shift_in_to_rad_prim(shift_in: float, cvt: int):
    min_radius = belt_constants.C.geometry.min_radius_primary
    engagement_shift_in = 0.0
    primary_groove_angle = 0.0
    if cvt == 0:
        engagement_shift_in = gaged.Primary.engagement_shift_in
        primary_groove_angle = gaged.Primary.groove_angle
    elif cvt == 1:
        engagement_shift_in = custom.Primary.engagement_shift_in
        primary_groove_angle = custom.Primary.groove_angle

    if shift_in < engagement_shift_in:
        return min_radius  # before engagement
    else:
        return (shift_in - engagement_shift_in) / np.tan(primary_groove_angle) + min_radius  # after engagement
    
def rad_sec_to_shift_out(rad_sec: float, cvt: int):
    max_radius = belt_constants.C.geometry.max_radius_secondary
    sec_groove_angle = 0.0

    if rad_sec > max_radius:
        return 0.0  # beyond maximum radius
    
    if cvt == 0:
        sec_groove_angle = gaged.Secondary.groove_angle
    elif cvt == 1:
        sec_groove_angle = custom.Secondary.groove_angle

    return (max_radius - rad_sec) * np.tan(sec_groove_angle)

# hard part: converting a primary radius into a secondary radius, wrap angles, ratio

def solve_geometry_state(shift_in: float, cvt: int):
    rad_prim = float(shift_in_to_rad_prim(shift_in, cvt))

    rad_sec = float(interp_radius_spline(rad_prim))
    shift_out = float(rad_sec_to_shift_out(rad_sec, cvt))
    # Placeholder values for wrap angles and ratio
    wrap_angle_prim = 0.0
    wrap_angle_sec = 0.0
    ratio = rad_sec / rad_prim
    if ratio > 1.0:
        wrap_angle_prim = np.pi - 2 * np.arcsin((rad_sec - rad_prim) / belt_constants.C.geometry.cc)
        wrap_angle_sec = 2 * np.pi - wrap_angle_prim
    else:
        wrap_angle_prim = np.pi + 2 * np.arcsin((rad_prim - rad_sec) / belt_constants.C.geometry.cc)
        wrap_angle_sec = 2 * np.pi - wrap_angle_prim

    return GeometryState(rad_prim, rad_sec, shift_in, shift_out, wrap_angle_prim, wrap_angle_sec, ratio)