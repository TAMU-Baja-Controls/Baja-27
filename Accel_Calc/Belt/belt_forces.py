import matplotlib.pyplot as plt
import numpy as np
from sympy import symbols, Eq, exp, solve, lambdify, tan, ln
from Belt import belt_constants
from _cvts import gaged, custom
from Belt.geometry_state import GeometryState
from _logger.Logger import Logger

belt_forces_logger = Logger("belt_forces_log.csv")

T_taut, T_slack, T_avg, wrap, radius, torque, mu_v, centrifugal = symbols('T_taut T_slack T_avg wrap radius torque mu_v centrifugal')
clamp_force, groove_angle = symbols('clamp_force groove_angle')
multiplier, max_M, min_F, adjustment_constant = symbols('multiplier max_M min_F adjustment_constant')

# Belt equations
# torque_eq relates the difference in belt tension to the applied torque
# multiplier_limit_eq specifies the multiplier for the capstan equation, which limits the ratio of taut to slack tension
# capstan_eq represents the capstan equation, limiting the ratio of taut to slack tension
# adjusted_multiplier_eq alters the multiplier based on clamp force
# clamp_eq relates the belt tension to the equivalent minimum possible clamp force
torque_eq = Eq((T_taut - T_slack) * (radius / 12), torque) # always true
multiplier_limit_eq = Eq(multiplier, exp(mu_v * wrap)) # this is the capstan limit, the maximum multiplier allowed
capstan_eq = Eq(T_taut - centrifugal, (T_slack - centrifugal) * multiplier) # this is the ratio ceiling
# fudgey multipler adjustment based on how hard belt is being clamped
adjusted_multiplier_eq = Eq(multiplier, 1 + (max_M - 1) * exp(-(adjustment_constant / 1000) * (clamp_force - min_F)))
clamp_eq = Eq(clamp_force, (T_slack - centrifugal) * (multiplier - 1) / (2 * tan(groove_angle / 2) * mu_v))

# updated equations
# relates belt tension to equivalent clamp force
clamp_eq_updated = Eq(clamp_force, (T_avg - centrifugal) * wrap / (2 * tan(groove_angle / 2)))
tensions_eq = Eq(T_avg, (T_taut + T_slack) / 2)

# Solutions of belt equations
capstan_ceiling_solution = solve((torque_eq, capstan_eq), (T_taut, T_slack)) # solves for torque and capstan for the minimum tension scenario
clamp_from_tension = solve(clamp_eq, clamp_force) # solves for clamp force roughly
tension_from_clamp = solve(clamp_eq, T_slack) # reverse of clamp_from_tension

torque_slack_conversion = solve(torque_eq, T_taut)[0] # turns any T_slack into its corresponding T_taut based on torque
torque_from_tension = solve(torque_eq, torque)[0] # gets torque from tension difference * radius

multiplier_limit = solve(multiplier_limit_eq, multiplier)[0] # gets the multiplier limit from the capstan equation

min_clamp_solution = solve((torque_eq, capstan_eq, clamp_eq), (clamp_force, T_taut, T_slack))

T_avg_from_clamp = solve(clamp_eq_updated, T_avg)[0]
clamp_from_T_avg = solve(clamp_eq_updated, clamp_force)[0]

tensions_updated_sol = solve((torque_eq, tensions_eq), (T_taut, T_slack))

# Numeric lambdify functions for quick evaluation
get_T_taut = lambdify((radius, multiplier, torque, centrifugal), capstan_ceiling_solution[T_taut], modules='numpy')
get_T_slack = lambdify((radius, multiplier, torque, centrifugal), capstan_ceiling_solution[T_slack], modules='numpy')
get_clamp_from_tension = lambdify((T_slack, centrifugal, multiplier, mu_v, groove_angle), clamp_from_tension[0], modules='numpy')
get_tension_from_clamp = lambdify((clamp_force, centrifugal, multiplier, mu_v, groove_angle), tension_from_clamp[0], modules='numpy')

get_taut_torque_from_slack = lambdify((radius, T_slack, torque), torque_slack_conversion, modules='numpy')
get_torque_from_tension = lambdify((radius, T_taut, T_slack), torque_from_tension, modules='numpy')

get_multiplier_limit = lambdify((mu_v, wrap), multiplier_limit, modules='numpy')

get_min_clamp = lambdify((radius, multiplier, torque, centrifugal, mu_v, groove_angle), min_clamp_solution[clamp_force], modules='numpy')

