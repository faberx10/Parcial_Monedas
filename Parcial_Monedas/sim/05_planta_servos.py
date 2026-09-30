"""
05_planta_servos.py
====================
Sistema de Logistica de Monedas Inteligentes - Grupo 3
Rediseno: banda unica recta + reconocimiento + 3 servomotores con paleta.

Reemplaza el sistema anterior (banda en L + brazos de 3 DOF). Cada
servo tiene asignada una sola denominacion. Cuando una moneda entra a
la zona de "reconocimiento" de un servo, el sistema ya sabe que
denominacion es (la genera el propio script) y decide: si coincide con
la denominacion de ese servo, la paleta gira y la empuja hacia su vaso;
si no coincide, la paleta se queda quieta y la moneda sigue de largo
hacia el siguiente servo.

El empuje combina dos cosas, igual que en el sistema anterior con los
brazos: la paleta SI se anima y tiene colision real (para que se vea el
movimiento), y ademas se le da un empujon de velocidad lateral directo
a la moneda mientras la paleta esta extendida -- as{i} el resultado es
confiable sin depender de que el contacto fisico paleta-moneda salga
perfecto en cada corrida.

Uso:
    python sim/05_planta_servos.py
"""

import os
import random
import time
import pybullet as p
import pybullet_data

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URDF_PLANTA = os.path.join(RAIZ, "urdf", "planta_servos_v4.urdf")
URDF_DRON = os.path.join(RAIZ, "urdf", "dron.urdf")
POSICION_DRON = [7.5, 0.0, 0.66]

Z_BANDA = 0.605
VELOCIDAD_BANDA = 0.35
K_CENTRADO = 3.0
VEL_CENTRADO_MAX = 0.5
INTERVALO_SPAWN = 1.8
PUNTO_SPAWN = [-0.45, 0.0, 0.85]   # bajo la rampa de la maquina (sin colision)

GROUP_MONEDA = 2
MASK_MONEDA = ~GROUP_MONEDA & 0xFFFF

# Rango fisico de la banda recta (una sola, sin esquinas ni placas)
BANDA_X = (-1.0, 7.0)
BANDA_Y = (-0.15, 0.15)

# --- denominaciones: radio, alto, color, servo asignado, X de su estacion ---
DENOMINACIONES = {
    "1000": {"radio": 0.0175, "alto": 0.022, "color": [0.85, 0.70, 0.25, 1], "servo": "servo_1000", "x_estacion": 1.5},
    "500":  {"radio": 0.0150, "alto": 0.020, "color": [0.75, 0.75, 0.78, 1], "servo": "servo_500",  "x_estacion": 3.5},
    "200":  {"radio": 0.0125, "alto": 0.018, "color": [0.72, 0.45, 0.20, 1], "servo": "servo_200",  "x_estacion": 5.5},
}

X_RECONOCIMIENTO = 0.3           # donde esta el gantry decorativo
ANCHO_ZONA_SERVO = 0.35          # +/- alrededor de cada x_estacion que activa el servo
ANGULO_RETRAIDO = 0.0
ANGULO_EXTENDIDO = 1.55          # ~89 grados, barre toda la banda
DURACION_EMPUJE = 1.0            # segundos que la paleta permanece activa
VEL_EMPUJE_LATERAL = 0.9         # m/s de empuje lateral directo hacia el vaso


def crear_moneda(denominacion):
    d = DENOMINACIONES[denominacion]
    col = p.createCollisionShape(p.GEOM_CYLINDER, radius=d["radio"], height=d["alto"])
    vis = p.createVisualShape(p.GEOM_CYLINDER, radius=d["radio"], length=d["alto"],
                              rgbaColor=d["color"])
    cuerpo = p.createMultiBody(baseMass=0.005,
                               baseCollisionShapeIndex=col,
                               baseVisualShapeIndex=vis,
                               basePosition=PUNTO_SPAWN,
                               baseOrientation=p.getQuaternionFromEuler([0, 0, 0]))
    p.changeDynamics(cuerpo, -1, lateralFriction=0.9, rollingFriction=0.001,
                     linearDamping=0.1, angularDamping=0.6)
    p.setCollisionFilterGroupMask(cuerpo, -1, collisionFilterGroup=GROUP_MONEDA,
                                  collisionFilterMask=MASK_MONEDA)
    return cuerpo, denominacion


