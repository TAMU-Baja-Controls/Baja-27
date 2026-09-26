#stores latest values of sensors for the future dashboard display
from config import SENSOR_HISTORY_LIMIT


latest_values = {}
history = {}

def update_data_store(packet):
    sensor = packet["sensor"]

    latest_values[sensor] = packet

    if sensor not in history:
        history[sensor] = []

    history[sensor].append(packet)

    # keep only recent points
    if len(history[sensor]) > SENSOR_HISTORY_LIMIT:
        history[sensor] = history[sensor][-SENSOR_HISTORY_LIMIT:]

def get_latest_values():
    return latest_values

def get_sensor_history(sensor, limit=None):
    if limit is None:
        limit = SENSOR_HISTORY_LIMIT

    return history.get(sensor, [])[-limit:]