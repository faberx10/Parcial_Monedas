"""
03_planta_con_dron.py
======================
Sistema de Logistica de Monedas Inteligentes - Grupo 3
FASE 2b: planta (sin carro) + dron como cuerpo independiente.

Carga planta_monedas_v3.urdf (fija al piso, useFixedBase=True, igual que
siempre) y dron.urdf como un SEGUNDO cuerpo con useFixedBase=False -- un
cuerpo libre de 6 grados de libertad que PyBullet simula con fisica
completa (cae si no se sostiene). Se posiciona "posado" justo donde
cinta_3 entrega los vasos, y las 4 helices giran solo para verificar
visualmente que los joints continuous responden.

Uso:
    python sim/03_planta_con_dron.py
"""

import os
import time
import pybullet as p
import pybullet_data

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URDF_PLANTA = os.path.join(RAIZ, "urdf", "planta_monedas_v3.urdf")
URDF_DRON = os.path.join(RAIZ, "urdf", "dron.urdf")

# Punto de entrega: extremo de cinta_3 (banda en Y=-4, va de X=-1 a X=3).
# El dron se posa justo despues del extremo, a la misma altura de banda.
POSICION_MUELLE = [3.35, -4.0, 0.66]


def main():
    for ruta in (URDF_PLANTA, URDF_DRON):
        if not os.path.isfile(ruta):
            print(f"[X] No encuentro {ruta}")
            return

    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1)
    p.setGravity(0, 0, -9.81)
    p.loadURDF("plane.urdf")

    planta = p.loadURDF(URDF_PLANTA, basePosition=[0, 0, 0], useFixedBase=True)
    dron = p.loadURDF(URDF_DRON, basePosition=POSICION_MUELLE,
                       baseOrientation=p.getQuaternionFromEuler([0, 0, 0]),
                       useFixedBase=False)

    print("=" * 68)
    print(f"Planta: {p.getNumJoints(planta)} joints  |  Dron body id: {dron}")
    print(f"Dron posado en: {POSICION_MUELLE}")
    print("=" * 68)

    # localizar las 4 helices del dron para animarlas
    helices = []
    for i in range(p.getNumJoints(dron)):
        info = p.getJointInfo(dron, i)
        if info[2] == p.JOINT_REVOLUTE or "helice" in info[1].decode("utf-8"):
            helices.append(i)
    print(f"Helices encontradas: {len(helices)} -> joints {helices}")

    # como el dron es un cuerpo LIBRE (no useFixedBase), sin nada que lo
    # sostenga va a caer por gravedad -- eso es correcto y esperado.
    # Para esta prueba de humo lo anclamos temporalmente con un constraint
    # para verificar la geometria sin que se caiga antes de tener el
    # control de vuelo (eso llega en una fase posterior).
    ancla = p.createConstraint(dron, -1, -1, -1, p.JOINT_FIXED,
                               [0, 0, 0], [0, 0, 0], POSICION_MUELLE)

    p.addUserDebugText("DRON (muelle)", [POSICION_MUELLE[0], POSICION_MUELLE[1], POSICION_MUELLE[2] + 0.3],
                       [1, 1, 0], 1.2)
    p.addUserDebugText("cinta_3 -> aqui entrega", [1.0, -3.55, 0.9], [1, 1, 0], 1.0)

    p.resetDebugVisualizerCamera(cameraDistance=6.0, cameraYaw=20, cameraPitch=-30,
                                 cameraTargetPosition=[2.0, -4.0, 0.6])

    print("\nVentana abierta. El dron esta anclado temporalmente (constraint)")
    print("para que no caiga -- el vuelo libre llega en una fase posterior.")
    print("Ctrl+C aqui para cerrar.\n")

    velocidad_helice = 15.0
    try:
        while p.isConnected():
            for h in helices:
                p.setJointMotorControl2(dron, h, p.VELOCITY_CONTROL,
                                        targetVelocity=velocidad_helice, force=1.0)
            p.stepSimulation()
            time.sleep(1 / 240)
    except KeyboardInterrupt:
        pass
    finally:
        p.disconnect()


if __name__ == "__main__":
    main()
