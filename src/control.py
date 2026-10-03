import time
import numpy as np
from djitellopy import Tello
from simple_pid import PID

pid_yaw = PID(1.5, 0.0, 0.1, setpoint=0)
pid_yaw.output_limits = (-45, 45)
pid_yaw.integral_limits = (-20, 20)

pid_roll = PID(1.15, 0.0, 0.55, setpoint=0)
pid_roll.output_limits = (-20, 20)
pid_roll.integral_limits = (-10, 10)

def safe_takeoff(
        drone: Tello,
        target_height_cm=60,
        max_attempts=3
    ):
    
    for attempt in range(max_attempts):
        try:
            print(f"[INFO] - Intento de despegue {attempt + 1}/{max_attempts}...")
            drone.takeoff()
            time.sleep(5)

            height = drone.get_distance_tof()
            print(f"[INFO] - Altura ToF: {height} cm")

            diff = target_height_cm - height
            move = max(20, abs(diff))
            drone.move_up(move) if diff > 0 else drone.move_down(move)
            time.sleep(2.5)
            print(f"[INFO] - Altura tras ajuste: {drone.get_distance_tof()} cm")

            return True

        except Exception as e:
            print(f"[ERROR] - Error en despegue: {e}")
            if attempt < max_attempts - 1:
                time.sleep(3)
            else:
                print("[ERROR] - Máximos intentos alcanzados. Aterrizando por seguridad...")
                try:
                    drone.land()
                except Exception as land_e:
                    print(f"Error al aterrizar: {land_e}")
                return False

    return False

def get_speed(
        solidez_linea,
        yaw,
        roll
    ):
    """
    Calcula la velocidad a la que debe ir el dron en funcion de las salidas de ambos
    PID's y de la solidez de la linea que estamos siguiendo
    
    Parameters
    ----------
    solidez_linea:
        Numero decimal [0, 1] indicando la "rectitud" de la linea que sigue el dron
    yaw:
        Salida del PID correspondiente al giro del dron
    roll:
        Salida del PID correspondiente a la desviacion lateral del dron

    Returns
    -------
    speed:
        Velocidad que debera tomar el dron
    """

    min_s = 10
    max_s = 40

    # Si no sabemos que linea seguir, paramos
    if yaw == None or roll == None:
        return 0

    s_sol = np.interp(solidez_linea, [0.8, 0], [max_s, min_s])
    s_yaw = np.interp(abs(yaw), [0, 10], [max_s, min_s])
    s_rol = np.interp(abs(roll), [0, 20], [max_s, min_s])

    return int(np.mean([s_sol, s_yaw, s_yaw, s_rol]))

def reset_pids():
    pid_yaw.reset()
    pid_roll.reset()
