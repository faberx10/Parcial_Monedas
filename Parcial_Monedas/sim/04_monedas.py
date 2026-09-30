"""
04_monedas.py
=============
Sistema de Logistica de Monedas Inteligentes - Grupo 3
FASE 3: monedas -- spawn, transporte por codigo y clasificacion.

Las monedas NO se mueven con un joint: se generan como cuerpos rigidos
sueltos (cilindros) y cada frame se les fuerza una velocidad horizontal
segun en que tramo de banda esten paradas. Eso es lo normal en PyBullet
para simular una cinta transportadora -- el link de la banda queda fijo,
lo que se mueve es lo que esta encima.

Recorrido (ver nota en el chat sobre el sentido de cada tramo):
    spawn (cerca de la maquina, sobre cinta_1) --( -X )--> cinta_1
    --( -Y )--> cinta_2 --( +X )--> cinta_3 --> zona del dron

Clasificacion: al pasar por la zona de brazo1 (X entre 1.3 y 1.7 sobre
cinta_1), cada moneda se identifica por su radio y se "traslada" al
contenedor que le corresponde (200 / 500 / 1000). Esto representa el
resultado del agarre, no la animacion del brazo en si -- animar el
brazo real (moverlo con IK hasta la moneda) es un refinamiento que
se puede agregar despues sobre esta misma base.

Uso:
    python sim/04_monedas.py
"""

import os
import random
import time
import pybullet as p
import pybullet_data

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URDF_PLANTA = os.path.join(RAIZ, "urdf", "planta_monedas_v3.urdf")
URDF_DRON = os.path.join(RAIZ, "urdf", "dron.urdf")
POSICION_MUELLE = [3.35, -4.0, 0.66]

Z_BANDA = 0.605          # superficie util de las tres cintas
VELOCIDAD_BANDA = 0.35   # m/s -- avance de las monedas sobre la banda

# Grupo de colision propio para las monedas: mascara SIN su propio bit,
# asi cada moneda deja de chocar con otras monedas pero sigue chocando
# con todo lo demas (grupo/mascara por defecto = 1 / -1 = "todo").
GROUP_MONEDA = 2
MASK_MONEDA = ~GROUP_MONEDA & 0xFFFF

INTERVALO_SPAWN = 1.8    # segundos entre monedas nuevas (antes 1.2 -- muy
                          # seguido para la velocidad de banda actual, generaba
                          # atasco cerca de la maquina; ver tambien GROUP_MONEDA)
PUNTO_SPAWN = [2.7, 0.0, 0.85]  # justo bajo la rampa de salida de la maquina (ver calculo en el chat: rampa en X=2.74)

# --- denominaciones: radio (m), alto (m), color RGBA, contenedor destino ---
# 200 y 500 se clasifican en brazo1 (sobre cinta_1). 1000 se deja pasar de
# largo en brazo1 a proposito y se clasifica en brazo2 (sobre cinta_3), asi
# recorre las tres bandas completas antes de llegar a su contenedor.
DENOMINACIONES = {
    "200":  {"radio": 0.0125, "alto": 0.018, "color": [0.72, 0.45, 0.20, 1], "contenedor_xy": (1.00, -1.35), "estacion": "brazo1"},
    "500":  {"radio": 0.0150, "alto": 0.020, "color": [0.75, 0.75, 0.78, 1], "contenedor_xy": (1.50, -1.35), "estacion": "brazo1"},
    "1000": {"radio": 0.0175, "alto": 0.022, "color": [0.85, 0.70, 0.25, 1], "contenedor_xy": (3.00, -4.55), "estacion": "brazo2"},
}

# --- tramos: caja de captura + eje de avance + centrado en el eje quieto ---
# Antes solo empujaba en el eje de avance y dejaba el otro en 0 -- eso deja
# a la moneda pegada en el borde por donde entro al tramo, que puede caer
# fuera del ancho fisico real de la banda (30cm). Ahora ademas se aplica
# una fuerza de centrado hacia el eje central de esa banda, para que la
# moneda viaje SIEMPRE por el centro fisico, sin importar por donde entro.
K_CENTRADO = 4.0           # ganancia proporcional del centrado
VEL_CENTRADO_MAX = 0.6    # tope de velocidad de centrado (m/s)

