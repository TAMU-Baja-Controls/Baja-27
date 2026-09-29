import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from sympy import *
import general_constants
from _cvts import gaged, custom

# Symbols
X_sec, torque_sec, clamping_force_sec = symbols('X_sec torque_sec clamping_force_sec', real=True)

if general_constants.cvt == 0:
    C_sec = gaged.secondary
else:
    C_sec = custom.secondary

# Precompute pure numeric constants from fixed parameters
helix_tan = tan(C_sec.helix_angle)  # sympy tan of constant
rad_per_in = helix_tan * C_sec.helix_radius  # twist rate (rad/in of shift)

# Intermediate expressions
linear_spring_expr = C_sec.compression_spring_rate * (X_sec + C_sec.compression_preload)

torsion_spring_expr = C_sec.torsional_spring_rate * (rad_per_in * X_sec + C_sec.torsional_preload)  # in-lbs

TORQUE_FEEDBACK_COEFF = 0.25

torque_feedback_expr = torque_sec * 12 * TORQUE_FEEDBACK_COEFF

helix_expr = (torsion_spring_expr + torque_feedback_expr) / (C_sec.helix_radius * helix_tan)

# Master equation
clamping_force_eq = Eq(
    clamping_force_sec,
    linear_spring_expr + helix_expr
)

clamp_force_func = lambdify((X_sec, torque_sec), clamping_force_eq.rhs, 'numpy')

# Solve for clamping force given X_sec and torque_sec
def get_clamping_force_secondary(torque_val, shift_out_val):
    return clamp_force_func(shift_out_val, torque_val)


def plot_secondary_clamp_force():
    torque_range = np.linspace(0, 80, 25)  # example range from 0 to 80 ft-lbs with 50 points
    x_sec_range = np.linspace(0, 0.75, 25)  # example range from 0 to 2 inches with 10 points

    # Create 3D scatter plot
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # Calculate clamping force for each combination
    torque_points = []
    x_sec_points = []
    clamping_force_points = []
    
    for torque_val in torque_range:
        for x_sec_val in x_sec_range:
            torque_points.append(torque_val)
            x_sec_points.append(x_sec_val)
            clamping_force_points.append(get_clamping_force_secondary(torque_val, x_sec_val))

    # Plot scatter points
    scatter = ax.scatter(torque_points, x_sec_points, clamping_force_points, c=clamping_force_points, cmap='viridis')

    # Labels
    ax.set_xlabel('Torque (ft-lbs)')
    ax.set_ylabel('Shift (inches)')
    ax.set_zlabel('Clamping Force (lbs)')
    ax.set_title('Secondary Clamping Force vs Torque and Shift')

    plt.show()
