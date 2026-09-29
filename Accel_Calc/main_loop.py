import numpy as np
from tqdm import tqdm
from mpl_toolkits.mplot3d import Axes3D
from Belt import belt_constants as bc
import general_constants as gc
from Driveline import driveline_constants as dc
from _cvts import gaged, custom
from Belt.geometry_state import GeometryState
from efficiency_helper import BELT_ENGAGEMENT_LOSS

from Crank.Crank import Crank
from Belt.Belt import Belt
from Driveline.Driveline import Driveline
from Dyno.Dyno import Dyno
from Tire.Tire import Tire
from _logger.Logger import Logger

crank = Crank(gc.car.idle_RPM, 0.0, gc.cvt)
belt = Belt(0.0, 0.0, gc.cvt)
driveline = Driveline(0.0, 0.0, gc.cvt)
dyno = Dyno(0.0, 0.0, 0.0, gc.cvt)
tire = Tire(0.0, 0.0, 0.0)

logger = Logger("main_loop_log.csv")

POSITION_TARGET = 148 # ft

dyno_mode: bool = gc.dyno_mode

time: float = 0.0 # seconds
geometry_state: GeometryState = belt.get_geometry_state()

# takes all segments and finds the acceleration of car, angular acceleration of driveline, and angular acceleration of crank if its not engaged
# doesn't model pre-engagement shifting yet
def find_belt_torque_clamp(belt_geometry_state: GeometryState):
    shift_force_delta = 0 # 0 - no shift, positive is upshift, negative is backshift

    engine_torque = crank.primary_torque()
    primary_clamp_force = crank.primary_clamp_force()
    crank_angular_velocity = crank.engine_rpm * (2 * np.pi / 60)  # rad / s

    # need to fix the primaries before I start doing engagement sliding stuff
    if (crank_angular_velocity > (belt.angular_velocity + 0.005)):
        belt_input_torque = belt.primary_sliding_torque(primary_clamp_force, belt_geometry_state)
        engaged = False
    else:
        belt_input_torque = engine_torque  # no sliding, use engine torque directly
        engaged = True

    # highkey this is probably gonna be where shit comes from
    secondary_torque, secondary_clamp_force, belt_slipping = belt.calculate_output_torque_clamp(
        belt_input_torque, 
        primary_clamp_force, 
        belt_geometry_state
    )
    
    secondary_resistive_clamp = dyno.get_resistive_clamp(secondary_torque) if dyno_mode else driveline.get_resistive_clamp(secondary_torque)

    if (secondary_clamp_force < secondary_resistive_clamp) and abs(belt_geometry_state.rad_prim - bc.C.geometry.min_radius_primary) > 0.001:
        shift_force_delta = secondary_clamp_force - secondary_resistive_clamp # negative means backshift
    elif (secondary_clamp_force >= secondary_resistive_clamp) and abs(belt_geometry_state.rad_prim - bc.C.geometry.max_radius_primary) > 0.001:
        shift_force_delta = secondary_clamp_force - secondary_resistive_clamp # positive means upshift
    else:
        shift_force_delta = 0  # no shift

    # first logging point
    logger.logCalculatorStates(time, gc.cvt, shift_force_delta, engaged, belt_slipping)
    logger.logCrankState(engine_torque, crank)
    logger.logBeltGeometry(belt_geometry_state)
    logger.logBeltState(belt, belt_input_torque, secondary_torque, primary_clamp_force, secondary_clamp_force)

    return engine_torque, belt_input_torque, secondary_torque, secondary_resistive_clamp, shift_force_delta, engaged

def find_accelerations_dyno(engine_torque, belt_input_torque, secondary_torque, secondary_resistive_clamp, engaged, belt_geometry_state: GeometryState):

    brake_input_torque = dyno.get_brake_torque(secondary_torque)

    J_dyno = dyno.get_dyno_J()
    J_crank = crank.crank_J(engaged, dyno_mode, belt_geometry_state.ratio)

    if (engaged):
        effective_accel, dyno_angular_accel = dyno.get_dyno_accels(secondary_torque, J_dyno + J_crank)
        crank_accel = 0.0 # needs to be calculated after shift
    else:
        effective_accel, dyno_angular_accel = dyno.get_dyno_accels(secondary_torque, J_dyno)
        crank_accel = (engine_torque - belt_input_torque) / (J_crank / gc.phys.g)  # angular acceleration of just the crank

    logger.logDynoState(dyno, effective_accel, dyno_angular_accel, secondary_resistive_clamp, brake_input_torque)

    return effective_accel, dyno_angular_accel, crank_accel