TRAMOS = [
    # cinta_2 primero: es el tramo angosto, hay que descartarlo antes que
    # cinta_1/cinta_3 para no confundir la esquina.
    {"nombre": "cinta_2", "caja": (-1.2, -0.8, -4.0, 0.2),
     "eje_avance": "y", "vel_avance": -VELOCIDAD_BANDA, "centro": -1.0},
    {"nombre": "cinta_1", "caja": (-1.0, 3.0, -0.2, 0.2),
     "eje_avance": "x", "vel_avance": -VELOCIDAD_BANDA, "centro": 0.0},
    # cinta_3 se extiende un poco mas alla del borde fisico de la banda
    # (X=3.0) para que la moneda no pierda el empuje antes de llegar a
    # la plataforma del dron, en X=3.35.
    {"nombre": "cinta_3", "caja": (-1.0, 3.5, -4.2, -3.8),
     "eje_avance": "x", "vel_avance": VELOCIDAD_BANDA, "centro": -4.0},
]

ZONA_BRAZO1 = (1.3, 1.7)     # rango de X sobre cinta_1 donde brazo1 "agarra"
ZONA_BRAZO2 = (2.3, 2.7)     # rango de X sobre cinta_3 donde brazo2 "agarra"


def velocidad_para(x, y):
    for tramo in TRAMOS:
        xmin, xmax, ymin, ymax = tramo["caja"]
        if xmin <= x <= xmax and ymin <= y <= ymax:
            avance = tramo["vel_avance"]
            if tramo["eje_avance"] == "x":
                # avanza en X; se centra en Y hacia el eje de esta banda
                v_centrado = K_CENTRADO * (tramo["centro"] - y)
                v_centrado = max(-VEL_CENTRADO_MAX, min(VEL_CENTRADO_MAX, v_centrado))
                return avance, v_centrado
            else:
                # avanza en Y; se centra en X hacia el eje de esta banda
                v_centrado = K_CENTRADO * (tramo["centro"] - x)
                v_centrado = max(-VEL_CENTRADO_MAX, min(VEL_CENTRADO_MAX, v_centrado))
                return v_centrado, avance
    return None  # fuera de cualquier banda


def crear_moneda(denominacion):
    d = DENOMINACIONES[denominacion]
    col = p.createCollisionShape(p.GEOM_CYLINDER, radius=d["radio"], height=d["alto"])
    vis = p.createVisualShape(p.GEOM_CYLINDER, radius=d["radio"], length=d["alto"],
                              rgbaColor=d["color"])
    # Sin rotacion: el eje del cilindro en pybullet/URDF va sobre Z por
    # convencion, asi que con orientacion identidad la moneda YA queda
    # acostada plana (como una moneda real), apoyada en su cara circular.
    # (Version anterior la giraba 90 grados y quedaba parada de canto
    # como una rueda -- rodaba y se desviaba en trayectos largos.)
    cuerpo = p.createMultiBody(baseMass=0.005,
                               baseCollisionShapeIndex=col,
                               baseVisualShapeIndex=vis,
                               basePosition=PUNTO_SPAWN,
                               baseOrientation=p.getQuaternionFromEuler([0, 0, 0]))
    p.changeDynamics(cuerpo, -1, lateralFriction=0.9, rollingFriction=0.001,
                     linearDamping=0.1, angularDamping=0.6)
    # Las monedas no chocan entre si (si siguen chocando con bandas, placas,
    # contenedores, piso y dron). Con el intervalo de spawn actual varias
    # monedas conviven cerca de la maquina al mismo tiempo; sin este filtro
    # se empujan unas a otras y se atascan justo ahi.
    p.setCollisionFilterGroupMask(cuerpo, -1,
                                  collisionFilterGroup=GROUP_MONEDA,
                                  collisionFilterMask=MASK_MONEDA)
    return cuerpo, denominacion


