"""
00_importar_referencias.py
==========================
Arma el dataset de entrenamiento SOLO con las fotos de referencia
(carpeta referencias/), sin necesidad de capturar con la ESP32-CAM.

Estructura esperada (ya viene lista):
    referencias/<clase>/fNN.jpg   moneda centrada, ocupando ~74 % del recorte
    referencias/fondos/*.jpg      superficie SIN moneda (para la clase "fondo")

Cada foto se multiplica en muchas variantes que imitan a la camara: la moneda se
recorta, se gira, se cambia de tamano, se inclina un poco, se pega sobre fondos
distintos y se le cambia luz, color, enfoque, ruido y compresion JPEG.

Uso:
    python 00_importar_referencias.py --validar   # prueba honesta: aparta 1 foto por moneda
    python 00_importar_referencias.py             # dataset final: usa TODAS las fotos
Despues:
    python 02_entrenar.py --ya-preparado
"""

import argparse
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

import config

DIR_REF = config.RAIZ / "referencias"
LADO = config.TAM_GUARDADO          # 320
FRACCION_MONEDA = 0.74              # cuanto del recorte ocupa la moneda en las fotos de referencia

# Fotos que se apartan en modo --validar (nunca se usan para entrenar en ese modo)
APARTADAS = {"f07", "f04", "f14", "f16", "f20", "f21", "f23"}
# Parches de fondo apartados (vienen de las mismas fotos apartadas)
FONDOS_APARTADOS = {"f07", "f04", "f14", "f16", "f20", "f21", "f23"}


# ---------------------------------------------------------------------------
# Utilidades de imagen
# ---------------------------------------------------------------------------
def fondo_sintetico():
    tipo = random.random()
    if tipo < 0.4:      # oscuro liso
        base = np.array([random.randint(10, 70) for _ in range(3)], np.float32)
    elif tipo < 0.7:    # claro / gris
        v = random.randint(150, 240)
        base = np.array([v + random.randint(-15, 15) for _ in range(3)], np.float32)
    else:               # color cualquiera
        base = np.array([random.randint(30, 220) for _ in range(3)], np.float32)
    img = np.tile(base, (LADO, LADO, 1))
    gx = np.linspace(random.uniform(-30, 10), random.uniform(-10, 30), LADO, dtype=np.float32)
    img += gx[None, :, None]
    img += np.random.normal(0, random.uniform(1, 6), img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def fondo_real(fondos):
    f = random.choice(fondos)
    img = cv2.resize(f, (LADO, LADO))
    if random.random() < 0.5:
        img = cv2.flip(img, 1)
    img = np.rot90(img, random.randint(0, 3)).copy()
    if random.random() < 0.5:                       # a veces mas ampliado
        z = random.uniform(1.0, 1.8)
        n = int(LADO / z)
        x, y = random.randint(0, LADO - n), random.randint(0, LADO - n)
        img = cv2.resize(img[y:y + n, x:x + n], (LADO, LADO))
    return img


def fondo(fondos):
    return fondo_real(fondos) if random.random() < 0.6 else fondo_sintetico()


def fotometria(img):
    """Cambios de luz/color/enfoque/ruido que imitan una camara barata."""
    img = img.astype(np.float32)
    img = img * random.uniform(0.6, 1.3) + random.uniform(-25, 25)
    img *= np.array([random.uniform(0.85, 1.15) for _ in range(3)], np.float32)
    gris = img.mean(axis=2, keepdims=True)
    img = gris + (img - gris) * random.uniform(0.6, 1.25)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if random.random() < 0.3:                       # resolucion baja de la ESP32
        n = random.randint(140, 240)
        img = cv2.resize(cv2.resize(img, (n, n), interpolation=cv2.INTER_AREA), (LADO, LADO))
    if random.random() < 0.6:
        k = random.choice([3, 5])
        img = cv2.GaussianBlur(img, (k, k), 0)
    img = np.clip(img.astype(np.float32) + np.random.normal(0, random.uniform(1, 8), img.shape), 0, 255).astype(np.uint8)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, random.randint(45, 90)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


# ---------------------------------------------------------------------------
# Generadores de muestras
# ---------------------------------------------------------------------------
def muestra_moneda(crop, fondos):
    """Moneda recortada + girada + escalada + inclinada, sobre un fondo aleatorio."""
    S = crop.shape[0]
    # mascara circular de la moneda (con borde suave)
    mask = np.zeros((S, S), np.float32)
    cv2.circle(mask, (S // 2, S // 2), int(S * FRACCION_MONEDA / 2 * 1.03), 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), 2.0)

    f = random.uniform(0.36, 0.86)                  # fraccion del cuadro que ocupa la moneda
    esc = f * LADO / (S * FRACCION_MONEDA)
    tita = np.deg2rad(random.uniform(0, 360))       # giro de la moneda
    fi = np.deg2rad(random.uniform(0, 180))         # eje de inclinacion
    inc = random.uniform(0.85, 1.0)                 # 1 = de frente
    R = lambda a: np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]], np.float32)
    A = esc * R(fi) @ np.diag([1.0, inc]).astype(np.float32) @ R(-fi) @ R(tita)
    cx = LADO / 2 + random.uniform(-0.12, 0.12) * LADO
    cy = LADO / 2 + random.uniform(-0.12, 0.12) * LADO
    t = np.array([cx, cy], np.float32) - A @ np.array([S / 2, S / 2], np.float32)
    M = np.hstack([A, t[:, None]])

    moneda = cv2.warpAffine(crop, M, (LADO, LADO), flags=cv2.INTER_AREA if esc < 1 else cv2.INTER_LINEAR)
    alfa = cv2.warpAffine(mask, M, (LADO, LADO))[..., None]

    bg = fondo(fondos).astype(np.float32)
    # sombra suave debajo de la moneda
    sombra = cv2.GaussianBlur(np.roll(alfa[..., 0], (4, 4), (0, 1)), (0, 0), 6)[..., None]
    bg *= 1 - 0.30 * sombra
    out = bg * (1 - alfa) + moneda.astype(np.float32) * alfa
    return fotometria(np.clip(out, 0, 255).astype(np.uint8))


