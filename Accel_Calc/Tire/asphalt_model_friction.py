import matplotlib.pyplot as plt
import numpy as np
from sympy import *
from scipy.interpolate import interp1d
import general_constants as gc
from Tire import tire_constants as tc

slips = np.array([0.0, 0.02, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 0.80, 1.0])
coefficients = np.array([0.0, 0.55, 0.66, 1.0, 0.89, 0.76, 0.65, 0.58, 0.55, 0.54])

mu_function = interp1d(slips, coefficients, kind='cubic')

slips_dense = np.linspace(slips[0], slips[-1], 100)
coefficients_dense = mu_function(slips_dense)

def calculate_asphalt_mu(slip: float) -> float:
    return max(float(mu_function(slip)), 0.0)


def plot_mu_curve():
    plt.figure(figsize=(10, 7))
    plt.plot(slips_dense, coefficients_dense, label='Interpolated Coefficient of Friction')
    plt.scatter(slips, coefficients, color='red', label='Measured Coefficient of Friction')
    plt.xlabel('Slip Ratio')
    plt.ylabel('Coefficient of Friction (mu)')
    plt.title('Coefficient of Friction vs Slip Ratio')
    plt.legend()
    plt.grid(True)
    plt.show()
