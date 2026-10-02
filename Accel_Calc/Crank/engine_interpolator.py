import numpy as np
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import general_constants as gc

rpms = np.array([1790, 2000, 2200, 2400, 2600, 2800, 3000, 3200, 3400, 3601])
torque = np.array([18.2, 18.6, 18.7, 18.5, 18.1, 17.4, 16.6, 15.4, 14.5, 13.5]) # ft-lbs

rpms_redline = np.array([3600, 3650, 3700, 3750, 3800])
torque_redline = np.array([13.5, 9.5, 4.5, 2.0, 0.0]) # ft-lbs

torque_function = interp1d(rpms, torque, kind='cubic')
torque_redline_function = interp1d(rpms_redline, torque_redline, kind='quadratic')

rpm_dense = np.linspace(rpms[0], rpms[-1], 500)
torque_dense = torque_function(rpm_dense)
power = torque_dense * rpm_dense * 2 * np.pi / 60 / 550 # convert ft-lbs and RPM to horsepower

rpm_redline_dense = np.linspace(rpms_redline[0], rpms_redline[-1], 100)
torque_redline_dense = torque_redline_function(rpm_redline_dense)
power_redline = torque_redline_dense * rpm_redline_dense * 2 * np.pi / 60 / 550 # convert ft-lbs and RPM to horsepower


def get_engine_torque(rpm):

    if rpm < rpms[0] or rpm > rpms_redline[-1]:
        raise ValueError(f"RPM {rpm:.1f} is out of bounds for the torque curve.")

    if (rpm >= rpms_redline[0]):
        return max(float(torque_redline_function(rpm)), 0.0)
    else:
        return float(torque_function(rpm))


def plot_engine_curve():
    plt.figure(figsize=(10, 7))
    plt.plot(rpm_dense, torque_dense, label='Interp Torque (ft-lbs)')
    plt.plot(rpm_dense, power, label='Power (HP)')
    plt.plot(rpm_redline_dense, torque_redline_dense, label='Interp Torque (ft-lbs) - Redline')
    plt.plot(rpm_redline_dense, power_redline, label='Power (HP) - Redline')
    plt.scatter(rpms, torque, color='red', label='Measured Torque (ft-lbs)')
    plt.scatter(rpms_redline, torque_redline, color='orange', label='Measured Torque (ft-lbs) - Redline')
    plt.xlabel('Engine RPM')
    plt.ylabel('Torque (ft-lbs) / Power (HP)')
    plt.title('Engine Torque and Power Curve')
    plt.legend()
    plt.grid(True)
    plt.show()