def muestra_fondo(fondos):
    return fotometria(fondo(fondos))


def muestra_original(crop):
    """Foto tal cual (con su fondo real), solo girada/iluminada: para validacion."""
    S = crop.shape[0]
    M = cv2.getRotationMatrix2D((S / 2, S / 2), random.uniform(0, 360), random.uniform(0.85, 1.15))
    img = cv2.warpAffine(crop, M, (S, S), borderMode=cv2.BORDER_REFLECT_101)
    img = cv2.resize(img, (LADO, LADO), interpolation=cv2.INTER_AREA)
    return fotometria(img)


# ---------------------------------------------------------------------------
def leer(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def guardar(img, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ruta), img, [cv2.IMWRITE_JPEG_QUALITY, 92])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validar", action="store_true", help="aparta 1 foto por moneda para una prueba honesta")
    ap.add_argument("--variantes", type=int, default=70, help="variantes de entrenamiento por foto")
    ap.add_argument("--fondos", type=int, default=260, help="imagenes de fondo (sin moneda) de entrenamiento")
    ap.add_argument("--semilla", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.semilla)
    np.random.seed(args.semilla)

    todos_fondos = sorted((DIR_REF / "fondos").glob("*.jpg"))
    if not todos_fondos:
        raise SystemExit("[X] Faltan imagenes en referencias/fondos/")
    if args.validar:
        f_train = [leer(p) for p in todos_fondos if p.stem.split("_")[0] not in FONDOS_APARTADOS]
        f_val = [leer(p) for p in todos_fondos if p.stem.split("_")[0] in FONDOS_APARTADOS]
    else:
        f_train = [leer(p) for p in todos_fondos]
        f_val = f_train

    if config.DIR_DATASET.exists():
        shutil.rmtree(config.DIR_DATASET)

    print(f"Modo: {'VALIDACION HONESTA (fotos apartadas)' if args.validar else 'FINAL (todas las fotos)'}\n")
    for clase in config.CLASES_MONEDA:
        fotos = sorted((DIR_REF / clase).glob("*.jpg"))
        if not fotos:
            raise SystemExit(f"[X] No hay fotos en referencias/{clase}/")
        if args.validar:
            val_f = [p for p in fotos if p.stem in APARTADAS]
            tr_f = [p for p in fotos if p.stem not in APARTADAS]
        else:
            val_f = tr_f = fotos
        for p in tr_f:
            crop = leer(p)
            for i in range(args.variantes):
                guardar(muestra_moneda(crop, f_train), config.DIR_DATASET / "train" / clase / f"{p.stem}_{i:03d}.jpg")
        for p in val_f:
            crop = leer(p)
            for i in range(12):
                img = muestra_original(crop) if args.validar else muestra_moneda(crop, f_val)
                guardar(img, config.DIR_DATASET / "val" / clase / f"{p.stem}_{i:03d}.jpg")
        print(f"  {config.CLASES[clase][0]:<16} entrena con {len(tr_f)} fotos"
              f"{'  | valida con ' + ', '.join(p.stem for p in val_f) if args.validar else ''}")

    for i in range(args.fondos):
        guardar(muestra_fondo(f_train), config.DIR_DATASET / "train" / config.CLASE_FONDO / f"fondo_{i:03d}.jpg")
    for i in range(60):
        guardar(muestra_fondo(f_val) if not args.validar else fotometria(cv2.resize(random.choice(f_val), (LADO, LADO))),
                config.DIR_DATASET / "val" / config.CLASE_FONDO / f"fondo_{i:03d}.jpg")
    print(f"  {'Sin moneda':<16} {args.fondos} fondos de entrenamiento")
    print("\nListo. Ahora corre:  python 02_entrenar.py --ya-preparado")


if __name__ == "__main__":
    main()
