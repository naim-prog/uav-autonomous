import cv2
import numpy as np
import time
from collections import Counter
import config
from djitellopy import Tello 

class LEDColorQueue:
    def __init__(self, max_frames=5):
        self.queue = []
        self.max_frames = max_frames

    def add(self, color: str):
        if len(self.queue) == self.max_frames:
            self.queue.pop(0)
        self.queue.append(color)

    def most_common_color(self) -> str:
        color_count = Counter(reversed(self.queue)).most_common()
        return max(color_count, key=lambda x: x[1])[0]

    def clear(self):
        self.queue = []

queue_led = LEDColorQueue()

def find_gaussian_intersection(m1, s1, m2, s2):
    """
    Encuentra el punto de interseccion entre dos distribuciones gaussianas.
    Utilizamos la aproximacin ponderada por la desviacion estandar, que es 
    rapida para encontrar la frontera de manera robusta.
    
    Formula: x = (m1 * s2 + m2 * s1) / (s1 + s2)
    """
    if s1 + s2 == 0:
        return (m1 + m2) / 2.0
    return (m1 * s2 + m2 * s1) / (s1 + s2)

def calibrate_colors(
        frame_read,
        dron: Tello
    ):
    """
    Calibra las fronteras entre colores dado un tiempo de calibracion y uno de pausa
    para cada uno de los colores disponibles

    Parameters
    ----------
    frame_read:
        BackgroundTask devuelta por la funcion `Tello().get_frame_read()` para poder leer los frames del dron
    dron : Tello
        Objeto de la clase Tello para controlar que el dron no aterrice

    Returns
    -------
    boundaries:
        Umbrales de Hue para cada par de colores LED
    """
    frame = np.ndarray([])
    previous_frame = np.ndarray([])

    color_data = {color: [] for color in config.COLOR_NAMES}
    
    print("=== INICIANDO CALIBRADOR DE COLORES LED ===")
    
    for color in config.COLOR_NAMES:
        # Para que el dron no aterrice (si no le envías un comando cada 15 segundos aterriza solo)
        dron.send_rc_control(0, 0, 0, 0)

        print(f"[PAUSA] - Cambia el LED al color: {color.upper()}")
        start_pause = time.time()
        while time.time() - start_pause < config.PAUSE_TIME_CAL_LED:
            frame = frame_read.frame
            time.sleep(0.033)            

        dron.send_rc_control(0, 0, 0, 0)

        print(f"[GRABANDO] - Extrayendo datos Hue de {color.upper()}\n")
        start_record = time.time()
        while time.time() - start_record < config.RECORD_TIME_CAL_LED:
            frame = frame_read.frame
            
            # Si el frame es nulo o el mismo no detectes nada, espera al siguiente
            if frame is None or equal_images(frame, previous_frame):
                time.sleep(0.001)
                continue

            previous_frame = frame

            # Extraer solo los pixeles brillantes/saturados
            hsv_image = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h_ch, s_ch, v_ch = cv2.split(hsv_image)
            b_mask = ((v_ch > 190) & (s_ch > 30)).view(np.uint8) * 255
            h_pixels = h_ch[b_mask == 255]
            if len(h_pixels) > 0:
                # Guardar muestras para estadistica
                color_data[color].extend(h_pixels.tolist())


    stats = {}
    for color in config.COLOR_NAMES:
        data = np.array(color_data[color])
        if len(data) == 0:
            print(f"[ERROR] - No se detecto luz para {color}. Usando fronteras por defecto.")
            return config.DEFAULT_BOUNDARIES

        if color == "red":
            data = np.where(data > 90, data - 180, data)
            
        mu = np.mean(data)
        std = np.std(data)
        stats[color] = {'mu': mu, 'std': std}

    boundaries = {}

    # Rojo - Naranja
    boundaries['red_orange'] = find_gaussian_intersection(
        stats['red']['mu'], stats['red']['std'], 
        stats['orange']['mu'], stats['orange']['std'])
    
    # Naranja - Verde
    boundaries['orange_green'] = find_gaussian_intersection(
        stats['orange']['mu'], stats['orange']['std'], 
        stats['green']['mu'], stats['green']['std'])
    
    # Verde - Cyan
    boundaries['green_cyan'] = find_gaussian_intersection(
        stats['green']['mu'], stats['green']['std'], 
        stats['cyan']['mu'], stats['cyan']['std'])
    
    # Cyan - Azul
    boundaries['cyan_blue'] = find_gaussian_intersection(
        stats['cyan']['mu'], stats['cyan']['std'], 
        stats['blue']['mu'], stats['blue']['std'])
    
    # Azul - Rosa
    boundaries['blue_pink'] = find_gaussian_intersection(
        stats['blue']['mu'], stats['blue']['std'], 
        stats['pink']['mu'], stats['pink']['std'])
    
    # Rosa - Rojo
    # Sumamos 180 al rojo por la circularidad del Hue en el caso del color rojo
    boundaries['pink_red'] = find_gaussian_intersection(
        stats['pink']['mu'], stats['pink']['std'], 
        stats['red']['mu'] + 180, stats['red']['std'])

    print("\n=== UMBRALES GENERADOS ===")
    
    # Convertimos a enteros entre 0 y 180
    b = {k: int(np.clip(v, 0, 180)) for k, v in boundaries.items()}
    
    print(f"[Rojo - Naranja]  = {b['red_orange']}")
    print(f"[Naranja - Verde] = {b['orange_green']}")
    print(f"[Verde - Cian]    = {b['green_cyan']}")
    print(f"[Cian - Azul]     = {b['cyan_blue']}")
    print(f"[Azul - Rosa]     = {b['blue_pink']}")
    print(f"[Rosa - Rojo]     = {b['pink_red']}")

    return b

