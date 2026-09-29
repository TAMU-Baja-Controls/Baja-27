import matplotlib.pyplot as plt
import numpy as np
import sympy as sp
from mpl_toolkits.mplot3d import Axes3D
from Crank import gaged_geom_helper
from _cvts import gaged

F_r, F_l, A_x, A_y, theta, ramp_angle = sp.symbols('F_r F_l A_x A_y theta ramp_angle')
# statics equations for flyweight clamp
eq1 = sp.Eq(
    0,
    F_r + A_y + A_x / sp.tan(ramp_angle)
)

eq2 = sp.Eq(
    F_l * sp.cos(theta) / 2,
    A_y * sp.cos(theta) + A_x * sp.sin(theta)
)

soln = sp.solve([eq1, eq2], (A_x, A_y))
flyweight_soln_lambda = sp.lambdify((F_r, F_l, theta, ramp_angle), (soln[A_x], soln[A_y]), 'numpy')

def get_clamping_force_primary_gaged(engine_rpm, X_prim):

    quick_theta = np.radians(gaged_geom_helper.quick_theta(X_prim))
    ramp_angle = np.radians(gaged_geom_helper.quick_tangent_angle(X_prim))

    radius_weights = (gaged.primary.hinge_radius + gaged.primary.link_length * np.sin(quick_theta)) # in
    F_weights = (gaged.primary.w_weights / 32.2) * ((engine_rpm * 2 * np.pi / 60) ** 2) * (radius_weights / 12.0) # lbs

    radius_links = (gaged.primary.hinge_radius + gaged.primary.link_length * np.sin(quick_theta) / 2) # in
    F_links = (gaged.primary.w_links / 32.2) * ((engine_rpm * 2 * np.pi / 60) ** 2) * (radius_links / 12.0) * (np.sin(quick_theta) / 2) # lbs

    A_x, A_y = flyweight_soln_lambda(F_weights, F_links, quick_theta, ramp_angle)

    F_counterspring = gaged.primary.counterspring_rate * (gaged.primary.counterspring_preload + X_prim) # lbs

    # if (engine_rpm > gaged.primary.fudged_engagement_rpm):
    #     clamping_force_prim = -A_x - F_counterspring
    # else:
    #     clamping_force_prim = 0
    
    return -A_x - F_counterspring

def plot_primary_curve():
    TEST_SHIFT_IN_RANGE = np.arange(0, 0.75, 0.05)
    TEST_RPM_RANGE = range(1500, 3500, 50)

    rpm_vals, shift_vals, clamp_vals = [], [], []

    for shift in TEST_SHIFT_IN_RANGE:
        for rpm in TEST_RPM_RANGE:
            clamp_vals.append(get_clamping_force_primary_gaged(rpm, shift))
            rpm_vals.append(rpm)
            shift_vals.append(shift)

    low_rpm_clamp_forces = [get_clamping_force_primary_gaged(1500, shift) for shift in TEST_SHIFT_IN_RANGE]
    for f in low_rpm_clamp_forces:
        print(f)

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(rpm_vals, shift_vals, clamp_vals, marker='o')
    ax.set_xlabel('Engine RPM')
    ax.set_ylabel('Shift In (in)')
    ax.set_zlabel('Primary Clamping Force (lbs)')
    ax.set_title('Primary Clamping Force vs Engine RPM and Shift Distance')
    plt.show()

