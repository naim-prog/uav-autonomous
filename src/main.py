import time
import sys
import keyboard
import numpy as np
from djitellopy import Tello
import cv2

import config
import vision
import control
import conection

key_states = {'w': False, 's': False, 'a': False, 'd': False, 'q': False, 'e': False}
paused_manual = False
should_land = False
toggle_pause_flag = False

def on_global_key_event(event):
    """
    Callback global para gestionar todos los eventos de teclado.
    - 'k': Activa la bandera de aterrizaje.
    - 'p': Activa la bandera para pausar/reanudar.
    - WASDQE: Gestiona el estado para el control manual.
        - 'w': Mueve el dron hacia delante
        - 's': Mueve el dron hacia detras
        - 'a': Mueve el dron hacia la izquierda
        - 'd': Mueve el dron hacia la derecha
        - 'q': Gira el dron en sentido antihorario
        - 'e': Gira el dron en sentido horario
    """
    global key_states, paused_manual, should_land, toggle_pause_flag
    
    key_name = event.name.lower()

    # Teclas de aterrizar o para dron
    if event.event_type == keyboard.KEY_DOWN:
        if key_name == 'k':
            should_land = True
        elif key_name == 'p':
            toggle_pause_flag = True

    # Teclas de control manual (solo en pausa)
    if paused_manual:
        if key_name in key_states:
            key_states[key_name] = (event.event_type == keyboard.KEY_DOWN)

try:
    keyboard.hook(on_global_key_event)
except Exception as e:
    print(f"[ERROR] - Fallo al registrar hook de teclado: {e}")
    print("\tPuede que necesites ejecutar como superusuario (sudo) en Linux.")
    print("\tContinuando sin control de teclado...")