def get_led_color(
        frame,
        boundaries_colors,
    ):
    """
    Devuelve el color de la tira LED dado un frame y las fronteras de decision cromatica.

    Parameters
    ----------
    frame:
        Frame original sacado del dron
    boundaries_colors:
        Fronteras de valor Hue entre los colores seleccionados

    Returns
    -------
    most_ocurrent_led : str
        Color de la tira LED devuelta por la clase LEDColorQueue()
    """

    img_h, img_w = frame.shape[:2]
    hsv_image = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = cv2.split(hsv_image)

    b_mask = ((v_ch > 190) & (s_ch > 30)).view(np.uint8) * 255

    contours, _ = cv2.findContours(b_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    led_colors = []

    for contour in contours:
        if cv2.contourArea(contour) <= 20:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img_w, x + w)
        y2 = min(img_h, y + h)

        h_pixels = h_ch[y1:y2, x1:x2].ravel()

        if len(h_pixels) == 0:
            continue

        bc = np.bincount(h_pixels, minlength=180)

        all_counts = np.array([
            bc[boundaries_colors['blue_pink']:boundaries_colors['pink_red']].sum(),                # pink
            bc[boundaries_colors['cyan_blue']:boundaries_colors['blue_pink']].sum(),               # blue
            bc[boundaries_colors['green_cyan']:boundaries_colors['cyan_blue']].sum(),              # cyan
            bc[boundaries_colors['orange_green']:boundaries_colors['green_cyan']].sum(),           # green
            bc[boundaries_colors['red_orange']:boundaries_colors['orange_green']].sum(),           # orange
            bc[:boundaries_colors['red_orange']].sum() + bc[boundaries_colors['pink_red']:].sum(), # red
        ])

        color_name = config.COLOR_NAMES[np.argmax(all_counts)]

        if all_counts.max() == 0:
            color_name = 'None'

        led_colors.append(color_name)

    most_ocurrent_led = max(led_colors, key=led_colors.count) if led_colors else "None"
    queue_led.add(most_ocurrent_led)

    return queue_led.most_common_color()

def aruco_markers(
        frame, 
    ):
    """
    Detecta marcadores ArUco en un frame dado.

    Parameters
    ----------
    frame:
        Imagen donde queremos buscar los marcadores.

    Returns
    -------
    frame_dibujado:
        El frame original con los marcadores detectados resaltados.
    marcadores_detectados:
        Lista con los ID's de los marcadores encontrados.
    """

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    esquinas, ids, rechazados = detector.detectMarkers(gray)

    ids_ret = []

    if ids is not None:
        if config.SAVE_VIDEO: cv2.aruco.drawDetectedMarkers(frame, esquinas, ids)
        ids_ret = list(ids.flatten())

    return frame, ids_ret

