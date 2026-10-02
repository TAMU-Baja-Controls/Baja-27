import matplotlib.pyplot as plt
import numpy as np
import sympy as sp
from mpl_toolkits.mplot3d import Axes3D

from _cvts import custom

_clamp_x = [i / 14 for i in range(15)]
_clamp_y = [75, 80, 85, 80, 80, 75, 70, 65, 60, 55, 40, 35, 30, 30, 25]

def get_min_rpm_clamp_force(x):
    if x <= 0: return _clamp_y[0]
    if x >= 1: return _clamp_y[-1]
    i = int(x * 14)
    t = (x - _clamp_x[i]) * 14
    return _clamp_y[i] + t * (_clamp_y[i + 1] - _clamp_y[i])

RPM_SCALER = 9 # multiplication for when RPM = 3600 as opposed to 1500

def get_clamp_force(rpm, shift_in):
    if rpm < 1500:
        return 0

    if rpm > 3600:
        return get_clamp_force(3600, shift_in)

    min_rpm_clamp = get_min_rpm_clamp_force(shift_in / custom.primary.max_shift_in)
    
    scaler = (RPM_SCALER - 1) * (rpm - 1500) / (3600 - 1500) + 1
    return min_rpm_clamp * scaler - custom.primary.counterspring_rate * (shift_in + custom.primary.counterspring_preload)

def plot_primary_curve():
    TEST_SHIFT_IN_RANGE = np.arange(0, custom.primary.max_shift_in, 0.05)
    TEST_RPM_RANGE = range(1500, 3500, 30)

    rpm_vals, shift_vals, clamp_vals = [], [], []

    for shift in TEST_SHIFT_IN_RANGE:
        for rpm in TEST_RPM_RANGE:
            clamp_vals.append(get_clamp_force(rpm, shift))
            rpm_vals.append(rpm)
            shift_vals.append(shift)

    low_rpm_clamp_forces = [get_clamp_force(1500, shift) for shift in TEST_SHIFT_IN_RANGE]
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


# plot_primary_curve()