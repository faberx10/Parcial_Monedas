"""
config.py
=========
Configuracion central del reconocimiento de monedas - Grupo 3.
Todo lo que tengas que cambiar (IP, umbrales, clases) esta aqui.
"""

from pathlib import Path

# ----------------------------------------------------------------------
# ESP32-CAM
# ----------------------------------------------------------------------
ESP32_IP = "192.168.1.14"              # <-- cambiala si tu router asigna otra
STREAM_URL = f"http://{ESP32_IP}:81/stream"
CONTROL_URL = f"http://{ESP32_IP}/control"

# Ajustes que se envian a la camara al arrancar (se pierden cada vez que
# la ESP32 se reinicia, por eso los aplicamos desde el PC).
# La resolucion (VGA 640x480) se fija en el sketch de Arduino, ver README.
AJUSTES_CAMARA = {
    "quality": 12,        # 10-15: buen balance nitidez / fluidez
    "vflip": 1,           # tu camara salia al reves: 1 la endereza (0 si queda al reves)
    "hmirror": 0,
    "led_intensity": 0,   # flash apagado: el metal refleja y satura la foto
}

# Fraccion del lado menor de la imagen que se recorta al centro (cuadrado).
# La moneda debe quedar dentro del circulo guia que dibujan los scripts.
FRACCION_RECORTE = 0.80
TAM_GUARDADO = 320      # px del recorte que se guarda en el dataset

# ----------------------------------------------------------------------
# Clases: nombre interno -> (etiqueta visible, valor en pesos, tecla)
# ----------------------------------------------------------------------
CLASES = {
    "1000_nueva":  ("$1.000 nueva",  1000, "1"),
    "500_nueva":   ("$500 nueva",     500, "2"),
    "500_antigua": ("$500 antigua",   500, "3"),
    "200_nueva":   ("$200 nueva",     200, "4"),
    "200_antigua": ("$200 antigua",   200, "5"),
    "100_nueva":   ("$100 nueva",     100, "6"),
    "100_antigua": ("$100 antigua",   100, "7"),
    "fondo":       ("Sin moneda",       0, "0"),
}
CLASE_FONDO = "fondo"
CLASES_MONEDA = [c for c in CLASES if c != CLASE_FONDO]

# ----------------------------------------------------------------------
# Reglas de conteo (evitan contar dos veces la misma moneda)
# ----------------------------------------------------------------------
UMBRAL_CONFIANZA = 0.85   # confianza minima para aceptar una prediccion
FRAMES_ESTABLES = 6       # frames seguidos con la misma moneda para contarla
FRAMES_VACIO = 5          # frames de fondo para "rearmar" el contador

# ----------------------------------------------------------------------
# Rutas
# ----------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
DIR_DATASET_CRUDO = RAIZ / "dataset_crudo"   # lo que captura el script 01
DIR_DATASET = RAIZ / "dataset"               # train/val que arma el script 02
DIR_MODELOS = RAIZ / "modelos"
RUTA_MODELO = DIR_MODELOS / "monedas.pt"
DIR_CAPTURAS = RAIZ / "capturas"             # fotos de cada moneda contada