def binarize_frame(
        frame,
        adaptive_block_size=101,
        adaptive_c_value=35,
        morph_open_kernel_size=3,
        morph_open_iterations=1,
        morph_close_kernel_size=9,
        morph_close_iterations=1,
        min_contour_area=1500
    ):
    """
    Procesa un frame para binarizarlo, eliminando ruido y resaltando la linea.

    Parameters
    ----------
    frame:
        Frame capturado por el dron.
    adaptive_block_size:
        Tamano utilizado para la binarización adaptativa.
    adaptive_c_value:
        Constante utilizada para la binarización adaptativa.
    morph_open_kernel_size:
        Tamano del kernel para apertura.
    morph_open_iterations:
        Número de iteraciones para la operación de apertura.
    morph_close_kernel_size:
        Tamano del kernel para cierre.
    morph_close_iterations:
        Número de iteraciones para la operación de cierre.
    min_contour_area:
        Area minima necesaria para considerarse valido una figura.

    Returns
    -------
    binary_images : (list)
        Lista de imagenes binarias con valores 0 y 255 cada una.
    """

    if frame is None:
        h, w = config.FRAME_HEIGHT, config.FRAME_WIDTH
        return np.zeros((h, w), dtype=np.uint8)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    binary_image = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        adaptive_block_size,
        adaptive_c_value
    )

    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_open_kernel_size, morph_open_kernel_size))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_close_kernel_size, morph_close_kernel_size))
    
    opened_image = cv2.morphologyEx(
        binary_image,
        cv2.MORPH_OPEN,
        kernel_open,
        iterations=morph_open_iterations
    )
    
    closed_image = cv2.morphologyEx(
        opened_image,
        cv2.MORPH_CLOSE,
        kernel_close,
        iterations=morph_close_iterations
    )

    contours, _ = cv2.findContours(closed_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filtrar contornos validos
    final_masks = []
    valid_contours = []
    if contours:
        valid_contours = [cnt for cnt in contours if cv2.contourArea(cnt) >= min_contour_area]

        for id, valid_contour in enumerate(valid_contours):
            final_masks.append(
                cv2.drawContours(np.zeros_like(gray), valid_contours, id, 255, thickness=cv2.FILLED)
            )

    return final_masks

def solidity_index(
        binary_image,
    ):
    """
    Calcula el indice de solidez de una imagen binaria

    Parameters
    ----------
    binary_image:
        Imagen binaria con valores 0 y 255.

    Returns
    -------
    solidity : float
        Solidez entre 0 y 1. Siendo 1 una recta perfecta
    """

    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return 0.0

    main_contour = max(contours, key=cv2.contourArea)

    # Area normal
    area_contour = cv2.contourArea(main_contour)

    # Area del casco convexo
    hull = cv2.convexHull(main_contour)
    area_hull = cv2.contourArea(hull)

    # Evitar division por cero
    if area_hull == 0:
        return 0.0

    solidity = area_contour / area_hull

    return solidity

def get_pixel_distance(
        point_1,
        point_2
    ):
    """
    Calcula la distancia euclidea entre dos puntos.

    Parameters
    ----------
    point_1 : tuple
        Primer punto.
    point_2 : tuple
        Segundo punto

    Returns
    -------
    int :
        Distancia en pixeles.
    """
    return np.sqrt(np.pow(point_1[0]-point_2[0], 2) + np.pow(point_1[1]-point_2[1], 2))

def angle_from_centre(
        list_cuts: list
    ):
    """
    Convierte los puntos de corte en los bordes a una lista de objetos
    que contienen el angulo desde el centro del frame, borde donde corta
    y coordenadas del punto.

    Parameters
    ----------
    list_cuts : list
        Lista de cortes [top, left, right, bot].

    Returns
    -------
    list_angle_objects:
        Una lista de diccionarios, cada uno representando un punto de corte.

    >>> [{'angle': 175.0, 'type': 'top', 'point': (50, 4), 'original_list_index': 0}]
    """

    list_middle_line_median_top   = list_cuts[0]
    list_middle_line_median_left  = list_cuts[1]
    list_middle_line_median_right = list_cuts[2]
    list_middle_line_median_bot   = list_cuts[3]

    h, w = config.FRAME_HEIGHT, config.FRAME_WIDTH
    mid_x, mid_y = w // 2, h // 2
    
    angle_objects = []

    # ---- Parte superior ----
    for i, top_pixel_cut in enumerate(list_middle_line_median_top):
        lado_opuesto = top_pixel_cut[1] - mid_x
        lado_contiguo = mid_y
        angle_objects.append({
            'angle': np.degrees(np.arctan2(lado_opuesto, lado_contiguo)),
            'type': 'top',
            'point': top_pixel_cut,
            'original_list_index': i
        })

    # ---- Parte izquierda ----
    for i, left_pixel_cut in enumerate(list_middle_line_median_left):
        lado_opuesto = mid_x
        lado_contiguo = mid_y - left_pixel_cut[0]
        angle_objects.append({
            'angle': -np.degrees(np.arctan2(lado_opuesto, lado_contiguo if lado_contiguo != 0 else 1)),
            'type': 'left',
            'point': left_pixel_cut,
            'original_list_index': i
        })

    # ---- Parte derecha ----
    for i, right_pixel_cut in enumerate(list_middle_line_median_right):
        lado_opuesto = mid_x
        lado_contiguo = mid_y - right_pixel_cut[0]
        angle_objects.append({
            'angle': np.degrees(np.arctan2(lado_opuesto, lado_contiguo if lado_contiguo != 0 else 1)),
            'type': 'right',
            'point': right_pixel_cut,
            'original_list_index': i
        })

    # ---- Parte inferior ----
    for i, bot_pixel_cut in enumerate(list_middle_line_median_bot):
        lado_opuesto = bot_pixel_cut[1] - mid_x
        lado_contiguo = -mid_y
        grados = np.degrees(np.arctan2(lado_opuesto, lado_contiguo))
        angle_objects.append({
            'angle': grados,
            'type': 'bot',
            'point': bot_pixel_cut,
            'original_list_index': i
        })

    return angle_objects

def clean_cuts(
        list_cuts: list
    ):
    """
    Recibe la lista de tipo y cortes de una figura y la limpia, eliminando las
    esquinas que puedan tener dos cortes.

    Parameters
    ----------
    list_types:
        Lista con tipo de figura y cortes en los bordes.

    Returns
    -------
    list_types:
        Lista con los cortes desduplicados.
    """

    angle_objects = angle_from_centre(list_cuts)

    if len(angle_objects) <= 1:
        return list_cuts

    angle_objects.sort(key=lambda x: x['angle'])

    cleaned_objects = []

    skip_next = False
    for i in range(len(angle_objects)):
        if skip_next:
            skip_next = False
            continue

        current_obj = angle_objects[i]

        if i + 1 < len(angle_objects):
            next_obj = angle_objects[i + 1]
            diff = abs(next_obj['angle'] - current_obj['angle'])

            # saltamos el siguiente corte si se encuentra muy cerca del actual
            if diff < 5.0:
                cleaned_objects.append(current_obj)
                skip_next = True
                continue

        cleaned_objects.append(current_obj)

    # Reconstruir la lista de cortes original
    new_list_cuts = [[] for _ in range(4)]
    for obj in cleaned_objects:
        point = obj['point']
        if obj['type'] == 'top':
            new_list_cuts[0].append(point)
        elif obj['type'] == 'left':
            new_list_cuts[1].append(point)
        elif obj['type'] == 'right':
            new_list_cuts[2].append(point)
        elif obj['type'] == 'bot':
            new_list_cuts[3].append(point)

    return new_list_cuts

def get_edge_cuts(
        binary_image,
    ):
    """
    Calculo de los cortes en los bordes a partir de una imagen binarizada.

    Parameters
    ----------
    binary_image:
        Imagen binaria con valores 0 y 255.

    Returns
    -------
    lista_cortes : list
        Lista con los cortes de la siguiente manera [arriba, izquierda, derecha, abajo, posicion_dron]
    """

    h, w = binary_image.shape
    dron_pos = h - 133

    top_slice    = binary_image[0:config.EDGE_PIXELS, :]
    bot_slice    = binary_image[h - config.EDGE_PIXELS:h, :]
    left_slice   = binary_image[:, 0:config.EDGE_PIXELS]
    right_slice  = binary_image[:, w - config.EDGE_PIXELS:w]
    middle_slice = binary_image[dron_pos-config.EDGE_PIXELS//2:dron_pos+config.EDGE_PIXELS//2, :]

    # Los ultimos y primeros pixeles los ponemos a 0 puesto que pueden dar fallo los
    # bordes a la hora de detectar lineas en las esquinas con la funcion np.diff()
    top_slice[:, [0, -1]]   = 0
    bot_slice[:, [0, -1]]   = 0
    left_slice[[0, -1], :]  = 0
    right_slice[[0, -1], :] = 0
    middle_slice[:, [0, -1]]   = 0

    # ---- Parte superior ----
    diff_slice = np.diff(top_slice)
    points_top = np.where(diff_slice > 0)

    list_middle_line = [[] for _ in range(config.EDGE_PIXELS)]
    list_cuts   = points_top[0]
    list_pixels = points_top[1]
    for cut, pixel in zip(list_cuts, list_pixels):
        list_middle_line[cut].append(pixel)

    if any(list_middle_line):
        # Contar frecuencia de cada longitud (solo considerar pares para el reshape)
        longitudes = [len(lst) for lst in list_middle_line]
        longitudes_pares = [l for l in longitudes if l > 0 and l % 2 == 0]

        # Encontrar la longitud par mas comun
        if longitudes_pares:
            counter = Counter(longitudes_pares)
            longitud_mas_comun = counter.most_common(1)[0][0]

            # Filtrar para quedarnos solo con las listas que tienen la longitud mas comun
            list_middle_line_filtrada = [lst for lst in list_middle_line if len(lst) == longitud_mas_comun]
        else:
            list_middle_line_filtrada = []
    else:
        list_middle_line_filtrada = []

    # Procesar listas filtradas
    if list_middle_line_filtrada:
        list_middle_line_np = np.array(list_middle_line_filtrada)
        list_middle_line_mean = np.mean(list_middle_line_np.reshape(list_middle_line_np.shape[0], -1, 2), axis=2)
        list_middle_line_median_top = np.median(list_middle_line_mean, axis=0)
    else:
        list_middle_line_median_top = np.array([])
    # ---- END ----


    # ---- Parte inferior ----
    diff_slice = np.diff(bot_slice)
    points_bot = np.where(diff_slice > 0)

    list_middle_line = [[] for _ in range(config.EDGE_PIXELS)]
    list_cuts   = points_bot[0]
    list_pixels = points_bot[1]
    for cut, pixel in zip(list_cuts, list_pixels):
        list_middle_line[cut].append(pixel)

    if any(list_middle_line):
        longitudes = [len(lst) for lst in list_middle_line]
        longitudes_pares = [l for l in longitudes if l > 0 and l % 2 == 0]

        if longitudes_pares:
            counter = Counter(longitudes_pares)
            longitud_mas_comun = counter.most_common(1)[0][0]

            list_middle_line_filtrada = [lst for lst in list_middle_line if len(lst) == longitud_mas_comun]
        else:
            list_middle_line_filtrada = []
    else:
        list_middle_line_filtrada = []

    if list_middle_line_filtrada:
        list_middle_line_np = np.array(list_middle_line_filtrada)
        list_middle_line_mean = np.mean(list_middle_line_np.reshape(list_middle_line_np.shape[0], -1, 2), axis=2)
        list_middle_line_median_bot = np.median(list_middle_line_mean, axis=0)
    else:
        list_middle_line_median_bot = np.array([])
    # ---- END ----


    # ---- Parte izquierda ----
    diff_slice = np.diff(left_slice, axis=0)
    points_left = np.where(diff_slice > 0)

    list_middle_line = [[] for _ in range(config.EDGE_PIXELS)]
    list_cuts   = points_left[1]
    list_pixels = points_left[0]

    for cut, pixel in zip(list_cuts, list_pixels):
        list_middle_line[cut].append(pixel)

    if any(list_middle_line):
        longitudes = [len(lst) for lst in list_middle_line]
        longitudes_pares = [l for l in longitudes if l > 0 and l % 2 == 0]

        if longitudes_pares:
            counter = Counter(longitudes_pares)
            longitud_mas_comun = counter.most_common(1)[0][0]

            list_middle_line_filtrada = [lst for lst in list_middle_line if len(lst) == longitud_mas_comun]
        else:
            list_middle_line_filtrada = []
    else:
        list_middle_line_filtrada = []

    if list_middle_line_filtrada:
        list_middle_line_np = np.array(list_middle_line_filtrada)
        list_middle_line_mean = np.mean(list_middle_line_np.reshape(list_middle_line_np.shape[0], -1, 2), axis=2)
        list_middle_line_median_left = np.median(list_middle_line_mean, axis=0)
    else:
        list_middle_line_median_left = np.array([])
    # ---- END ----


    # ---- Parte Derecha ----
    diff_slice = np.diff(right_slice, axis=0)
    points_right = np.where(diff_slice > 0)

    list_middle_line = [[] for _ in range(config.EDGE_PIXELS)]
    list_cuts   = points_right[1]
    list_pixels = points_right[0]

    for cut, pixel in zip(list_cuts, list_pixels):
        list_middle_line[cut].append(pixel)

    if any(list_middle_line):
        longitudes = [len(lst) for lst in list_middle_line]
        longitudes_pares = [l for l in longitudes if l > 0 and l % 2 == 0]
        
        if longitudes_pares:
            counter = Counter(longitudes_pares)
            longitud_mas_comun = counter.most_common(1)[0][0]

            list_middle_line_filtrada = [lst for lst in list_middle_line if len(lst) == longitud_mas_comun]
        else:
            list_middle_line_filtrada = []
    else:
        list_middle_line_filtrada = []

    if list_middle_line_filtrada:
        list_middle_line_np = np.array(list_middle_line_filtrada)
        list_middle_line_mean = np.mean(list_middle_line_np.reshape(list_middle_line_np.shape[0], -1, 2), axis=2)
        list_middle_line_median_right = np.median(list_middle_line_mean, axis=0)
    else:
        list_middle_line_median_right = np.array([])
    # ---- END ----


    # ---- Parte media ----
    diff_slice = np.diff(middle_slice)
    points_middle = np.where(diff_slice > 0)

    list_middle_line = [[] for _ in range(config.EDGE_PIXELS)]
    list_cuts   = points_middle[0]
    list_pixels = points_middle[1]
    for cut, pixel in zip(list_cuts, list_pixels):
        list_middle_line[cut].append(pixel)

    if any(list_middle_line):
        longitudes = [len(lst) for lst in list_middle_line]
        longitudes_pares = [l for l in longitudes if l > 0 and l % 2 == 0]

        if longitudes_pares:
            counter = Counter(longitudes_pares)
            longitud_mas_comun = counter.most_common(1)[0][0]

            list_middle_line_filtrada = [lst for lst in list_middle_line if len(lst) == longitud_mas_comun]
        else:
            list_middle_line_filtrada = []
    else:
        list_middle_line_filtrada = []

    if list_middle_line_filtrada:
        list_middle_line_np = np.array(list_middle_line_filtrada)
        list_middle_line_mean = np.mean(list_middle_line_np.reshape(list_middle_line_np.shape[0], -1, 2), axis=2)
        list_middle_line_median_middle = np.median(list_middle_line_mean, axis=0)
    else:
        list_middle_line_median_middle = np.array([])
    # ---- END ----


    return [
        [(config.EDGE_PIXELS//2, cut) for cut in list_middle_line_median_top],
        [(cut, config.EDGE_PIXELS//2) for cut in list_middle_line_median_left],
        [(cut, w-config.EDGE_PIXELS//2) for cut in list_middle_line_median_right],
        [(h-config.EDGE_PIXELS//2, cut) for cut in list_middle_line_median_bot],
        [(dron_pos, cut) for cut in list_middle_line_median_middle],
    ]

def pair_edge_centre(
        lista_types_and_cuts
    ):
    """
    Empareja los cortes de los bordes con los cortes en el centro.

    Parameters
    ----------
    lista_types_and_cuts:
        Lista de cortes en los bordes

    Returns
    -------
    list_pairs : list
        Lista de parejas de (centro, borde)
    """

    list_left   = lista_types_and_cuts[1][1]
    list_top    = lista_types_and_cuts[1][0]
    list_right  = lista_types_and_cuts[1][2]
    list_centre = lista_types_and_cuts[1][4]

    list_ltr = list_left + list_top + list_right

    # Le damos la vuelta a la lista de la izquierda
    list_left = list_left[::-1]

    if len(list_centre) == 0:
        return []

    list_pairs = []

    # Si hay solamente un corte arriba emparejar con el corte del centro mas cercano
    if len(list_top) == 1:
        return [
            (
                list_centre[np.argmin([get_pixel_distance(list_top[0], point_centre) for point_centre in list_centre])],
                list_top[0]
            )
        ]

    # Emparejamos el borde con el que este mas cercano
    for cut_border in list_ltr:
        index = np.argmin([get_pixel_distance(cut_border, point_centre) for point_centre in list_centre])
        list_pairs.append((list_centre[index], cut_border))

    return list_pairs

def calculate_angle(
        punto1,
        punto2
    ):
    """
    Calcula el angulo en grados con respecto a la horizontal, necesario para
    "rotar" el punto1 hasta que este en la misma coordenada Y que el punto2.

    El sistema de coordenadas de OpenCV tiene el origen (0,0) en la esquina
    superior izquierda, con Y aumentando hacia abajo y X aumentando hacia la derecha.

    Parameters
    ----------
    punto1 : tuple
        Coordenadas (x1, y1) del primer punto.
    punto2 : tuple
        Coordenadas (x2, y2) del segundo punto (punto de referencia).

    Returns
    -------
    float:
        El angulo en grados. Matematicamente invertido para comodidad 
    """

    x1, y1 = punto1
    x2, y2 = punto2

    # cateto opuesto
    delta_y = y1 - y2
    # cateto contiguo.
    delta_x = x2 - x1
    
    # Caso de una linea vertical
    if delta_x == 0:
        if delta_y < 0:
            angulo_grados = np.float64(90.0)
        elif delta_y > 0:
            angulo_grados = np.float64(-90.0)
        else:
            angulo_grados = None
    else:
        angulo_radianes = np.arctan2(-delta_y, delta_x)
        angulo_grados = np.degrees(angulo_radianes)

    # Se niega el angulo para que la salida pueda ser la entrada del PID de manera directa
    return -angulo_grados

def select_angle(
        lista_types_and_cuts,
        previous_angle_point,
        preference=None,
    ):
    """
    Devuelve el elemento de la lista que mas cerca esté del angulo anterior.
    En caso de estar vacia devuelve `None`.

    Parameters
    ----------
    lista_types_and_cuts:
        Lista de tipo de linea y cortes en los bordes
    previous_angle:
        Angulo que estaba siguiendo el dron en el ultimo frame valido
    preference:
        Preferencia de angulo ['left', 'right']

    Returns
    -------
    angle:
        Angulo de entrada para el PID
    cut_point:
        Punto de corte (x, y) donde se encuentra el angulo que estamos siguiendo
    index_figure:
        Indice de la figura que vamos a seguir. Servira como entrada para calcular
        el desplazamiento lateral.
    """

    # No hay figuras, reiniciar el angulo previo y el actual para el PID
    if lista_types_and_cuts == []:
        return None, (), None

    # Elige la figura que tenga el corte en los bordes mas cercano al anterior
    selected_figure_index = 0
    min_distance = config.FRAME_WIDTH**2
    for fig_index, (solidity, list_cuts) in enumerate(lista_types_and_cuts):
        for edge_index, edge in enumerate(list_cuts):
            for point in edge:
                # Solo queremos fijarnos en los bordes arriba, izquierda y derecha
                if edge_index in [0, 1, 2]:
                    pixel_distance = get_pixel_distance(previous_angle_point, point)
                    if pixel_distance < min_distance:
                        selected_figure_index = fig_index
                        min_distance = pixel_distance

    list_pairs = pair_edge_centre(lista_types_and_cuts[selected_figure_index])

    # 1. Puede haber corte en el centro y abajo pero no en los lados importantes
    if len(list_pairs) == 0:
        return None, (), selected_figure_index

    # 2. Si solo hay un corte, solo podemos seguir ese corte
    elif len(list_pairs) == 1:
        selected_pair = list_pairs[0]

    # 3. Con dos cortes seguimos el del lado que queramos
    elif len(list_pairs) == 2:
        if preference == 'left':
            selected_pair = list_pairs[0]
        elif preference == 'right':
            selected_pair = list_pairs[1]
        else:
            selected_pair = list_pairs[1]

    # 4. Con mas cortes seleccionamos el mas cercano al anterior
    else:
        selected_pair = min(list_pairs, key=lambda pair: get_pixel_distance(pair[1], previous_angle_point))

    selected_angle = calculate_angle(selected_pair[1], selected_pair[0])

    return selected_angle, selected_pair, selected_figure_index

def calculate_lateral_roll(
        frame_resized,
        selected_pair,
        altura_dron,
    ):
    """
    Calcula el desplazamiento lateral de la linea respecto al centro de la imagen.
    Devuelve el error en centimetros.

    Parameters
    ----------
    frame_resized:
        Frame utilizado para la visualizacion del usuario con anotaciones.
    selected_pair:
        Pareja seleccionada para el calculo del angulo de giro.
    altura_dron:
        Altura actual del dron en centimetros.

    Returns
    -------
    roll_offset : bool
        Desplazamiento lateral necesario en centimetros
    frame_resized:
        Frame utilizado para la visualizacion del usuario con anotaciones.
    """

    if selected_pair == () or len(selected_pair) != 2:
        return None, frame_resized

    centre_cut = selected_pair[0]
    medida_media_base = altura_dron * np.tan(np.radians(41.3))
    pixel_offset = centre_cut[1] - (config.FRAME_WIDTH//2)
    medida_real_offset = (medida_media_base * pixel_offset) / (config.FRAME_WIDTH//2)

    if config.SAVE_VIDEO: cv2.line(frame_resized, (int(centre_cut[1]-5), int(centre_cut[0])), (int(centre_cut[1]+5), int(centre_cut[0])), (255, 0, 255), 2)

    return medida_real_offset, frame_resized

def equal_images(
        img1,
        img2
    ):
    """
    Compara dos imagenes y devuelve `True` o `False` segun sean iguales o no

    Parameters
    ----------
    img1:
        Primera imagen
    img2:
        Segunda imagen

    Returns
    -------
    equal : bool
        Devuelve `True` si las dos imagenes son iguales, `False` en caso contrario
    """

    if img1.shape == () or img2.shape == ():
        return np.array_equal(img1, img2)
    
    h, w, _ = img1.shape
    
    # 1. Comprobar pixel fijo
    y_fija = h // 4
    x_fija = w // 2
    if not np.array_equal(img1[y_fija, x_fija], img2[y_fija, x_fija]):
        return False

    # 2. Comprobar 6 pixeles en la misma altura
    indices_x = np.linspace(0, w - 1, 6, dtype=int)
    if not np.array_equal(img1[y_fija, indices_x], img2[y_fija, indices_x]):
        return False

    # 3. Comprobacion completa
    return np.array_equal(img1, img2)

def process_frame(
        frame,
        boundaries_colors,
    ):
    """
    Procesa un frame de video para extraer informacion de la linea.

    Parameters
    ----------
    frame:
        Frame original del dron
    boundaries_colors:
        Fronteras de valor Hue entre los colores seleccionados

    Returns
    -------
    frame_resized:
        Frame original resultante de hacer un reescalado
    list_type_and_cuts:
        Lista con los cortes con los bordes (arriba, izquierda, derecha y abajo) y en la posicion del dron
    color_led : str
        Color con mayor representacion en número de LED's vistos en el frame
    """

    start = time.time_ns()
    color_led = get_led_color(frame, boundaries_colors)
    end = time.time_ns()
    config.time_led.append(end-start)

    start = time.time_ns()
    frame_flipped = cv2.flip(frame, 0)
    frame_resized = cv2.resize(frame_flipped, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
    end = time.time_ns()
    config.time_preprocess.append(end-start)

    start = time.time_ns()
    list_binary_images = binarize_frame(frame_resized)
    end = time.time_ns()
    config.time_binarize.append(end-start)

    start = time.time_ns()
    _, aruco_ids = aruco_markers(frame_resized)
    end = time.time_ns()
    config.time_aruco.append(end-start)

    list_type_and_cuts = []

    for binary_image in list_binary_images:

        start = time.time_ns()
        solidity = solidity_index(binary_image)
        end = time.time_ns()
        config.time_solidity.append(end-start)

        start = time.time_ns()
        list_cuts = get_edge_cuts(binary_image)
        list_cuts_clean = clean_cuts(list_cuts[0:-1])
        end = time.time_ns()
        config.time_edges.append(end-start)

        list_type_and_cuts.append(
            (
                solidity,
                [*list_cuts_clean, list_cuts[-1]]
            )
        )

    return frame_resized, list_type_and_cuts, color_led, aruco_ids
