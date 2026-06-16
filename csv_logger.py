#saves every valid reading to a csv file
import csv
import config

def log_to_csv(data, filename=config.CSV_FILENAME):
    with open(filename, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(data.values())

def csv_header(filename=config.CSV_FILENAME):
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['timestamp', 'name', 'value', 'unit', 'status'])