import numpy as np
import pandas as pd
from scipy.integrate import cumulative_trapezoid

FILENAME = "CVT_RUN_3"
FILENAME_FILTERED = "26_RUN_3_FILTERED"

FINAL_DRIVE = 7.26
WHEEL_RAD_IN = 21.0 / 24.0  # radius of 26 tires in feet

df = pd.read_csv("../26_Accelerated_DAQ/Data_Raw/{}.csv".format(FILENAME))

df["time_s"] = (df["timestamp_ms"] - df["timestamp_ms"].iloc[0]) / 1000.0
df["driveline_angular_velocity"] = df["sec_rpm"] * 2 * np.pi / 60  # Convert RPM to rad/s
df["accel_x_ft_s_s"] = df["g_x"] * 32.174 # Convert g to ft/s^2
df["integrated_car_velocity_ft_s"] = cumulative_trapezoid(df["accel_x_ft_s_s"], df["time_s"], initial=0) # integrated IMU
df["effective_position_ft"] = cumulative_trapezoid(df["integrated_car_velocity_ft_s"], df["time_s"], initial=0) # double integrated IMU
df["racebox_speed_ft_s"] = df["speed_mph"] * 5280 / 3600  # Convert mph to ft/s
df["racebox_position_ft"] = cumulative_trapezoid(df["racebox_speed_ft_s"], df["time_s"], initial=0) # racebox position
df["tire_angular_velocity"] = df["driveline_angular_velocity"] / FINAL_DRIVE # rad / s of the actual tire
# this assumes no slip condition for car, maybe true on asphalt only

df.to_csv("../26_Accelerated_DAQ/Data_Filtered/{}.csv".format(FILENAME_FILTERED), index=False)

