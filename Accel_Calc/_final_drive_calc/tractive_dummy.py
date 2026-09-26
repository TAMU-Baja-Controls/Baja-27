# silly math to do tractive shit

eff = 0.9 * (0.98**8) * 0.99 * 0.97

max_torque = 18.5

tire_radius = 23.0 / 24.0

cvt_low = 3.14

MU = 0.6

W = 390 + 160 + 20

overall_required = (W * MU * tire_radius) / (max_torque * eff)
print(f"Overall Required: {overall_required:.4f}")

final_drive = overall_required / cvt_low
print(f"Final Drive: {final_drive:.4f}")