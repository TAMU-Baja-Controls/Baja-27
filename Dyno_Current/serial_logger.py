"""Dyno serial logger. Requires: pip install pyserial

Reads the Arduino's CSV stream, takes the header from the board itself,
and writes one row at RATE_HZ into OUT_DIR. Ctrl+C to stop.
"""

import csv
import os
import time
from datetime import datetime

import serial

# ---- settings ----------------------------------------------------------
PORT    = "COM5"    # Windows: COM3 etc.  Mac/Linux: /dev/tty.usbmodem... or /dev/ttyACM0
BAUD    = 115200
RATE_HZ = 50        # rows per second written to the CSV (max 50, see note)
OUT_DIR = "logs_day1"    # folder created next to this script
# ------------------------------------------------------------------------

here = os.path.dirname(os.path.abspath(__file__))
out_dir = os.path.join(here, OUT_DIR)
os.makedirs(out_dir, exist_ok=True)
path = os.path.join(out_dir, datetime.now().strftime("run_%Y%m%d_%H%M%S.csv"))

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2.0)              # board may reset when the port opens
ser.reset_input_buffer()
ser.write(b"\n")             # ask the board to resend its header

headers = None
while headers is None:
    line = ser.readline().decode(errors="ignore").strip()
    if line.startswith("#"):
        headers = line[1:].split(",")

interval = (1.0 / RATE_HZ)
next_write = time.monotonic()
latest = None
t0 = None

with open(path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    print(f"Logging {len(headers)} columns to {path} at {RATE_HZ} Hz. Ctrl+C to stop.")

    try:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if line and not line.startswith("#"):
                fields = line.split(",")
                if len(fields) == len(headers):
                    latest = fields

            now = time.monotonic()
            if latest and now >= next_write:
                if t0 is None:
                    t0 = int(latest[0])

                shifted_latest = [int(latest[0]) - t0] + latest[1:]
                writer.writerow(shifted_latest)
                f.flush()
                print(shifted_latest)
                next_write += interval
                if next_write < now:     # fell behind, resync
                    next_write = now + interval

    except KeyboardInterrupt:
        pass

ser.close()
print(f"\nSaved {path}")
