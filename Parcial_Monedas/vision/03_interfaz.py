"""
03_interfaz.py
==============
Servidor de la interfaz en tiempo real.

  ESP32-CAM --(MJPEG WiFi)--> este programa --(modelo YOLO)--> contador
                                   |
                                   +--> http://localhost:8000  (interfaz web)

Rutas:
    /         interfaz (static/index.html)
    /video    video en vivo anotado (MJPEG)
    /ws       estado en tiempo real (WebSocket, JSON)
    /reset    POST: pone los contadores en cero

Uso:
    python 03_interfaz.py            # con la ESP32-CAM y el modelo entrenado
    python 03_interfaz.py --demo     # sin ESP32 ni modelo: datos simulados
"""

import argparse
import asyncio
import base64
import math
import random
import threading
import time
from datetime import datetime

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

import config
from camara import CamaraESP32, aplicar_ajustes, recorte_central
from contador import ContadorEstable

DIR_STATIC = config.RAIZ / "static"
MAX_HISTORIAL = 12


# ======================================================================
# Fuentes de datos: real (ESP32 + modelo) y demo (simulada)
# ======================================================================
class FuenteReal:
    """ESP32-CAM + modelo YOLO entrenado."""

    def __init__(self):
        from ultralytics import YOLO
        if not config.RUTA_MODELO.exists():
            raise SystemExit(f"[X] No existe {config.RUTA_MODELO}. "
                             "Entrena primero con 02_entrenar.py, o usa --demo.")
        self.modelo = YOLO(str(config.RUTA_MODELO))
        self.nombres = self.modelo.names
        faltan = set(config.CLASES) - set(self.nombres.values())
        if faltan:
            raise SystemExit(f"[X] El modelo no conoce estas clases: {faltan}")
        aplicar_ajustes()
        self.cam = CamaraESP32().start()
        self._ultimo = -1

    @property
    def conectada(self):
        return self.cam.conectada

    @property
    def fps(self):
        return self.cam.fps

    def siguiente(self):
        """Devuelve (frame, {clase: prob}) o (None, None) si no hay frame nuevo."""
        if self.cam.n_frames == self._ultimo:
            return None, None
        self._ultimo = self.cam.n_frames
        frame, _ = self.cam.leer()
        if frame is None:
            return None, None
        recorte, _ = recorte_central(frame)
        r = self.modelo.predict(recorte, imgsz=224, verbose=False)[0]
        probs = r.probs.data.cpu().numpy()
        return frame, {self.nombres[i]: float(p) for i, p in enumerate(probs)}


