import argparse
import cv2
from datetime import datetime

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Sistema de Guiado Autonomo y Control de Lazo Cerrado para UAVs en Interiores Industriales"
    )
    
    parser.add_argument(
        "--test", 
        action="store_true", 
        default=False,
        help="Activa el modo de simulacion omitiendo las ordenes fisicas a los motores."
    )
    parser.add_argument(
        "--save-video", 
        action="store_true",
        default=False,
        help="Almacena la sesion de vuelo de forma local con superposiciones graficas."
    )
    parser.add_argument(
        "--calibrate-led", 
        action="store_true", 
        default=False,
        help="Inicializa el protocolo de calibracion cromatica antes del bucle de navegacion."
    )
    parser.add_argument(
        "--timer", 
        action="store_true", 
        default=False,
        help="Imprime analisis de tiempo de las principales tareas del programa al finalizar la ejecucion."
    )
    parser.add_argument(
        "--altitude", 
        type=int, 
        default=60,
        help="Establece la altura de vuelo en centimetros tras el despegue inicial."
    )
    parser.add_argument(
        "--edge-pixels", 
        type=int, 
        default=10,
        help="Define el umbral de pixeles para la delimitacion y filtrado de los bordes."
    )
    parser.add_argument(
        "--calibrate-record", 
        type=int, 
        default=3,
        help="Tiempo de grabacion en segundos por color para la calibracion cromatica."
    )
    parser.add_argument(
        "--calibrate-pause", 
        type=int, 
        default=3,
        help="Tiempo de pausa en segundos entre colores para la calibracion cromatica."
    )
    
    return parser.parse_args()

args = parse_arguments()

FRAME_WIDTH = 640
FRAME_HEIGHT = 480
ALTITUDE_TARGET = args.altitude
EDGE_PIXELS = args.edge_pixels
TEST = args.test
SAVE_VIDEO = args.save_video
CALIBRATE_LED = args.calibrate_led
PRINT_TIMES = args.timer
RECORD_TIME_CAL_LED = args.calibrate_record
PAUSE_TIME_CAL_LED = args.calibrate_pause
COLOR_NAMES = ["pink", "blue", "cyan", "green", "orange", "red"]
WIFI_SSID = ''
WIFI_PASS = ''

time_led        = []
time_preprocess = []
time_aruco      = []
time_binarize   = []
time_solidity   = []
time_edges      = []
time_angle      = []
time_roll       = []
time_save_img   = []
loop_times      = []

DEFAULT_BOUNDARIES = {
    'red_orange': 11,
    'orange_green': 50,
    'green_cyan': 85,
    'cyan_blue': 100,
    'blue_pink': 130,
    'pink_red': 170,
}

def get_video_writer():
    if not SAVE_VIDEO:
        return None
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    filename = f'tello_{datetime.now().strftime("%d_%B_%Y-%H.%M.%S")}.avi'
    return cv2.VideoWriter(filename, fourcc, 30.0, (FRAME_WIDTH, FRAME_HEIGHT))
