#gets serial data from arduino and returns it as a string to be parsed

import config
import serial
serial_port = serial.Serial(port=config.SERIAL_PORT, baudrate=config.BAUD_RATE, timeout=1)

def get_serial_message(serial_port):
    line = serial_port.readline().decode('utf-8').strip()
    return line