def main():
    global paused_manual, should_land, toggle_pause_flag
    
    try:
        conection.connect_to_wifi(config.WIFI_SSID, config.WIFI_PASS)
    except Exception:
        pass

    tello = Tello()
    try:
        tello.connect(wait_for_state=True)
        tello.send_command_with_return("command")
        tello.send_rc_control(0, 0, 0, 0)
        print("Tello conectado en modo SDK.")
    except Exception:
        print("Error conectando con Tello. Finalizando ejecucion del programa")
        sys.exit(1)

    print(f"Bateria actual: {tello.get_battery()}%")

    try:
        tello.streamon()
        frame_read = tello.get_frame_read()
        start_time_stream = time.time()
        while frame_read.frame is None and (time.time() - start_time_stream) < 10:
            time.sleep(0.05)
        if frame_read.frame is None:
            print("[ERROR] - No se recibio correctamente el primer frame. Finalizando ejecucion del programa.")
            tello.land()
            sys.exit(1)
        print("[INFO] - Stream de video correctamente iniciado.")
    except Exception as e:
        print(f"[ERROR] - Error iniciando el stream: {e}")
        tello.land()
        sys.exit(1)

    if not config.TEST:
        if not control.safe_takeoff(tello, target_height_cm=config.ALTITUDE_TARGET):
            print("[ERROR] - Fallo en el despegue. Finalizando ejecucion del programa.")
            tello.streamoff()
            sys.exit(1)

    video_writer = config.get_video_writer()
    boundaries_colors = config.DEFAULT_BOUNDARIES
    if config.CALIBRATE_LED:
        try: boundaries_colors = vision.calibrate_colors(frame_read, tello)
        except Exception as e:
            print("[ERROR] - Fallo en la calibracion de fronteras, utilizando las fronteras por defecto")
            print(e.with_traceback())
            boundaries_colors = config.DEFAULT_BOUNDARIES

    frame = np.ndarray([])
    previous_frame = np.ndarray([])
    previous_angle_point = (config.EDGE_PIXELS // 2, config.FRAME_WIDTH // 2)
    current_selected_angle  = 0
    current_selected_roll   = 0
    pref_bifurcacion = 'right'

    try:
        while not should_land:
            if toggle_pause_flag:
                paused_manual = not paused_manual
                control.reset_pids()

                for k in key_states: key_states[k] = False
                
                if not config.TEST: tello.send_rc_control(0, 0, 0, 0)

                if paused_manual: print("PAUSADO para control manual. Use WASDQE. Presione 'p' para reanudar seguimiento.")
                else: print("REANUDANDO seguimiento de linea.")
                
                toggle_pause_flag = False

            frame = frame_read.frame

            if frame is None:
                time.sleep(0.001)
                continue

            # Evitamos una sobrecorrecion o infracorreccion al procesar frames iguales
            while vision.equal_images(previous_frame, frame):
                # Retardo de 1ms para no saturar la CPU
                time.sleep(0.001)
                frame = frame_read.frame

            previous_frame = frame

            start_time = time.time_ns()

            show_image, lista_type_and_cuts, color_led, aruco_ids = vision.process_frame(frame, boundaries_colors)

            if paused_manual:
                manual_pitch = 0
                if key_states['w']: manual_pitch = 30
                elif key_states['s']: manual_pitch = -30

                manual_roll = 0
                if key_states['a']: manual_roll = -30
                elif key_states['d']: manual_roll = 30

                manual_yaw = 0
                if key_states['q']: manual_yaw = -30
                elif key_states['e']: manual_yaw = 30

                current_manual_command_active = any([
                    key_states['w'], key_states['s'], key_states['a'],
                    key_states['d'], key_states['q'], key_states['e']
                ])

                if not config.TEST:
                    tello.send_rc_control(manual_roll, manual_pitch, 0, manual_yaw)
                else:
                    if current_manual_command_active: print(f"[TEST] - Manual RC: R={manual_roll}, P={manual_pitch}, T=0, Y={manual_yaw}")
            else:

                f_yaw         = 0
                f_roll        = 0
                selected_pair = ()
                index_figure  = None
                speed         = None
                speed_inv     = False

                if color_led == 'None': pass
                elif color_led == 'red': speed = 0
                elif color_led == 'green': pref_bifurcacion = 'left'
                elif color_led == 'blue': pref_bifurcacion = 'right'
                elif color_led == 'pink': should_land = True
                elif color_led == 'orange': speed_inv = True
                elif color_led == 'cyan':
                    tello.rotate_clockwise(180)
                    # limpiar la cola para evitar giros duplicados
                    vision.queue_led.clear()

                if aruco_ids != []:
                    aruco_ids = sorted(aruco_ids, reverse=False)
                    # Solo tenemos en cuenta el primero en caso de haber varios (prioridad inversa)
                    if aruco_ids[0] == 0: should_land = True
                    elif aruco_ids[0] == 1: speed = 0
                    elif aruco_ids[0] == 2:
                        tello.rotate_clockwise(180)
                        vision.queue_led.clear()


                if lista_type_and_cuts:
                    start = time.time_ns()
                    current_selected_angle, selected_pair, index_figure = vision.select_angle(lista_type_and_cuts, previous_angle_point, pref_bifurcacion)
                    end = time.time_ns()
                    config.time_angle.append(end-start)

                    if current_selected_angle is not None:
                        f_yaw = int(-control.pid_yaw(current_selected_angle))
                        previous_angle_point = selected_pair[1]
                        if config.SAVE_VIDEO: cv2.circle(show_image, (int(selected_pair[1][1]), int(selected_pair[1][0])), 5, (255, 0, 0), -1)
                else:
                    control.pid_yaw.reset()

                start = time.time_ns()
                current_selected_roll, show_image = vision.calculate_lateral_roll(
                    show_image,
                    selected_pair,
                    tello.get_distance_tof()
                )
                end = time.time_ns()
                config.time_roll.append(end-start)

                if current_selected_roll is not None:
                    f_roll = int(-control.pid_roll(current_selected_roll))
                else:
                    control.pid_roll.reset()

                if current_selected_angle is not None or current_selected_roll is not None:
                    if speed is None:
                        try: speed = control.get_speed(lista_type_and_cuts[index_figure][0], f_yaw, f_roll)
                        except (IndexError, TypeError): speed = 0
                    
                    f_yaw  = f_yaw if f_yaw != None else 0
                    f_roll = f_roll if f_roll != None else 0
                    if not config.TEST:
                        speed = -speed if speed_inv else speed
                        tello.send_rc_control(f_roll, speed, 0, f_yaw)
                else:
                    control.reset_pids()
                    if not config.TEST: tello.send_rc_control(0, 0, 0, 0)

            if config.SAVE_VIDEO and video_writer:
                start = time.time_ns()
                video_writer.write(show_image)
                end = time.time_ns()
                config.time_save_img.append(end-start)

            end_time = time.time_ns()
            config.loop_times.append(end_time-start_time)

    except KeyboardInterrupt:
        print("[INFO] - Interrupcion por teclado detectada. Aterrizando dron.")
    except Exception as e:
        print(e.with_traceback())
    finally:
        print("[INFO] - Finalizando ejecucion del programa")
        if config.PRINT_TIMES:
            print(f"[TIEMPO] - Deteccion LED: -> AVG: {np.mean(config.time_led)/1e6:.2f}ms | MAX: {np.max(config.time_led)/1e6:.2f}ms. | MIN: {np.min(config.time_led)/1e6:.2f}ms | STD: {np.std(config.time_led)/1e6:.2f}ms.")
            print(f"[TIEMPO] - Preprocesado: -> AVG: {np.mean(config.time_preprocess)/1e6:.2f}ms | MAX: {np.max(config.time_preprocess)/1e6:.2f}ms. | MIN: {np.min(config.time_preprocess)/1e6:.2f}ms | STD: {np.std(config.time_preprocess)/1e6:.2f}ms.")
            print(f"[TIEMPO] - Binarizacion: -> AVG: {np.mean(config.time_binarize)/1e6:.2f}ms | MAX: {np.max(config.time_binarize)/1e6:.2f}ms. | MIN: {np.min(config.time_binarize)/1e6:.2f}ms | STD: {np.std(config.time_binarize)/1e6:.2f}ms.")
            print(f"[TIEMPO] - Indice de solidez: -> AVG: {np.mean(config.time_solidity)/1e6:.2f}ms | MAX: {np.max(config.time_solidity)/1e6:.2f}ms. | MIN: {np.min(config.time_solidity)/1e6:.2f}ms | STD: {np.std(config.time_solidity)/1e6:.2f}ms.")
            print(f"[TIEMPO] - Corte en los bordes: -> AVG: {np.mean(config.time_edges)/1e6:.2f}ms | MAX: {np.max(config.time_edges)/1e6:.2f}ms. | MIN: {np.min(config.time_edges)/1e6:.2f}ms | STD: {np.std(config.time_edges)/1e6:.2f}ms.")
            print(f"[TIEMPO] - Calculo de angulo de giro: -> AVG: {np.mean(config.time_angle)/1e6:.2f}ms | MAX: {np.max(config.time_angle)/1e6:.2f}ms. | MIN: {np.min(config.time_angle)/1e6:.2f}ms | STD: {np.std(config.time_angle)/1e6:.2f}ms.")
            print(f"[TIEMPO] - Calculo desplazamiento lateral: -> AVG: {np.mean(config.time_roll)/1e6:.2f}ms | MAX: {np.max(config.time_roll)/1e6:.2f}ms. | MIN: {np.min(config.time_roll)/1e6:.2f}ms | STD: {np.std(config.time_roll)/1e6:.2f}ms.")
            if config.SAVE_VIDEO: print(f"[TIEMPO] - Guardado de imagen: -> AVG: {np.mean(config.time_save_img)/1e6:.2f}ms | MAX: {np.max(config.time_save_img)/1e6:.2f}ms. | MIN: {np.min(config.time_save_img)/1e6:.2f}ms | STD: {np.std(config.time_save_img)/1e6:.2f}ms.")
            print(f"[TIEMPO] - General: -> AVG: {np.mean(config.loop_times)/1e6:.2f}ms | MAX: {np.max(config.loop_times)/1e6:.2f}ms. | MIN: {np.min(config.loop_times)/1e6:.2f}ms | STD: {np.std(config.loop_times)/1e6:.2f}ms.")
        
        keyboard.unhook_all()
        if video_writer: video_writer.release()
        if not config.TEST:
            tello.send_rc_control(0, 0, 0, 0)
            tello.land()
            tello.streamoff()

if __name__ == "__main__":
    main()
