import pandas as pd
import numpy as np
from scipy.integrate import cumulative_trapezoid

INPUT_DIRECTORY = "raw_logs"
OUTPUT_DIRECTORY = "processed_logs"
FILENAME = "run3"

RATIO_RANGE = [3.55, 0.9]

DISTANCE_TARGET = 200 # ft

# angular to effetive conversion rad to ft
FINAL_DRIVE = 7.26
TIRE_DIAM = 21.0 / 12.0 # ft

def angular_to_effective(angular_column):
    return angular_column / FINAL_DRIVE * (TIRE_DIAM / 2)


# Load CSV into a DataFrame
df = pd.read_csv(f"{INPUT_DIRECTORY}/{FILENAME}.csv")
 
# Assign each column to a variable
time_ms = df["time_ms"]
primary_rpm = df["primary_rpm"]
secondary_rpm = df["secondary_rpm"]
ratio = df["ratio"]
 
df["time_s"] = (time_ms - time_ms[0]) / 1000.0
df["crank_angular_velocity"] = primary_rpm * (2 * np.pi / 60)
df["disk_angular_velocity"] = secondary_rpm * (2 * np.pi / 60)
df["disk_angular_acceleration"] = df['disk_angular_velocity'].rolling(window=5, min_periods=1).mean().diff() / df["time_s"].diff()
df["disk_effective_velocity"] = angular_to_effective(df["disk_angular_velocity"])
df["disk_effective_position"] = cumulative_trapezoid(df["disk_effective_velocity"], df['time_s'], initial=0)
df["ratio_limited"] = ratio.clip(lower=RATIO_RANGE[0], upper=RATIO_RANGE[1])

distance_completion_index = (df['disk_effective_position'] - DISTANCE_TARGET).abs().idxmin()
closest_time = df.loc[distance_completion_index, 'time_s']

print(f"Completed {DISTANCE_TARGET} ft run in: {closest_time}s")
 
# Save the modified DataFrame to a new CSV in another folder
df.to_csv(f"{OUTPUT_DIRECTORY}/{FILENAME}_processed.csv", index=False)