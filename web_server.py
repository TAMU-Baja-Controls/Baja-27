from fastapi import FastAPI
import threading
import serial_reader
import csv_logger
import config
import parser
import data_store
from fastapi.staticfiles import StaticFiles


app = FastAPI()

def serial_loop():
    csv_logger.csv_header()

    while True:
        line = serial_reader.get_serial_message(serial_reader.serial_port)
        data = parser.parse_packet(line)

        if data is not None:
            csv_logger.log_to_csv(data, config.CSV_FILENAME)
            data_store.update_data_store(data)

@app.on_event("startup")
def start_serial_thread():
    thread = threading.Thread(target=serial_loop, daemon=True)
    thread.start()

@app.get("/latest")
def latest():
    return data_store.get_latest_values()

@app.get("/history/{sensor}")
def get_sensor_history(sensor: str, limit: int = config.SENSOR_HISTORY_LIMIT):
    history = data_store.get_sensor_history(sensor, limit)
    return history



app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")