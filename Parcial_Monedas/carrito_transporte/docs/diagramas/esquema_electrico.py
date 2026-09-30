"""
Esquema eléctrico del carrito de transporte (Grupo 3).
Genera docs/img/esquema_electrico.svg (y .png si está instalado cairosvg).

    python esquema_electrico.py
"""
from pathlib import Path

SALIDA = Path(__file__).resolve().parent.parent / "img"
SALIDA.mkdir(exist_ok=True)

W, H = 1420, 1060
el = []  # elementos SVG

TXT = "#111827"
GRIS = "#6b7280"


def linea(pts, color=TXT, ancho=2.2):
    p = " ".join(f"{x},{y}" for x, y in pts)
    el.append(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{ancho}" '
              f'stroke-linejoin="round" stroke-linecap="round"/>')


def punto(x, y):
    el.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{TXT}"/>')


def texto(x, y, s, tam=15, anchor="start", peso="normal", color=TXT, italica=False):
    est = ' font-style="italic"' if italica else ""
    for i, linea_txt in enumerate(s.split("\n")):
        el.append(f'<text x="{x}" y="{y + i * (tam + 4)}" font-size="{tam}" text-anchor="{anchor}" '
                  f'font-weight="{peso}" fill="{color}"{est}>{linea_txt}</text>')


def caja(x, y, w, h, titulo, subtitulo):
    el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#f8fafc" '
              f'stroke="{TXT}" stroke-width="2.5"/>')
    texto(x + w / 2, y + h / 2 - 8, titulo, 19, "middle", "bold")
    texto(x + w / 2, y + h / 2 + 18, subtitulo, 13, "middle", color=GRIS)


def pin(x, y, nombre, lado, largo=26):
    """Pin de un bloque: pequeño segmento hacia afuera y su nombre por dentro."""
    if lado == "der":
        linea([(x, y), (x + largo, y)])
        texto(x - 8, y + 5, nombre, 15, "end", "bold")
        return (x + largo, y)
    if lado == "izq":
        linea([(x, y), (x - largo, y)])
        texto(x + 8, y + 5, nombre, 15, "start", "bold")
        return (x - largo, y)
    if lado == "abajo":
        linea([(x, y), (x, y + largo)])
        texto(x, y - 10, nombre, 15, "middle", "bold")
        return (x, y + largo)


def motor(cx, cy, etiqueta):
    el.append(f'<circle cx="{cx}" cy="{cy}" r="24" fill="#ffffff" stroke="{TXT}" stroke-width="2.4"/>')
    texto(cx, cy + 7, "M", 20, "middle", "bold")
    texto(cx + 32, cy - 6, etiqueta, 13, "start")


def bateria(x, y_sup, y_inf, etiqueta, lado_etq="der"):
    """Batería vertical de 2 celdas entre y_sup (+) e y_inf (−)."""
    m = (y_sup + y_inf) / 2
    linea([(x, y_sup), (x, m - 20)])
    for dy, ancho_placa, grosor in [(-20, 26, 2.4), (-12, 14, 4), (0, 26, 2.4), (8, 14, 4)]:
        el.append(f'<line x1="{x - ancho_placa}" y1="{m + dy}" x2="{x + ancho_placa}" y2="{m + dy}" '
                  f'stroke="{TXT}" stroke-width="{grosor}"/>')
    linea([(x, m + 8), (x, y_inf)])
    texto(x - 34, m - 20, "+", 16, "middle", "bold")
    if lado_etq == "der":
        texto(x + 38, m - 14, etiqueta, 14, "start")
    else:
        texto(x - 44, m - 14, etiqueta, 14, "end")


def tierra(x, y):
    linea([(x, y), (x, y + 14)])
    for i, a in enumerate([20, 13, 6]):
        el.append(f'<line x1="{x - a}" y1="{y + 14 + i * 6}" x2="{x + a}" y2="{y + 14 + i * 6}" '
                  f'stroke="{TXT}" stroke-width="2.2"/>')


# ------------------------------------------------------------------ Título
texto(40, 48, "Carrito de transporte — Esquema eléctrico", 26, peso="bold")
texto(40, 76, "Sistema de Logística de Monedas Inteligentes · Grupo 3 · Micros y Laboratorio · UMNG", 15, color=GRIS)

# ------------------------------------------------------------------ Bloques
EX, EY, EW, EH = 300, 130, 230, 470       # ESP32
LX, LY, LW, LH = 780, 130, 250, 470       # L298N
caja(EX, EY, EW, EH, "U1 · ESP32", "DevKit V1 (30 pines)")
caja(LX, LY, LW, LH, "U2 · L298N", "Puente H doble")

SENALES = [  # (pin ESP32, pin L298N, color, función)
    ("D13", "ENA", "#d97706", "PWM velocidad izq."),
    ("D27", "IN1", "#15803d", "dirección izq. A"),
    ("D26", "IN2", "#2563eb", "dirección izq. B"),
    ("D25", "IN3", "#15803d", "dirección der. A"),
    ("D33", "IN4", "#2563eb", "dirección der. B"),
    ("D32", "ENB", "#d97706", "PWM velocidad der."),
]
Y0, PASO = 170, 56
for i, (pe, pl, col, func) in enumerate(SENALES):
    y = Y0 + i * PASO
    a = pin(EX + EW, y, pe, "der")
    b = pin(LX, y, pl, "izq")
    linea([a, b], col, 2.6)
    texto((a[0] + b[0]) / 2, y - 8, func, 12, "middle", color=GRIS, italica=True)