def main():
    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.loadURDF("plane.urdf")

    planta = p.loadURDF(URDF_PLANTA, basePosition=[0, 0, 0], useFixedBase=True)
    dron = p.loadURDF(URDF_DRON, basePosition=POSICION_MUELLE, useFixedBase=False)
    p.createConstraint(dron, -1, -1, -1, p.JOINT_FIXED, [0, 0, 0], [0, 0, 0], POSICION_MUELLE)

    # Los brazos estan en reposo (no animados todavia -- "agarran" por
    # teletransporte, no de verdad) pero su geometria SI tiene colision
    # fisica, y queda parada justo sobre el camino de la banda. Cualquier
    # moneda que deba pasar de largo (las de $1000 en brazo1, por ejemplo)
    # chocaria contra el brazo como si fuera una pared. Se desactiva la
    # colision moneda<->brazo para todos los links de brazo1 y brazo2;
    # el "agarre" sigue resolviendose por posicion, no por contacto fisico.
    links_brazos = []
    for i in range(p.getNumJoints(planta)):
        nombre_link = p.getJointInfo(planta, i)[12].decode("utf-8")
        if nombre_link.startswith("brazo1_") or nombre_link.startswith("brazo2_"):
            links_brazos.append(i)
    print(f"Colision desactivada moneda<->brazo en {len(links_brazos)} links de brazo1/brazo2.")

    p.resetDebugVisualizerCamera(cameraDistance=6.5, cameraYaw=0, cameraPitch=-55,
                                 cameraTargetPosition=[0.7, -2.0, 0.4])

    conteo = {"200": 0, "500": 0, "1000": 0}
    texto_conteo = p.addUserDebugText("", [1.0, 1.0, 1.5], [1, 1, 0], 1.3)

    def refrescar_texto():
        nonlocal texto_conteo
        msg = f"200: {conteo['200']}   500: {conteo['500']}   1000: {conteo['1000']}"
        texto_conteo = p.addUserDebugText(msg, [-2.5, 1.0, 2.0], [1, 1, 0], 1.4,
                                          replaceItemUniqueId=texto_conteo)

    monedas = []           # lista de (id, denominacion, clasificada?)
    siguiente_spawn = time.time()
    paso = 1 / 240

    print("Simulacion de monedas iniciada. Ctrl+C para cerrar.\n")
    try:
        while p.isConnected():
            ahora = time.time()

            # --- spawn periodico ---
            if ahora >= siguiente_spawn:
                den = random.choice(list(DENOMINACIONES.keys()))
                cid, den = crear_moneda(den)
                for link_idx in links_brazos:
                    p.setCollisionFilterPair(planta, cid, link_idx, -1, enableCollision=0)
                monedas.append([cid, den, False])
                siguiente_spawn = ahora + INTERVALO_SPAWN

            # --- mover cada moneda segun el tramo en que este ---
            for registro in monedas:
                cid, den, clasificada = registro
                if clasificada:
                    continue
                pos, _ = p.getBasePositionAndOrientation(cid)
                x, y, z = pos
                estacion_moneda = DENOMINACIONES[den]["estacion"]

                # clasificacion: cada denominacion solo se agarra en SU
                # estacion (brazo1 sobre cinta_1, o brazo2 sobre cinta_3).
                # Si no es su estacion, sigue de largo sobre la banda.
                en_brazo1 = (estacion_moneda == "brazo1" and
                            ZONA_BRAZO1[0] <= x <= ZONA_BRAZO1[1] and abs(y) < 0.2 and z < 0.9)
                en_brazo2 = (estacion_moneda == "brazo2" and
                            ZONA_BRAZO2[0] <= x <= ZONA_BRAZO2[1] and abs(y - (-4.0)) < 0.2 and z < 0.9)

                if en_brazo1 or en_brazo2:
                    cx, cy = DENOMINACIONES[den]["contenedor_xy"]
                    p.resetBasePositionAndOrientation(
                        cid, [cx + random.uniform(-0.03, 0.03),
                              cy + random.uniform(-0.03, 0.03), 0.55],
                        p.getQuaternionFromEuler([0, 0, 0]))
                    p.resetBaseVelocity(cid, linearVelocity=[0, 0, 0])
                    registro[2] = True
                    conteo[den] += 1
                    refrescar_texto()
                    continue

                vel = velocidad_para(x, y)
                if vel is not None and z < Z_BANDA + 0.05:
                    _, _, vz = p.getBaseVelocity(cid)[0]
                    p.resetBaseVelocity(cid, linearVelocity=[vel[0], vel[1], vz])

            p.stepSimulation()
            time.sleep(paso)
    except KeyboardInterrupt:
        pass
    finally:
        p.disconnect()
        print("\nConteo final:", conteo)


if __name__ == "__main__":
    main()
