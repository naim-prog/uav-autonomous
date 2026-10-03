# Desarrollo de un Sistema de Guiado Autónomo y Control de Lazo Cerrado para UAVs en Interiores Industriales

Este repositorio contiene el código fuente, diseños 3D y la documentación técnica del Trabajo de Fin de Grado en Ingeniería Informática (Universidad de Cádiz, 2026), realizado por Naím Rodríguez Reyes.

## Documentación principal (Memoria)

Toda la información técnica detallada, incluyendo el modelado matemático del controlador PD, los experimentos de calibración gaussiana en espacio HSV, la validación cinemática y las pruebas en entorno real, se encuentra redactada en la memoria oficial del proyecto:

[Descargar memoria completa (PDF)](./Memoria_TFG.pdf)

## Vídeo demostración

[![Vídeo demostración](https://pub-1bf0594c46264a9c9ae5a139ec1cf243.r2.dev/videos_demostracion_frame_0.jpg)](https://pub-1bf0594c46264a9c9ae5a139ec1cf243.r2.dev/videos_demostracion.mp4)

## Motivación y resumen del proyecto

En entornos industriales críticos (como astilleros o plantas logísticas), la saturación de redes inalámbricas, las interferencias electromagnéticas y las restricciones de ciberseguridad imposibilitan el guiado de drones mediante procesamiento en servidores externos.

Este proyecto presenta una solución de navegación autónoma de alta precisión en lazo cerrado sobre una plataforma de bajo coste (DJI Tello), delegando la percepción al propio entorno físico a través de líneas de seguimiento, señalización lumínica dinámica (LEDs) y marcadores de emergencia (ArUco).

```
+------------------+      Vídeo H.264 (UDP 11111)      +-------------------------+
|    DJI Tello     | --------------------------------> |  Estación de Control    |
| (Espejo 50° 3D)  | <-------------------------------- |  (Visión por Computador |
+------------------+    Comandos SDK (UDP 8889)        |   + Control PD Dual)    |
                                                       +-------------------------+
```

## Innovaciones clave del sistema

- **Adaptación óptica 3D**: Diseño no destructivo de un acople a 50° con espejo ultrafino (1 mm) que redirige el campo de visión de la cámara frontal hacia el suelo, proporcionando un alcance de 40 cm de anticipación frontal a 60 cm de altitud.

- **Pipeline de visión en tiempo real**: Algoritmo de filtrado jerárquico de frames duplicados y binarización adaptativa ante variaciones severas de iluminación.

- **Controlador dual PD**: Regulación simultánea de guiñada (*Yaw*) y alabeo (*Roll*) optimizada para eliminar fenómenos de saturación (*windup*) y mantener la aeronave sobre la línea central.

- **Toma de decisiones y contingencias**: Reconocimiento de estados cromáticos mediante modelado estocástico (*HSV*) y detección activa de marcadores ArUco para paradas de emergencia o reenrutamiento.

## Aplicaciones industriales

La arquitectura propuesta sirve como prueba de concepto para escenarios reales en la industria (tales como la industria naval o de defensa):

- **Inspección de pasillos operativos**: Patrullaje autónomo en naves sin cobertura GPS ni dependencia de redes externas.

- **Entornos de ciberseguiridad**: Navegación reactiva con mínima emisión de radiofrecuencia, inmune a interferencias o robos de señal.

- **Paradas de emergencia físicas**: Interrupción inmediata de rutas mediante la colocación de balizas fiduciales temporales por parte del personal de planta.

## Estructura del repositorio

```
.
├── src/                  # Código fuente del proyecto
├── src/requirements.txt  # Dependencias del proyecto
├── 3d/                   # Diseños STL para la adaptación óptica a 50°
└── Memoria_TFG.pdf       # Memoria académica completa del TFG
```

## Uso e instalación del programa

1. Clonar el repositorio e instalar las dependencias

```bash
git clone https://github.com/naim-prog/uav-autonomous.git
cd uav-autonomous/src/
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

2. Ejemplo de ejecución del programa

```bash
python src/main.py --save-video --altitude 90 --timer
```
