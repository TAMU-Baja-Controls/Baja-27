import matplotlib.pyplot as plt
from sympy import *
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from scipy.interpolate import interp1d, CubicSpline
from _cvts import gaged

# Build interpolated lookup table from ramp_coords
xs, ys = zip(*gaged.ramp.ramp_coords)
xs = np.array(xs)
ys = np.array(ys)

ramp_interp = CubicSpline(xs, ys) # ramp y as a function of the local ramp x

# Dense x values for smooth curve
x_fine = np.linspace(xs[0], xs[-1], 500)
y_fine = ramp_interp(x_fine)

# Tangent angle lookup table: arctan(dy/dx) in degrees
dydx_fine = ramp_interp.derivative()(x_fine)
angle_fine = np.degrees(np.arctan(dydx_fine))

tangent_angle_local_interp = interp1d(x_fine, angle_fine, kind='cubic')

# now I need to find an x_ramp_local
def solve_for_X(X):
    x_local_range = np.linspace(0, gaged.ramp.ramp_length, 500)
    x_global_range = x_local_range + gaged.ramp.ramp_x_offset + X

    y_local_range = ramp_interp(x_local_range)
    y_global_range = gaged.ramp.ramp_base_radius - gaged.primary.hinge_radius - y_local_range

    tangent_angles = tangent_angle_local_interp(x_local_range)

    link_end_x = x_global_range - gaged.primary.roller_radius * np.sin(np.radians(tangent_angles))
    link_end_y = y_global_range - gaged.primary.roller_radius * np.cos(np.radians(tangent_angles))

    # theta is a single number where magnitude of link length is closes to LINK_LENGTH
    min_error_idx = np.argmin(np.abs(np.sqrt(link_end_x**2 + link_end_y**2) - gaged.primary.link_length))
    theta = np.degrees(np.arctan2(link_end_y[min_error_idx], link_end_x[min_error_idx]))
    tangent_angle_at_theta = tangent_angles[min_error_idx]

    return theta, tangent_angle_at_theta

x_range = np.linspace(0.0, 0.75, 100)
thetas = [solve_for_X(x)[0] for x in x_range]
tangent_angles = [solve_for_X(x)[1] for x in x_range]

theta_interp = interp1d(x_range, thetas, kind='cubic')
tangent_angle_interp = interp1d(x_range, tangent_angles, kind='cubic')

def quick_theta(X):
    return theta_interp(X)

def quick_tangent_angle(X):
    return tangent_angle_interp(X)