get_T_avg = lambdify((clamp_force, groove_angle, wrap, centrifugal), T_avg_from_clamp, modules='numpy')
get_clamp_updated = lambdify((T_avg, groove_angle, wrap, centrifugal), clamp_from_T_avg, modules='numpy')

get_tensions_updated = lambdify((radius, torque, T_avg), (tensions_updated_sol[T_taut], tensions_updated_sol[T_slack]), modules='numpy')

def mu_effective(mu, groove_angle):
    return mu / np.sin(groove_angle / 2)

def solve_for_min_tension(radius, multiplier, torque, centrifugal):
    taut = get_T_taut(radius, multiplier, torque, centrifugal)
    slack = get_T_slack(radius, multiplier, torque, centrifugal)

    return taut, slack
    
def propagate_clamp_forward(input_torque, angular_velocity, primary_clamp, geometry_state: GeometryState, cvt: int):
    groove_angle_prim = 0.0
    groove_angle_sec = 0.0

    if cvt == 0:
        groove_angle_prim = gaged.Primary.groove_angle
        groove_angle_sec = gaged.Secondary.groove_angle
    elif cvt == 1:
        groove_angle_prim = custom.Primary.groove_angle
        groove_angle_sec = custom.Secondary.groove_angle

    mu_v_prim = mu_effective(belt_constants.C.mu, groove_angle_prim)
    mu_v_sec = mu_effective(belt_constants.C.mu, groove_angle_sec)
    
    # C_f = (m * w^2 * r) / wrap --- gives a differentiated force that integrates easily
    centrifugal_prim = (
        (belt_constants.C.belt_mass_per_length * geometry_state.rad_prim * geometry_state.wrap_angle_prim) * # slugs wrapped total
        (angular_velocity ** 2) * # (rad/s)^2
        (geometry_state.rad_prim / 12) # ft
    ) / geometry_state.wrap_angle_prim # gives lbs / rad of belt wrap

    centrifugal_sec = (
        (belt_constants.C.belt_mass_per_length * geometry_state.rad_sec * geometry_state.wrap_angle_sec) * # slugs wrapped total
        ((angular_velocity / geometry_state.ratio) ** 2) * # (rad/s)^2
        (geometry_state.rad_sec / 12) # ft
    ) / geometry_state.wrap_angle_sec # gives lbs / rad of belt wrap

    multiplier_limit_prim = get_multiplier_limit(mu_v_prim, geometry_state.wrap_angle_prim)
    multiplier_limit_sec = get_multiplier_limit(mu_v_sec, geometry_state.wrap_angle_sec)

    min_clamp_prim = get_min_clamp(geometry_state.rad_prim, multiplier_limit_prim, input_torque, centrifugal_prim, mu_v_prim, groove_angle_prim)
    
    slipping = False
    if primary_clamp < min_clamp_prim:
        slipping = True

    T_avg = get_T_avg(primary_clamp, groove_angle_prim, geometry_state.wrap_angle_prim, centrifugal_prim)
    T_taut, T_slack = get_tensions_updated(geometry_state.rad_prim, input_torque, T_avg)

    if (T_slack != 0):
        effective_multiplier = T_taut / T_slack
    else:
        effective_multiplier = 0.0

    secondary_clamp = get_clamp_updated(T_avg, groove_angle_sec, geometry_state.wrap_angle_sec, centrifugal_sec)
    torque_secondary = get_torque_from_tension(geometry_state.rad_sec, T_taut, T_slack)

    belt_forces_logger.logBeltForces(mu_v_prim, mu_v_sec, centrifugal_prim, centrifugal_sec, min_clamp_prim, multiplier_limit_prim, multiplier_limit_sec, T_taut, T_slack, T_avg, effective_multiplier, secondary_clamp, torque_secondary)
    belt_forces_logger.saveData()

    return secondary_clamp, torque_secondary, slipping

def test_updated_equations():
    clamp_forces = np.linspace(0, 500, 50)
    secondary_clamps = []
    for clamp_force in clamp_forces:
        T_avg = get_T_avg(clamp_force, gaged.Primary.groove_angle, 2.53, 0)
        sec_clamp = get_clamp_updated(T_avg, gaged.Secondary.groove_angle, 3.753, 0)
        secondary_clamps.append(sec_clamp)

    plt.plot(clamp_forces, secondary_clamps, marker='o')
    plt.xlabel('Clamp force')
    plt.ylabel('Secondary clamp')
    plt.title('Clamp force vs. secondary clamp')
    plt.grid(True)
    plt.show()

        
