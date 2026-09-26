import matplotlib.pyplot as plt
import numpy as np
from sympy import *
from scipy.interpolate import CubicSpline
import general_constants as gc
from Tire import tire_constants as tc
from Tire.helper import meters, ft, newtons, lbs

# complicated empirical numeric designed for estimating traction

brixius_numeric_1 = (tc.cone_index_kPa * 1000) * meters(tc.tire.diameter) * meters(tc.tire.width) / newtons(gc.car.W_total / 4) # corner weight on each tire

brixius_numeric_2 = 1 + 5 * (tc.tire.deflection / tc.tire.section_height) # no conversion bc ratio

brixius_numeric_3 = 1 + 3 * (tc.tire.width / tc.tire.diameter) # no conversion bc ratio

brixius_numeric = brixius_numeric_1 * brixius_numeric_2 / brixius_numeric_3

# all these random numbers come from this dudes paper lmao
def brixius_coefficients(slip: float) -> float: # returns coef of friction
    gross_coefficient = 0.88 * (1 - np.exp(-0.1 * brixius_numeric)) * (1 - np.exp(-7.5 * slip))
    resistive_coefficient = (1.0 / brixius_numeric) + 0.5 * (slip / np.sqrt(brixius_numeric))
    return gross_coefficient, gross_coefficient - resistive_coefficient
