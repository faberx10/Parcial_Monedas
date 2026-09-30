"""
camara.py
=========
Lectura del video de la ESP32-CAM desde el PC.

La ESP32 (sketch CameraWebServer) publica un stream MJPEG en
http://IP:81/stream. Aqui un hilo en segundo plano lee ese stream sin
parar y siempre guarda el ULTIMO frame decodificado; asi el programa
principal nunca se atrasa acumulando frames viejos (causa tipica de
"lag" creciente con la ESP32-CAM).
"""

import threading
import time

import cv2
import numpy as np
import requests

import config


def aplicar_ajustes(ajustes=None, timeout=3):
    """Envia a la ESP32 los ajustes de config.AJUSTES_CAMARA (/control)."""
    ajustes = ajustes or config.AJUSTES_CAMARA
    for var, val in ajustes.items():
        try:
            requests.get(config.CONTROL_URL, params={"var": var, "val": val},
                         timeout=timeout)
        except requests.RequestException as e:
            print(f"[camara] no se pudo aplicar {var}={val}: {e}")


class CamaraESP32:
    """Lector MJPEG en hilo propio. Uso: cam.start(); frame = cam.leer()."""

    def __init__(self, url=None):
        self.url = url or config.STREAM_URL
        self._frame = None
        self._t_frame = 0.0
        self._lock = threading.Lock()
        self._activo = False
        self._hilo = None
        self.conectada = False
        self.fps = 0.0
        self.n_frames = 0          # sube con cada frame nuevo recibido

    # ------------------------------------------------------------------
    def start(self):
        self._activo = True
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        return self

    def stop(self):
        self._activo = False

    def leer(self):
        """Devuelve (frame BGR o None, edad del frame en segundos)."""
        with self._lock:
            if self._frame is None:
                return None, None
            return self._frame.copy(), time.time() - self._t_frame

    # ------------------------------------------------------------------
    def _bucle(self):
        while self._activo:
            try:
                self._leer_stream()
            except Exception as e:  # red caida, ESP32 reiniciada, etc.
                self.conectada = False
                print(f"[camara] sin conexion ({e.__class__.__name__}); "
                      f"reintentando en 2 s...")
                time.sleep(2)

    def _leer_stream(self):
        with requests.get(self.url, stream=True, timeout=(4, 8)) as r:
            r.raise_for_status()
            self.conectada = True
            print(f"[camara] conectada a {self.url}")
            buffer = b""
            conteo, t0 = 0, time.time()
            for trozo in r.iter_content(chunk_size=4096):
                if not self._activo:
                    return
                buffer += trozo
                # Un JPEG empieza en FFD8 y termina en FFD9
                ini = buffer.find(b"\xff\xd8")
                fin = buffer.find(b"\xff\xd9", ini + 2) if ini != -1 else -1
                if ini == -1 or fin == -1:
                    if len(buffer) > 2_000_000:   # basura acumulada
                        buffer = b""
                    continue
                jpg = buffer[ini:fin + 2]
                buffer = buffer[fin + 2:]
                img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    continue
                with self._lock:
                    self._frame = img
                    self._t_frame = time.time()
                    self.n_frames += 1
                conteo += 1
                if time.time() - t0 >= 1.0:
                    self.fps = conteo / (time.time() - t0)
                    conteo, t0 = 0, time.time()


# ----------------------------------------------------------------------
# Utilidades de imagen compartidas por captura, entrenamiento e interfaz
# ----------------------------------------------------------------------
def recorte_central(img, fraccion=None):
    """Recorte cuadrado centrado. Devuelve (recorte, (x0, y0, lado))."""
    fraccion = fraccion or config.FRACCION_RECORTE
    h, w = img.shape[:2]
    lado = int(min(h, w) * fraccion)
    x0, y0 = (w - lado) // 2, (h - lado) // 2
    return img[y0:y0 + lado, x0:x0 + lado], (x0, y0, lado)


def dibujar_guia(img, color=(80, 190, 255)):
    """Dibuja el circulo donde debe ponerse la moneda."""
    _, (x0, y0, lado) = recorte_central(img)
    c = (x0 + lado // 2, y0 + lado // 2)
    cv2.circle(img, c, int(lado * 0.45), color, 2, cv2.LINE_AA)
    cv2.rectangle(img, (x0, y0), (x0 + lado, y0 + lado), (90, 90, 90), 1)
    return img


def nitidez(img):
    """Varianza del Laplaciano: < ~60 suele ser una foto movida/desenfocada."""
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gris, cv2.CV_64F).var())
