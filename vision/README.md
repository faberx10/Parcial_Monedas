# Reconocimiento de monedas con ESP32-CAM — Grupo 3

La ESP32-CAM transmite video por WiFi y el PC hace el trabajo pesado: un modelo YOLO entrenado con **tus** monedas reconoce cuál es, un contador la registra una sola vez y una interfaz web lo muestra todo en tiempo real.

```
ESP32-CAM ──WiFi (MJPEG)──► PC: modelo YOLO ──► contador ──► interfaz web (localhost:8000)
```

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `config.py` | IP de la ESP32, clases, umbrales. **Lo único que normalmente editas.** |
| `camara.py` | Lee el video de la ESP32 sin acumular retraso |
| `contador.py` | Reglas para contar cada moneda una sola vez |
| `01_capturar_dataset.py` | Toma las fotos de entrenamiento |
| `02_entrenar.py` | Entrena el modelo y muestra qué tan preciso quedó |
| `03_interfaz.py` | Servidor de la interfaz en tiempo real |
| `static/index.html` | La interfaz (estilo oscuro fintech) |

Las 8 clases que reconoce: $1.000 nueva, $500 nueva, $500 antigua, $200 nueva, $200 antigua, $100 nueva, $100 antigua, y **fondo** (sin moneda). La clase fondo es necesaria: sin ella el modelo siempre "vería" alguna moneda aunque no haya nada.

---

## Camino rapido: entrenar SOLO con fotos de referencia (sin capturar con la ESP32)

Ya viene todo listo en `referencias/` (una carpeta por moneda, con fotos de ambas caras, y `fondos/` con superficie sin moneda).

```
python 00_importar_referencias.py --validar     # prueba honesta (aparta 1 foto por moneda)
python 02_entrenar.py --ya-preparado --epocas 20
python 00_importar_referencias.py               # dataset final con TODAS las fotos
python 02_entrenar.py --ya-preparado --epocas 20
python 03_interfaz.py
```

- El generador recorta cada moneda y la pega sobre fondos distintos, con giro, tamano, inclinacion, luz y ruido, para que el modelo reconozca monedas con la camara de la ESP32 aunque nunca haya visto sus fotos.
- Para mejorar: agrega mas fotos a `referencias/<moneda>/` (moneda centrada ocupando ~74 % del cuadrado) y vuelve a correr los comandos. Si algo falla en vivo, agrega tambien fotos de la propia ESP32-CAM (`01_capturar_dataset.py` guarda en `dataset_crudo/`, que puedes copiar a `referencias/`).
- Los fondos de `referencias/fondos/` son la tela de las fotos. Si tu superficie real es otra, agrega ahi 10-20 fotos de esa superficie vacia.

---

## Paso 1 — Montaje físico (lo que más influye en la precisión)

1. **Cámara fija apuntando hacia abajo**, a la altura donde se vea nítida una moneda (unos 10–15 cm). Usa un soporte, no la sostengas con la mano: la distancia debe ser siempre la misma.
2. **Fondo liso y mate**, de un solo color que contraste con el metal: cartulina negra o azul oscura mate. Nada brillante ni con dibujos.
3. **Luz difusa y constante**: una lámpara de lado con un papel blanco delante para suavizarla. El flash de la ESP32 queda apagado desde el código porque el metal lo refleja y "quema" la foto.
4. **Enfoca**: abre `http://192.168.1.14` en el navegador, dale Start Stream, pon una moneda y gira el anillo del lente hasta que se lean las letras. **Luego cierra esa pestaña** (la ESP32 solo atiende un video a la vez; si la dejas abierta, los scripts no reciben imagen).

## Paso 2 — Un cambio en el sketch de Arduino

En `CameraWebServer.ino` busca este bloque y cambia `FRAMESIZE_QVGA` por `FRAMESIZE_VGA` (640×480, más detalle para distinguir antigua de nueva):

```cpp
  if (config.pixel_format == PIXFORMAT_JPEG) {
    s->set_framesize(s, FRAMESIZE_VGA);
  }
```

Sube el sketch como siempre (IO0 + RST → soltar IO0 → Subir) y después aliméntala con el **cargador de pared**.

## Paso 3 — Instalar Python (una sola vez)

En el **Anaconda Prompt**, dentro de la carpeta `vision`:

```
conda activate monedas_g3
```

Instala PyTorch con soporte para tu RTX 3050. Entra a https://pytorch.org/get-started/locally/, elige *Stable · Windows · Pip · Python · CUDA* (la versión CUDA más alta que aparezca) y copia el comando. Se ve así:

