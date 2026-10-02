import matplotlib.pyplot as plt
import numpy as np
import sympy as sp
import pandas as pd
from pathlib import Path

INPUT_FILE_PATH = "Logs/main_loop_log.csv"
OUTPUT_FILE_PATH = "Logs/primary_characterization.csv"

HEADERS = ["crank_speed_rpm", "shift_in", "input_clamp"]
POINTS = 45 # how many timestep datapoints the output has to have

# resolve paths relative to this file so the script works from any working directory
BASE_DIR = Path(__file__).resolve().parent

df = pd.read_csv(BASE_DIR / INPUT_FILE_PATH)

missing = [h for h in HEADERS if h not in df.columns]
if missing:
    raise KeyError(f"Columns {missing} not found in {INPUT_FILE_PATH}. Available: {list(df.columns)}")

df = df[HEADERS]

# take every (rows / POINTS)th row, e.g. 3000 rows & 30 points -> every 100th row
step = max(len(df) // POINTS, 1)
df = df.iloc[::step].head(POINTS)

df.to_csv(BASE_DIR / OUTPUT_FILE_PATH, index=False)
print(f"Saved {len(df)} rows (every {step}th row) to {OUTPUT_FILE_PATH}")

