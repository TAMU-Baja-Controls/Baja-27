import numpy as np
# the final scaled constants I'm using for this model -- pre-testing

BELT_ENGAGEMENT_LOSS = 1.001
BELT_PEAK_ETA = 0.925 # from messick's
BELT_RATIO_POINTS = [ # ratio, efficiency
    (1.0, 1.0),
    (2.7, 0.96),
    (0.5, 0.90),
    (4.0, 0.92)
]

GEAR_EFF_PER_MESH = 0.995 # efficiency per gear mesh, typical value

EFFICIENCY_LOSS_PER_DEGREE = 0.001 # based on Cirelli paper Rzeppa joints


shift_fudge_k: float = 0.0005 # units are (inches / s) / lbs i guess -- not a real physical constant, just a tuning parameter
# positive constant that turns the secondary clamp delta into a shift_in change for a timestep

mu: float = 0.6
mu_k: float = 0.3


slips = np.array([0.0, 0.02, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 0.80, 1.0])
coefficients = np.array([0.0, 0.55, 0.66, 1.0, 0.89, 0.76, 0.65, 0.58, 0.55, 0.54])


TORQUE_FEEDBACK_COEFF = 0.2