# GND de la ESP32 (lado derecho) → borne GND del L298N
Y_GND_E = 540
g_esp = pin(EX + EW, Y_GND_E, "GND", "der")

# Bornes de potencia del L298N (abajo)
X_VS, X_GND, X_5V = LX + 50, LX + 125, LX + 200
p_vs = pin(X_VS, LY + LH, "+12V", "abajo")
p_gnd = pin(X_GND, LY + LH, "GND", "abajo")
p_5v = pin(X_5V, LY + LH, "5V", "abajo")
texto(X_5V + 10, LY + LH + 48, "sin conexión\n(jumper 5V-EN puesto)", 12, color=GRIS)

# Batería de motores BT1 + conector J1
linea([p_vs, (X_VS, 640)])
el.append(f'<circle cx="{X_VS}" cy="650" r="9" fill="#ffffff" stroke="{TXT}" stroke-width="2.2"/>')
el.append(f'<circle cx="{X_VS}" cy="668" r="9" fill="#ffffff" stroke="{TXT}" stroke-width="2.2"/>')
texto(X_VS - 22, 657, "J1", 14, "end", "bold")
texto(X_VS - 22, 675, "conector = ON/OFF", 12, "end", color=GRIS)
bateria(X_VS, 677, 810, "BT1\nNi-MH 7,2 V\n500 mAh", "izq")
linea([(X_VS, 810), (X_GND, 810)])
punto(X_GND, 810)

# Tierra común: GND de la ESP32 → borne GND del L298N (mismo nodo que el − de BT1)
Y_NODO = 860
linea([g_esp, (650, Y_GND_E), (650, Y_NODO), (X_GND, Y_NODO)], TXT, 2.6)
linea([p_gnd, (X_GND, Y_NODO)])
punto(X_GND, Y_NODO)
texto(662, Y_NODO - 10, "GND común (obligatorio)", 13, peso="bold")
tierra(X_GND, Y_NODO)

# Motores (2 en paralelo por lado)
def lado_motores(y_a, y_b, n1, n2, titulo):
    xa = LX + LW
    pa = pin(xa, y_a, "OUT" + n1[0], "der")
    pb = pin(xa, y_b, "OUT" + n1[1], "der")
    x1, x2 = 1140, 1290
    linea([pa, (x2, y_a)])
    linea([pb, (x2, y_b)])
    cy = (y_a + y_b) / 2
    for x, et in [(x1, n2[0]), (x2, n2[1])]:
        linea([(x, y_a), (x, cy - 24)])
        linea([(x, cy + 24), (x, y_b)])
        motor(x, cy, et)
    punto(x1, y_a)
    punto(x1, y_b)
    texto((x1 + x2) / 2, y_a - 14, titulo, 14, "middle", "bold")

lado_motores(200, 300, "12", ("M1\ndel.", "M2\ntras."), "Lado izquierdo")
lado_motores(420, 520, "34", ("M3\ndel.", "M4\ntras."), "Lado derecho")
texto(1215, 580, "Motorreductores TT 3–6 V (1:48)", 12, "middle", color=GRIS)

# Power bank BT2 → ESP32
Y_VIN, Y_GNDI = 300, 470
p_vin = pin(EX, Y_VIN, "VIN (USB)", "izq")
p_gi = pin(EX, Y_GNDI, "GND", "izq")
XB = 170
linea([p_vin, (XB, Y_VIN), (XB, 330)])
bateria(XB, 330, 440, "BT2\nPower bank\n5 V (USB)", "izq")
linea([(XB, 440), (XB, Y_GNDI), p_gi])

# ------------------------------------------------------------------ Notas
notas = [
    "Notas",
    "1. Jumpers ENA y ENB del L298N retirados: la velocidad se controla por PWM desde D13 y D32.",
    "2. Los dos motores de cada lado se conectan en paralelo a la misma salida del puente H.",
    "3. La ESP32 se alimenta aparte (power bank) para evitar reinicios por caídas de tensión de los motores.",
    "4. Sin interruptor: conectar / desconectar J1 enciende y apaga la etapa de potencia.",
]
el.append(f'<rect x="40" y="{H - 150}" width="720" height="130" rx="6" fill="#f1f5f9" stroke="#cbd5e1"/>')
for i, n in enumerate(notas):
    texto(56, H - 122 + i * 24, n, 13 if i else 14, peso="bold" if i == 0 else "normal")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       f'font-family="DejaVu Sans, Arial, Helvetica, sans-serif">'
       f'<rect width="100%" height="100%" fill="#ffffff"/>' + "".join(el) + "</svg>")
(SALIDA / "esquema_electrico.svg").write_text(svg, encoding="utf-8")

try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(SALIDA / "esquema_electrico.png"), scale=1.5)
except ImportError:
    print("cairosvg no instalado: solo se generó el SVG")

print("Esquema guardado en", SALIDA)