class FuenteDemo:
    """Genera video y predicciones falsas para probar la interfaz."""

    ESTILO = {  # colores BGR aproximados para dibujar la moneda simulada
        "1000_nueva": ((200, 200, 205), (60, 170, 210)),
        "500_nueva": ((70, 175, 215), (195, 195, 200)),
        "500_antigua": ((80, 160, 200), (185, 185, 190)),
        "200_nueva": ((70, 160, 205), None),
        "200_antigua": ((95, 170, 200), None),
        "100_nueva": ((60, 150, 200), None),
        "100_antigua": ((150, 150, 150), None),
    }

    def __init__(self):
        self.conectada = True
        self.fps = 12.0
        self.t0 = time.time()
        self.fase = None
        self._nueva_fase()
        rng = np.random.default_rng(3)
        ruido = rng.integers(0, 18, (480, 640, 1), dtype=np.uint8)
        self.fondo = (np.full((480, 640, 3), (52, 55, 60), np.uint8) + ruido)

    def _nueva_fase(self):
        if self.fase and self.fase[0] != config.CLASE_FONDO:
            self.fase = (config.CLASE_FONDO, time.time(), random.uniform(1.2, 2.0))
        else:
            clase = random.choice(config.CLASES_MONEDA)
            self.fase = (clase, time.time(), random.uniform(2.2, 3.2))

    def siguiente(self):
        time.sleep(1 / self.fps)
        clase, t_ini, dur = self.fase
        t = time.time() - t_ini
        if t > dur:
            self._nueva_fase()
            clase, t_ini, dur = self.fase
            t = 0
        frame = self.fondo.copy()
        probs = {c: random.uniform(0, 0.02) for c in config.CLASES}
        if clase == config.CLASE_FONDO:
            probs[clase] = random.uniform(0.93, 0.99)
        else:
            cx = 320 + int(8 * math.sin(t * 3))
            cy = 240 + int(6 * math.cos(t * 2))
            centro, anillo = self.ESTILO[clase]
            r = 95 if clase.startswith("1000") else 88 if clase.startswith("500") else 80
            if anillo:
                cv2.circle(frame, (cx, cy), r, anillo, -1, cv2.LINE_AA)
                cv2.circle(frame, (cx, cy), int(r * 0.66), centro, -1, cv2.LINE_AA)
            else:
                cv2.circle(frame, (cx, cy), r, centro, -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), r, (40, 40, 40), 2, cv2.LINE_AA)
            texto = clase.split("_")[0]
            (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_DUPLEX, 1.1, 2)
            cv2.putText(frame, texto, (cx - tw // 2, cy + th // 2),
                        cv2.FONT_HERSHEY_DUPLEX, 1.1, (40, 40, 40), 2, cv2.LINE_AA)
            # los primeros instantes la prediccion es dudosa (moneda entrando)
            if t < 0.35:
                probs[clase] = random.uniform(0.4, 0.7)
                probs[random.choice(config.CLASES_MONEDA)] += 0.25
            else:
                probs[clase] = random.uniform(0.9, 0.995)
                gemela = clase.replace("nueva", "antigua") if "nueva" in clase \
                    else clase.replace("antigua", "nueva")
                if gemela in probs:
                    probs[gemela] += random.uniform(0.0, 0.06)
        total = sum(probs.values())
        return frame, {c: p / total for c, p in probs.items()}


# ======================================================================
# Motor: corre en un hilo, mantiene el estado que lee la interfaz
# ======================================================================
class Motor:
    def __init__(self, fuente, guardar_capturas=True):
        self.fuente = fuente
        self.guardar_capturas = guardar_capturas   # en --demo no se guardan fotos falsas
        self.contador = ContadorEstable()
        self.lock = threading.Lock()
        self.jpeg = None
        self.pred = {"clase": None, "confianza": 0.0, "top": []}
        self.historial = []          # eventos de conteo (mas reciente primero)
        self.n_evento = 0
        self.fps_inferencia = 0.0

    def start(self):
        threading.Thread(target=self._bucle, daemon=True).start()
        return self

    def reset(self):
        with self.lock:
            self.contador.reiniciar()
            self.historial.clear()

    def _bucle(self):
        n, t0 = 0, time.time()
        while True:
            frame, probs = self.fuente.siguiente()
            if frame is None:
                time.sleep(0.005)
                continue
            clase = max(probs, key=probs.get)
            conf = probs[clase]
            top = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:3]

            with self.lock:
                evento = self.contador.actualizar(clase, conf)
                if evento:
                    self._registrar(frame, evento, conf)
                self.pred = {"clase": clase, "confianza": conf,
                             "top": [[c, p] for c, p in top]}
                self.jpeg = self._anotar(frame, clase, conf)

            n += 1
            if time.time() - t0 >= 1:
                self.fps_inferencia = n / (time.time() - t0)
                n, t0 = 0, time.time()

    def _registrar(self, frame, clase, conf):
        recorte, _ = recorte_central(frame)
        ahora = datetime.now()
        if self.guardar_capturas:
            destino = config.DIR_CAPTURAS / clase
            destino.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(destino / (ahora.strftime("%Y%m%d_%H%M%S_%f") + ".jpg")), recorte)
        mini = cv2.resize(recorte, (112, 112), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", mini, [cv2.IMWRITE_JPEG_QUALITY, 80])
        self.n_evento += 1
        self.historial.insert(0, {
            "id": self.n_evento,
            "clase": clase,
            "etiqueta": config.CLASES[clase][0],
            "valor": config.CLASES[clase][1],
            "confianza": conf,
            "hora": ahora.strftime("%H:%M:%S"),
            "miniatura": "data:image/jpeg;base64," + base64.b64encode(buf).decode(),
        })
        del self.historial[MAX_HISTORIAL:]

    def _anotar(self, frame, clase, conf):
        vista = frame.copy()
        _, (x0, y0, lado) = recorte_central(vista)
        c = (x0 + lado // 2, y0 + lado // 2)
        radio = int(lado * 0.45)
        es_moneda = clase != config.CLASE_FONDO and conf >= config.UMBRAL_CONFIANZA
        if not self.contador.armado:
            color = (120, 200, 90)            # verde: contada, retirar moneda
        elif es_moneda:
            color = (70, 190, 235)            # dorado: confirmando
        else:
            color = (150, 150, 150)           # gris: esperando
        cv2.circle(vista, c, radio, color, 2, cv2.LINE_AA)
        prog = self.contador.progreso
        if prog > 0:
            cv2.ellipse(vista, c, (radio + 7, radio + 7), -90, 0, 360 * prog,
                        (70, 190, 235), 4, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", vista, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else None

    def estado(self):
        with self.lock:
            clase = self.pred["clase"]
            return {
                "conectada": self.fuente.conectada,
                "fps_camara": round(self.fuente.fps, 1),
                "fps_inferencia": round(self.fps_inferencia, 1),
                "prediccion": {
                    "clase": clase,
                    "etiqueta": config.CLASES[clase][0] if clase else "—",
                    "confianza": self.pred["confianza"],
                    "top": [[c, config.CLASES[c][0], p] for c, p in self.pred["top"]],
                },
                "umbral": config.UMBRAL_CONFIANZA,
                "armado": self.contador.armado,
                "progreso": self.contador.progreso,
                "conteo": self.contador.conteo,
                "total_monedas": self.contador.total_monedas,
                "total_pesos": self.contador.total_pesos,
                "ultimo_evento": self.n_evento,
            }


# ======================================================================
# Aplicacion web
# ======================================================================
def crear_app(motor):
    app = FastAPI()

    @app.get("/")
    def inicio():
        return FileResponse(DIR_STATIC / "index.html")

    @app.get("/clases")
    def clases():
        return {c: {"etiqueta": e, "valor": v} for c, (e, v, _) in config.CLASES.items()
                if c != config.CLASE_FONDO}

    @app.post("/reset")
    def reset():
        motor.reset()
        return {"ok": True}

    @app.get("/video")
    def video():
        async def generar():
            anterior = None
            while True:
                jpg = motor.jpeg
                if jpg is not None and jpg is not anterior:
                    anterior = jpg
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                await asyncio.sleep(0.03)
        return StreamingResponse(generar(),
                                 media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        enviados = 0
        try:
            while True:
                estado = motor.estado()
                if estado["ultimo_evento"] != enviados:
                    with motor.lock:
                        nuevos = [e for e in motor.historial if e["id"] > enviados]
                    estado["eventos"] = list(reversed(nuevos))
                    enviados = estado["ultimo_evento"]
                await sock.send_json(estado)
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError):
            pass

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sin ESP32 ni modelo")
    ap.add_argument("--puerto", type=int, default=8000)
    args = ap.parse_args()

    fuente = FuenteDemo() if args.demo else FuenteReal()
    motor = Motor(fuente, guardar_capturas=not args.demo).start()
    print(f"\n  Interfaz lista en  http://localhost:{args.puerto}\n")
    uvicorn.run(crear_app(motor), host="0.0.0.0", port=args.puerto, log_level="warning")