```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

Verifica que detecte la GPU (debe decir `True`):

```
python -c "import torch; print(torch.cuda.is_available())"
```

Instala el resto:

```
pip install -r requirements_vision.txt
```

## Paso 4 — Probar la interfaz sin nada conectado

```
python 03_interfaz.py --demo
```

Abre **http://localhost:8000**. Verás monedas simuladas apareciendo y el contador subiendo. Sirve para confirmar que la instalación quedó bien. Ctrl+C para cerrar.

## Paso 5 — Capturar el dataset

Revisa que `ESP32_IP` en `config.py` sea la IP actual de tu cámara, y ejecuta:

```
python 01_capturar_dataset.py
```

Se abre una ventana con el video y un **círculo guía**: la moneda siempre va dentro del círculo.

| Tecla | Acción |
|---|---|
| `1` `2` `3` `4` `5` `6` `7` | Elige la moneda y toma 1 foto (1=$1000, 2=$500 N, 3=$500 A, 4=$200 N, 5=$200 A, 6=$100 N, 7=$100 A) |
| `0` | Clase fondo (sin moneda), 1 foto |
| `R` | Ráfaga ON/OFF: ~4 fotos por segundo de la clase elegida (descarta las movidas) |
| `Q` | Salir y ver el resumen |

**Receta por cada moneda (meta: 150 fotos):**
1. Pulsa su número una vez (queda elegida) y activa la ráfaga con `R`.
2. **Cara 1**: gira la moneda despacio con la punta de un palillo, muévela un poco dentro del círculo. ~75 fotos.
3. `R` para pausar, voltéala, `R` otra vez. **Cara 2**: lo mismo, ~75 fotos.
4. `R` para detener.

**Fondo (150 fotos):** el círculo vacío, cambiando un poco la luz. Si tienes más de una moneda del mismo tipo, fotografía varias: el desgaste cambia y el modelo aprende mejor.

El panel de la derecha muestra cuántas llevas; se pone verde al llegar a 150.

## Paso 6 — Entrenar

```
python 02_entrenar.py
```

Con la GPU tarda unos minutos. Al final imprime la **exactitud en validación** y una matriz de confusión. La meta es **≥ 97 %**. Si alguna moneda se confunde con otra (lo típico: antigua ↔ nueva de la misma denominación), el script te dice cuál: captura más fotos de esas dos y vuelve a entrenar.

## Paso 7 — Usar el sistema

```
python 03_interfaz.py
```

Abre **http://localhost:8000**. Pon una moneda en el círculo:

- El círculo del video se pone **dorado** y se va llenando mientras confirma (6 frames seguidos iguales).
- Cuando la registra se pone **verde**, suma al contador, aparece en "Últimas monedas registradas" y se guarda la foto en `capturas/<moneda>/`.
- **Retira la moneda** para que se "rearme" y cuente la siguiente. Así nunca cuenta dos veces la misma.

Puedes abrir la interfaz desde el celular en la misma red: `http://<IP-de-tu-PC>:8000`.

## Ajustes finos (`config.py`)

| Variable | Qué cambia |
|---|---|
| `UMBRAL_CONFIANZA` (0.85) | Súbelo si cuenta monedas equivocadas; bájalo si le cuesta aceptar monedas correctas |
| `FRAMES_ESTABLES` (6) | Más alto = más seguro pero más lento en confirmar |
| `FRAMES_VACIO` (5) | Frames de fondo necesarios para rearmar el contador |
| `vflip` en `AJUSTES_CAMARA` | Pon 0 si la imagen sale al revés |

## Problemas comunes

| Síntoma | Solución |
|---|---|
| "sin conexion... reintentando" | IP equivocada en `config.py`, o tienes la página de la ESP32 abierta en el navegador (ciérrala) |
| Imagen que se congela o reinicios | Alimentación: usa el cargador de pared, no el USB del PC |
| Se confunde antigua con nueva | Más fotos de ambas, ambas caras, y revisa el enfoque |
| Cuenta la moneda al ponerla y al quitarla | Sube `FRAMES_ESTABLES` o captura más fotos de fondo |
| `torch.cuda.is_available()` da False | Reinstala torch con el comando CUDA de pytorch.org (no el de pip normal) |

## Personalizar la interfaz

Todos los colores están al principio de `static/index.html`, en `:root`. Cambiando esas líneas cambias todo el tema:

- `--gold` y `--gold-2`: color de acento (prueba cian `#38BDF8` / `#7DD3FC` para un look más tecnológico).
- `--bg`, `--panel`: fondo y tarjetas.
- El objeto `ESTILO` en el `<script>` define el color de cada moneda dibujada; ajústalo para que se parezca a las reales.