def find_accelerations_driveline_tire(engine_torque, belt_input_torque, secondary_torque, secondary_resistive_clamp, engaged, belt_geometry_state: GeometryState):

    tire_input_torque = driveline.get_output_torque(secondary_torque)
    # second logging point
    logger.logDrivelineState(driveline, secondary_resistive_clamp, tire_input_torque)
    
    # torque propagation is done -- now the results of the torque

    J_driveline = driveline.get_driveline_J()
    m_eff = driveline.get_effective_mass()
    # if its engaged, then you want it from the wheels perspective
    J_crank = crank.crank_J(engaged, dyno_mode, ratio=belt_geometry_state.ratio)

    if (engaged):
        vehicle_accel, tire_angular_accel, slip_percent, tractive_force_difference = tire.get_transient_accels_friction(tire_input_torque, J_driveline + J_crank, m_eff)
        crank_accel = 0.0 # needs to be calculated after shift
    else:
        vehicle_accel, tire_angular_accel, slip_percent, tractive_force_difference = tire.get_transient_accels_friction(tire_input_torque, J_driveline, m_eff)
        crank_accel = (engine_torque - belt_input_torque * BELT_ENGAGEMENT_LOSS) / (J_crank / gc.phys.g)  # angular acceleration of just the crank

    # third logging point
    logger.logTireState(tire, vehicle_accel, tire_angular_accel, crank_accel, slip_percent, tractive_force_difference)

    return vehicle_accel, tire_angular_accel, crank_accel

def accelerate_driveline(vehicle_accel, tire_angular_accel, timestep):

    tire.angular_velocity += tire_angular_accel * timestep
    tire.vehicle_velocity += vehicle_accel * timestep

    driveline.angular_velocity = tire.angular_velocity * dc.final_drive
    tire.vehicle_position += tire.vehicle_velocity * timestep

def accelerate_belt_and_crank(driveline_angular_velocity, crank_accel, engaged, ratio, timestep):
    # uses the new ratio to accelerate belt and crank if belt shifted
    belt.angular_velocity = driveline_angular_velocity * ratio

    if engaged: # if engaged, crank is matching belt
        crank.engine_rpm = belt.angular_velocity * (60 / (2 * np.pi))  # convert from rad/s to RPM
    else:
        crank.engine_rpm += crank_accel * timestep * (60 / (2 * np.pi)) # velocity integration of just the crank in RPM

print("Initiated Accel Model Successfully.")

pbar = tqdm(total=POSITION_TARGET, unit="ft")
prev_position = 0.0

while (dyno.effective_position if dyno_mode else tire.vehicle_position) < POSITION_TARGET:

    (
        engine_torque,
        belt_input_torque,
        secondary_torque,
        secondary_resistive_clamp,
        shift_force_delta,
        engaged
    ) = find_belt_torque_clamp(geometry_state)

    if dyno_mode:
        (
            effective_accel, 
            dyno_angular_accel, 
            crank_accel
        ) = find_accelerations_dyno(
            engine_torque, 
            belt_input_torque, 
            secondary_torque, 
            secondary_resistive_clamp, 
            engaged, 
            geometry_state
        )

        dyno.angular_velocity += dyno_angular_accel * gc.calc.timestep
        dyno.effective_velocity += effective_accel * gc.calc.timestep
        dyno.effective_position += dyno.effective_velocity * gc.calc.timestep

    else:
        (
            vehicle_accel, 
            tire_angular_accel, 
            crank_accel
        ) = find_accelerations_driveline_tire(
            engine_torque, 
            belt_input_torque, 
            secondary_torque, 
            secondary_resistive_clamp, 
            engaged, 
            geometry_state
        )

        accelerate_driveline(vehicle_accel, tire_angular_accel, gc.calc.timestep)

    logger.saveData()  # save the logged data at each iteration after accelerations are found

    new_position = min((dyno.effective_position if dyno_mode else tire.vehicle_position), POSITION_TARGET)
    pbar.update(new_position - prev_position)
    prev_position = new_position

    geometry_state = belt.shift_from_delta(shift_force_delta, gc.calc.timestep) # shifts belt if it needs to
    crank.shift_in = geometry_state.shift_in

    if dyno_mode:
        dyno.shift_out = geometry_state.shift_out
    else:
        driveline.shift_out = geometry_state.shift_out

    accelerate_belt_and_crank(
        dyno.angular_velocity if dyno_mode else driveline.angular_velocity, 
        crank_accel, 
        engaged, 
        geometry_state.ratio, 
        gc.calc.timestep
    )

    time += gc.calc.timestep  # increment simulation time

pbar.close()

print(f"Completion Time for {POSITION_TARGET} ft: {time:.3f}")