import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import scipy as sp
import sympy as sym

# climbing a flat vertical surface, friction assume to be infinite
# calculates necessary torque to climb the wall

W = 390 + 160 + 20 # dry weight + driver + fuel
WB = 62.0 / 12.0 # ft --- assumes a 50-50 weight distribution
CG_HEIGHT = 11.2 / 12.0 # ft -- doesn't matter at THETA = 0
THETA = np.radians(0)  # harshest force required is at 0 degrees, so this is conservative

ENGINE_PEAK_T = 18.5  # ft-lb
ENGINE_T_FACTOR = 0.92 # 90% of peak torque is conservative
ENGINE_PEAK_RPM = 3800 # RPM
ENGINE_RPM_FACTOR = 0.90 # 90% of peak RPM is conservative
CVTS = ["Gaged", "Custom"]
CVT_LOW_RATIO = [3.9, 3.14] # gaged then custom
CVT_HIGH_RATIO = [0.9, 0.54] # gaged then custom
TIRE_RAD = [21.0 / 24.0, 23.0 / 24.0] # ft, old tires then new

f_necessary = 2 * W * (WB * np.cos(THETA) / 2 - np.sin(THETA)*CG_HEIGHT) / (WB * (np.sin(THETA) + np.cos(THETA)))

f_required, drive_ratio, cvt_low_ratio, tire_rad, engine_peak_T = sym.symbols('f_required drive_ratio cvt_low_ratio tire_rad engine_peak_T')

main_eq = sym.Eq(
    engine_peak_T * cvt_low_ratio * drive_ratio / tire_rad,
    f_required
)  


final_drive_sol = sym.solve(main_eq, drive_ratio)

final_drive_func = sym.lambdify((f_required, cvt_low_ratio, tire_rad, engine_peak_T), final_drive_sol[0])

print("-" * 100)
print("Final Drive Calculator -- vertical wall climb:")
print()
print(f"\tTotal Weight: {W} lb (Dry weight + driver + fuel)")
print(f"\tWheelbase: {WB * 12} in")
print(f"\tLongitudinal Weight Distribution: 50-50")
print(f"\tEngine {int(ENGINE_T_FACTOR * 100)}% Peak Torque: {ENGINE_PEAK_T} ft-lb")
print(f"\tEngine {int(ENGINE_RPM_FACTOR * 100)}% RPM: {ENGINE_PEAK_RPM * ENGINE_RPM_FACTOR} RPM")
print()
print("-" * 100)
print(f"{'CVT':<10} {'CVT Low Ratio':<15} {'CVT High Ratio':<15} {'Tire Diameter':<18} {'Final Drive':<15} {'90% Top Speed (mph)':<18}") 
print("-" * 100)
for i, cvt_low in enumerate(CVT_LOW_RATIO):
    for tire_rad in TIRE_RAD:
        final_drive = final_drive_func(f_necessary, cvt_low, tire_rad, ENGINE_PEAK_T * ENGINE_T_FACTOR)
        top_speed = (ENGINE_PEAK_RPM * ENGINE_RPM_FACTOR * (2 * np.pi / 60) * tire_rad) / (CVT_HIGH_RATIO[i] * final_drive)  # ft/s
        top_speed_mph = top_speed * 3600.0 / 5280.0  # convert ft/s to mph
        print(f"{CVTS[i]:<10} {cvt_low:<15.2f} {CVT_HIGH_RATIO[i]:<15.2f} {(tire_rad * 24):<18.4f} {final_drive:<15.4f} {top_speed_mph:<18.4f}")
print("-" * 100)