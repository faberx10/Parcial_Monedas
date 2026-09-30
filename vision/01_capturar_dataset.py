"""
01_capturar_dataset.py
======================
Captura fotos de entrenamiento desde la ESP32-CAM.

Controles (con la ventana de video seleccionada):
    1..7   elegir clase activa y tomar UNA foto
           1=$1000 nueva  2=$500 nueva  3=$500 antigua  4=$200 nueva
           5=$200 antigua 6=$100 nueva  7=$100 antigua
    0      clase "fondo" (sin moneda) y tomar UNA foto
    R      rafaga ON/OFF para la clase activa (~4 fotos/s, descarta las movidas)
    Q/ESC  salir

Meta sugerida: 150 fotos por moneda (75 por cada cara) + 150 de fondo.
Las fotos quedan en dataset_crudo/<clase>/.

Uso:
    python 01_capturar_dataset.py
"""

import time
from datetime import datetime

import cv2
import numpy as np

import config
from camara import CamaraESP32, aplicar_ajustes, dibujar_guia, nitidez, recorte_central

META_POR_CLASE = 150
INTERVALO_RAFAGA = 0.25     # segundos entre fotos en modo rafaga
NITIDEZ_MIN = 40            # por debajo se considera foto movida


def contar_existentes():
    cuenta = {}
    for c in config.CLASES:
        d = config.DIR_DATASET_CRUDO / c
        d.mkdir(parents=True, exist_ok=True)
        cuenta[c] = len(list(d.glob("*.jpg")))
    return cuenta


def guardar(frame, clase):
    recorte, _ = recorte_central(frame)
    recorte = cv2.resize(recorte, (config.TAM_GUARDADO, config.TAM_GUARDADO),
                         interpolation=cv2.INTER_AREA)
    nombre = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
    cv2.imwrite(str(config.DIR_DATASET_CRUDO / clase / nombre), recorte,
                [cv2.IMWRITE_JPEG_QUALITY, 95])


def main():
    print("Aplicando ajustes a la camara...")
    aplicar_ajustes()
    cam = CamaraESP32().start()
    teclas = {ord(t): c for c, (_, _, t) in config.CLASES.items()}
    cuenta = contar_existentes()
    activa = config.CLASES_MONEDA[0]
    rafaga = False
    t_ultima = 0.0

    print(__doc__)
    while True:
        frame, _ = cam.leer()
        if frame is None:
            vacio = np.zeros((480, 640, 3), np.uint8)
            cv2.putText(vacio, "Esperando video de la ESP32-CAM...", (40, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            cv2.imshow("Captura", vacio)
            if cv2.waitKey(200) & 0xFF in (ord("q"), 27):
                break
            continue

        ahora = time.time()
        if rafaga and ahora - t_ultima >= INTERVALO_RAFAGA:
            recorte, _ = recorte_central(frame)
            if nitidez(recorte) >= NITIDEZ_MIN:
                guardar(frame, activa)
                cuenta[activa] += 1
                if cuenta[activa] % 10 == 0:
                    print(f"  [rafaga] {config.CLASES[activa][0]}: {cuenta[activa]} fotos")
            t_ultima = ahora

        vista = dibujar_guia(frame.copy())
        cv2.imshow("Captura", vista)

        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), 27):
            break
        if k in (ord("r"), ord("R")):
            rafaga = not rafaga
            print(f"Rafaga {'ACTIVADA' if rafaga else 'detenida'} -> {config.CLASES[activa][0]}")
        elif k in teclas:
            activa = teclas[k]
            guardar(frame, activa)
            cuenta[activa] += 1
            print(f"Guardada 1 foto de {config.CLASES[activa][0]} (total {cuenta[activa]})")

    cam.stop()
    cv2.destroyAllWindows()
    print("\nResumen del dataset:")
    for c, n in cuenta.items():
        marca = "OK" if n >= META_POR_CLASE else f"faltan {META_POR_CLASE - n}"
        print(f"  {config.CLASES[c][0]:<16} {n:>4}  {marca}")


if __name__ == "__main__":
    main()
