import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import scipy as sp
import sympy as sym

G = 32.17405      # ft / s^2
air_density = 0.0023769  # slugs / ft^3

R = 23.0 / 24.0  # ft
A_frontal = 18.0   # ft^2
C_drag = 0.563
C_rolling = 0.0122
W = 390 + 160 + 20

efficiency = 0.9 * (0.98**8) * 0.99 * 0.97
T_redline = 13.5
RPM_redline = 3800.0

overall_ratio_range = np.linspace(3.0, 9.0, 100)  # gear ratio range
geometric_top_speed_range = (RPM_redline * (2 * np.pi / 60) * R) / overall_ratio_range  # ft/s
geometric_top_speed_mph = geometric_top_speed_range * 3600 / 5280  # mph
F_loss_range = 0.5 * air_density * A_frontal * C_drag * geometric_top_speed_range**2 + C_rolling * W  # lbs
F_tractive_range = efficiency * T_redline * overall_ratio_range / R  # lbs

force_difference = abs(F_tractive_range - F_loss_range)
optimal_ratio = overall_ratio_range[np.argmin(force_difference)]
print(f"Optimal Overall High Gear Ratio: {optimal_ratio:.2f}")

# Create subplots with shared x-axis
fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 8))

# First subplot: Geometric top speed vs gear ratio
ax1.plot(overall_ratio_range, geometric_top_speed_range, 'b-', linewidth=2, label='Geometric Top Speed (ft/s)')
ax1.plot(overall_ratio_range, geometric_top_speed_mph, 'b--', linewidth=2, label='Geometric Top Speed (mph)')
ax1.axvline(optimal_ratio, color='k', linestyle='--', linewidth=1, label='Optimal Ratio')
ax1.legend()
ax1.set_ylabel('Geometric Top Speed (ft/s & mph)')
ax1.grid(True, alpha=0.3)

# Second subplot: F_loss and F_tractive vs gear ratio
ax2.plot(overall_ratio_range, F_loss_range, 'r-', linewidth=2, label='F_loss')
ax2.plot(overall_ratio_range, F_tractive_range, 'g-', linewidth=2, label='F_tractive')
ax2.set_xlabel('Overall Gear Ratio')
ax2.set_ylabel('Force (lbs)')
ax2.legend()
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()