def main():
    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.loadURDF("plane.urdf")

    planta = p.loadURDF(URDF_PLANTA, basePosition=[0, 0, 0], useFixedBase=True)
    dron = p.loadURDF(URDF_DRON, basePosition=POSICION_DRON, useFixedBase=False)
    p.createConstraint(dron, -1, -1, -1, p.JOINT_FIXED, [0, 0, 0], [0, 0, 0], POSICION_DRON)

    # localizar el joint de la paleta de cada servo por nombre
    joint_paleta = {}
    for i in range(p.getNumJoints(planta)):
        nombre = p.getJointInfo(planta, i)[1].decode("utf-8")
        for den, info in DENOMINACIONES.items():
            if nombre == f"j_{info['servo']}_paleta":
                joint_paleta[info["servo"]] = i
    print("Joints de paleta encontrados:", joint_paleta)
    assert len(joint_paleta) == 3, "No se encontraron los 3 servos -- revisa nombres en el URDF"

    p.resetDebugVisualizerCamera(cameraDistance=7.5, cameraYaw=0, cameraPitch=-45,
                                 cameraTargetPosition=[3.0, 0.3, 0.4])

    conteo = {"200": 0, "500": 0, "1000": 0}
    texto_conteo = p.addUserDebugText("", [0, 1.2, 1.6], [1, 1, 0], 1.3)

    def refrescar_texto():
        nonlocal texto_conteo
        msg = f"200: {conteo['200']}   500: {conteo['500']}   1000: {conteo['1000']}"
        texto_conteo = p.addUserDebugText(msg, [0, 1.2, 1.6], [1, 1, 0], 1.4,
                                          replaceItemUniqueId=texto_conteo)

    # estado de cada servo: None (inactivo) o el tiempo en que se activo
    activado_en = {info["servo"]: None for info in DENOMINACIONES.values()}

    monedas = []
    reconocidas = set()   # ids ya marcados en la estacion de reconocimiento
    siguiente_spawn = time.time()
    paso = 1 / 240

    print("Simulacion iniciada. Ctrl+C para cerrar.\n")
    try:
        while p.isConnected():
            ahora = time.time()

            if ahora >= siguiente_spawn:
                den = random.choice(list(DENOMINACIONES.keys()))
                cid, den = crear_moneda(den)
                monedas.append([cid, den, False, False])  # + empujando (persistente)
                siguiente_spawn = ahora + INTERVALO_SPAWN

            for registro in monedas:
                cid, den, clasificada, empujando = registro
                if clasificada:
                    continue
                pos, _ = p.getBasePositionAndOrientation(cid)
                x, y, z = pos

                # marca de reconocimiento (una vez, solo informativo)
                if cid not in reconocidas and x <= X_RECONOCIMIENTO and z < 0.9:
                    reconocidas.add(cid)
                    print(f"[reconocimiento] moneda ${den} detectada -> objetivo: {DENOMINACIONES[den]['servo']}")

                info = DENOMINACIONES[den]
                x_estacion = info["x_estacion"]

                # "empujando" es un estado que persiste una vez activado --
                # NO se vuelve a evaluar la condicion de entrada mientras
                # dure, porque empujar en Y haria que abs(y)<0.25 deje de
                # cumplirse a mitad de camino y la moneda "se saliera" de
                # su propia zona antes de llegar al vaso.
                if not empujando:
                    if abs(x - x_estacion) <= ANCHO_ZONA_SERVO and abs(y) < 0.25 and z < 0.9:
                        empujando = True
                        registro[3] = True
                en_su_zona = empujando

                if en_su_zona and activado_en[info["servo"]] is None:
                    activado_en[info["servo"]] = ahora

                if en_su_zona:
                    # empuje lateral directo: se frena el avance en X (la
                    # paleta "atrapa" la moneda) y se empuja hacia +Y, hacia
                    # el vaso, mientras esta dentro de la zona de su servo.
                    _, _, vz = p.getBaseVelocity(cid)[0]
                    p.resetBaseVelocity(cid, linearVelocity=[0, VEL_EMPUJE_LATERAL, vz])
                    if y >= 0.55:   # ya llego a la altura del vaso -> clasificada
                        registro[2] = True
                        conteo[den] += 1
                        refrescar_texto()
                        p.resetBaseVelocity(cid, linearVelocity=[0, 0, 0])
                    continue

                # avance normal sobre la banda (fuera de cualquier zona de servo)
                if BANDA_X[0] <= x <= BANDA_X[1] and abs(y) < 0.3 and z < Z_BANDA + 0.05:
                    v_centrado = max(-VEL_CENTRADO_MAX, min(VEL_CENTRADO_MAX, K_CENTRADO * (0.0 - y)))
                    _, _, vz = p.getBaseVelocity(cid)[0]
                    p.resetBaseVelocity(cid, linearVelocity=[VELOCIDAD_BANDA, v_centrado, vz])

            # animar cada paleta: extendida mientras este dentro de su
            # ventana de tiempo activa, retraida el resto
            for servo_nombre, t_activo in activado_en.items():
                objetivo = ANGULO_RETRAIDO
                if t_activo is not None and (ahora - t_activo) < DURACION_EMPUJE:
                    objetivo = ANGULO_EXTENDIDO
                elif t_activo is not None:
                    activado_en[servo_nombre] = None  # listo, vuelve a inactivo
                p.setJointMotorControl2(planta, joint_paleta[servo_nombre], p.POSITION_CONTROL,
                                        targetPosition=objetivo, force=15, maxVelocity=6.0)

            p.stepSimulation()
            time.sleep(paso)
    except KeyboardInterrupt:
        pass
    finally:
        p.disconnect()
        print("\nConteo final:", conteo)


if __name__ == "__main__":
    main()
