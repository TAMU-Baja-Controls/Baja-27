import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from sympy import *
from scipy.interpolate import interp1d

# since efficiency is so fudgey, I'm not gonna mix it with the main physics calculations.

# -------------------- BELT ----------------------
BELT_ENGAGEMENT_LOSS = 1.001
BELT_PEAK_ETA = 0.90 # from messick's
BELT_RATIO_POINTS = [ # ratio, efficiency
    (1.0, 1.0),
    (2.7, 0.96),
    (0.5, 0.90),
    (4.0, 0.92)
]

_ratio_data = np.array([p[0] for p in BELT_RATIO_POINTS])
_eta_data = np.array([p[1] for p in BELT_RATIO_POINTS])
linear_interp = interp1d(_ratio_data, _eta_data, kind='linear')

def get_belt_efficiency(ratio):
    return float(linear_interp(ratio)) * BELT_PEAK_ETA

# -------------------- GEARS ----------------------
GEAR_EFF_PER_MESH = 0.99 # efficiency per gear mesh, typical value

def get_gear_efficiency(num_meshes):
    return GEAR_EFF_PER_MESH ** num_meshes

# -------------------- RZEPPA CV JOINTS ----------------------
EFFICIENCY_LOSS_PER_DEGREE = 0.002 # based on Cirelli paper

def get_rzeppa_efficiency(angle_degrees, four_wheel_drive: bool):
    eta_one_joint = 1.0 - (EFFICIENCY_LOSS_PER_DEGREE * angle_degrees)
    if four_wheel_drive: # for 4x4
        return eta_one_joint ** 8
    else: # for 2wd
        return eta_one_joint ** 4
    