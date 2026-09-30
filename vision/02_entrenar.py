"""
02_entrenar.py
==============
Entrena el clasificador de monedas con las fotos de dataset_crudo/.

Pasos que hace:
  1. Revisa que cada clase tenga fotos suficientes.
  2. Separa 80% entrenamiento / 20% validacion (siempre igual, semilla fija).
  3. Multiplica el set de entrenamiento con rotaciones aleatorias: una
     moneda puede llegar girada en cualquier angulo y el modelo debe saberlo.
  4. Entrena YOLO (clasificacion) en la GPU si esta disponible.
  5. Evalua en validacion y muestra la matriz de confusion por clase.
  6. Guarda el mejor modelo en modelos/monedas.pt

Uso:
    python 02_entrenar.py              # 40 epocas (por defecto)
    python 02_entrenar.py --epocas 60
"""

import argparse
import random
import shutil

import cv2
import numpy as np

import config

MIN_FOTOS = 40
ROTACIONES_EXTRA = 3        # copias rotadas por cada foto de entrenamiento
SEMILLA = 42
IMGSZ = 224


def preparar_dataset():
    if config.DIR_DATASET.exists():
        shutil.rmtree(config.DIR_DATASET)
    rng = random.Random(SEMILLA)
    resumen = {}
    for clase in config.CLASES:
        fotos = sorted((config.DIR_DATASET_CRUDO / clase).glob("*.jpg"))
        if len(fotos) < MIN_FOTOS:
            raise SystemExit(f"[X] {clase}: solo {len(fotos)} fotos "
                             f"(minimo {MIN_FOTOS}). Captura mas con 01_capturar_dataset.py")
        rng.shuffle(fotos)
        n_val = max(8, int(len(fotos) * 0.2))
        grupos = {"val": fotos[:n_val], "train": fotos[n_val:]}
        for split, lista in grupos.items():
            destino = config.DIR_DATASET / split / clase
            destino.mkdir(parents=True, exist_ok=True)
            for f in lista:
                shutil.copy2(f, destino / f.name)
                if split == "train":
                    img = cv2.imread(str(f))
                    for k in range(ROTACIONES_EXTRA):
                        ang = rng.uniform(0, 360)
                        rot = rotar(img, ang)
                        cv2.imwrite(str(destino / f"{f.stem}_r{k}.jpg"), rot)
        resumen[clase] = (len(grupos["train"]), n_val)
    print("\nDataset preparado (train originales / val):")
    for c, (t, v) in resumen.items():
        print(f"  {config.CLASES[c][0]:<16} {t:>4} / {v:<4} "
              f"(+{t * ROTACIONES_EXTRA} rotadas)")


def rotar(img, angulo):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angulo, 1.0)
    return cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)


def entrenar(epocas):
    import torch
    from ultralytics import YOLO

    dispositivo = 0 if torch.cuda.is_available() else "cpu"
    print(f"\nEntrenando en: {'GPU ' + torch.cuda.get_device_name(0) if dispositivo == 0 else 'CPU (sera mas lento)'}")

    modelo = YOLO("yolo11n-cls.pt")   # se descarga solo la primera vez
    modelo.train(
        data=str(config.DIR_DATASET),
        epochs=epocas,
        imgsz=IMGSZ,
        batch=32,
        device=dispositivo,
        patience=15,
        fliplr=0.0,          # una moneda espejada no existe en la realidad
        hsv_h=0.01, hsv_s=0.4, hsv_v=0.4,   # tolerancia a cambios de luz
        project=str(config.RAIZ / "runs"),
        name="monedas",
        exist_ok=True,
        verbose=False,
    )
    mejor = config.RAIZ / "runs" / "monedas" / "weights" / "best.pt"
    config.DIR_MODELOS.mkdir(exist_ok=True)
    shutil.copy2(mejor, config.RUTA_MODELO)
    print(f"\nModelo guardado en {config.RUTA_MODELO}")
    return YOLO(str(config.RUTA_MODELO))


def evaluar(modelo):
    nombres = modelo.names                    # {indice: nombre_clase}
    idx = {n: i for i, n in nombres.items()}
    k = len(nombres)
    matriz = np.zeros((k, k), dtype=int)
    for clase in config.CLASES:
        for f in (config.DIR_DATASET / "val" / clase).glob("*.jpg"):
            r = modelo.predict(str(f), imgsz=IMGSZ, verbose=False)[0]
            matriz[idx[clase], int(r.probs.top1)] += 1

    print("\n=== Matriz de confusion (filas = real, columnas = predicho) ===")
    cortos = [nombres[i][:9] for i in range(k)]
    print(" " * 14 + " ".join(f"{c:>9}" for c in cortos))
    for i in range(k):
        print(f"{nombres[i]:<14}" + " ".join(f"{v:>9}" for v in matriz[i]))
    exactitud = np.trace(matriz) / matriz.sum()
    print(f"\nExactitud en validacion: {exactitud:.1%}")
    for i in range(k):
        total = matriz[i].sum()
        if total and matriz[i, i] < total:
            errores = {nombres[j]: int(matriz[i, j]) for j in range(k)
                       if j != i and matriz[i, j]}
            print(f"  [!] {nombres[i]} se confundio con: {errores}")
    if exactitud < 0.97:
        print("\nSugerencia: captura mas fotos de las clases que se confunden "
              "(ambas caras, distintos giros) y vuelve a entrenar.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epocas", type=int, default=40)
    ap.add_argument("--ya-preparado", action="store_true",
                    help="no reconstruir dataset/ (lo dejo listo 00_importar_referencias.py)")
    args = ap.parse_args()
    if not args.ya_preparado:
        preparar_dataset()
    evaluar(entrenar(args.epocas))
