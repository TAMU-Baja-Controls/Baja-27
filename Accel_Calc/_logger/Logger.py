import atexit
import csv
import os

import matplotlib.pyplot as plt
import numpy as np

import Crank.Crank as Crank
import Belt.Belt as Belt
import Dyno.Dyno as Dyno
import Driveline.Driveline as Driveline
import Tire.Tire as Tire
from Belt.geometry_state import GeometryState

class Logger:

    # list of things at beginning of every iteration -- everything pre-shift and pre update
    # Vehicle states: cvt mode, shift state, engaged, slipping, timestep
    # Crank states: engine torque, crank speed RPM
    # Belt Geometry state
    # Belt force states: belt angular velocity, belt input torque, belt output torque, input clamp, output clamp
    # Driveline states: secondary resistive clamp, driveline angular velocity, driveline output torque
    # secondary resistive clamp, driveline angular velocity, driveline output torque
    # tire angular velocity, vehicle velocity, vehicle acceleration
    
    def __init__(self, filename):
        self.data = {}
        self.rows = []          # buffered rows, written to disk once by flush()
        self.filepath = "Logs/" + filename
        self.clearCSV()
        # flush at interpreter shutdown -- covers normal completion, the early
        # break in main_loop, uncaught exceptions and Ctrl-C
        atexit.register(self.flush)

    def logCalculatorStates(self, timestep, cvt_mode, shift_force_delta, engaged, slipping):
        self.data.update({
            'timestep': timestep,
            'cvt_mode': cvt_mode,
            'shift_force_delta': shift_force_delta,
            'engaged': engaged,
            'slipping': slipping
        })

    def logCrankState(self, engine_torque: float, crank: Crank):
        self.data.update({
            'engine_torque': engine_torque,
            'crank_speed_rpm': crank.engine_rpm,
            'crank_angular_velocity': crank.engine_rpm * (2 * np.pi / 60),
            'crank_shift_in': crank.shift_in
        })

    def logBeltGeometry(self, beltGeometryState: GeometryState):
        self.data.update({
            'rad_prim': beltGeometryState.rad_prim,
            'rad_sec': beltGeometryState.rad_sec,
            'shift_in': beltGeometryState.shift_in,
            'shift_out': beltGeometryState.shift_out,
            'wrap_angle_prim': beltGeometryState.wrap_angle_prim,
            'wrap_angle_sec': beltGeometryState.wrap_angle_sec,
            'ratio': beltGeometryState.ratio
        })

    def logBeltState(self, belt: Belt, input_torque: float, output_torque, input_clamp, output_clamp):
        self.data.update({
            'belt_angular_velocity': belt.angular_velocity,
            'belt_input_torque': input_torque,
            'belt_output_torque': output_torque,
            'input_clamp': input_clamp,
            'output_clamp': output_clamp
        })

    def logDynoState(self, dyno: Dyno, effective_accel, dyno_angular_accel, secondary_resistive_clamp, brake_torque):
        self.data.update({
            'secondary_resistive_clamp': secondary_resistive_clamp,
            'dyno_angular_velocity': dyno.angular_velocity,
            'dyno_angular_acceleration': dyno_angular_accel,
            'effective_acceleration': effective_accel,
            'dyno_effective_velocity': dyno.effective_velocity,
            'dyno_effective_position': dyno.effective_position,
            'dyno_shift_out': dyno.shift_out,
            'brake_torque': brake_torque
        })

    def logDrivelineState(self, driveline: Driveline, secondary_resistive_clamp, output_torque):
        self.data.update({
            'secondary_resistive_clamp': secondary_resistive_clamp,
            'driveline_angular_velocity': driveline.angular_velocity,
            'driveline_shift_out': driveline.shift_out,
            'driveline_output_torque': output_torque # the "result" of everything
        })

    def logTireState(self, tire: Tire, vehicle_accel, driveline_angular_accel, crank_accel, slip_percent, tractive_force_difference):
        self.data.update({
            'tire_angular_velocity': tire.angular_velocity,
            'vehicle_velocity': tire.vehicle_velocity,
            'vehicle_position': tire.vehicle_position,
            'vehicle_acceleration': vehicle_accel,
            'driveline_angular_acceleration': driveline_angular_accel,
            'crank_angular_acceleration': crank_accel,
            'slip_percent': slip_percent,
            'tractive_force_difference': tractive_force_difference
        })

    def logBeltForces(self, mu_v_prim, mu_v_sec, centrifugal_prim, centrifugal_sec, min_clamp_prim, multiplier_limit_prim, multiplier_limit_sec, T_taut, T_slack, T_avg, effective_multiplier, transferred_clamp, transferred_torque):
        self.data.update({
            'mu_v_prim': mu_v_prim,
            'mu_v_sec': mu_v_sec,
            'centrifugal_prim': centrifugal_prim,
            'centrifugal_sec': centrifugal_sec,
            'min_clamp_prim': min_clamp_prim,
            'multiplier_limit_prim': multiplier_limit_prim,
            'multiplier_limit_sec': multiplier_limit_sec,
            'T_taut': T_taut,
            'T_slack': T_slack,
            'T_avg': T_avg,
            'effective_multiplier': effective_multiplier,
            'transferred_clamp': transferred_clamp,
            'transferred_torque': transferred_torque
        })

    def saveData(self):
        # Buffer this row in memory instead of touching the disk. Opening the
        # CSV once per iteration cost ~22 ms/call and was ~99% of the sim's
        # runtime; flush() writes everything in one pass at exit.

        # Round all numeric values to 3 decimal places.
        # This also COPIES self.data, which is required -- self.data is a single
        # dict mutated in place by the logXxx methods, so appending it directly
        # would make every buffered row alias the same final-timestep values.
        rounded_data = {}
        for key, value in self.data.items():
            if isinstance(value, float):
                rounded_data[key] = round(value, 4)
            else:
                rounded_data[key] = value

        self.rows.append(rounded_data)

    def flush(self):
        if not self.rows:
            return

        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.filepath)
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)

        # Every row carries the same keys, so the first row defines the header.
        # extrasaction='ignore' keeps a row with an unexpected extra key from
        # raising part-way through the write.
        headers = list(self.rows[0].keys())
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows({h: row.get(h, '') for h in headers} for row in self.rows)

        self.rows.clear()  # a second flush() call must not duplicate the data

    def clearCSV(self):
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.filepath)
        if os.path.exists(csv_path):
            os.remove(csv_path)