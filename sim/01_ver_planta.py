"""
01_ver_planta.py
================
Sistema de Logistica de Monedas Inteligentes - Grupo 3
FASE 1: visualizacion de la planta reparada.

Carga planta_monedas_v1.urdf, dibuja los ejes de referencia y marca la
altura util de las bandas para comprobar que toda la geometria quedo
donde debe.

Uso:
    python sim/01_ver_planta.py
    python sim/01_ver_planta.py --original     (carga la maqueta del profe)

Teclas dentro de la ventana de PyBullet:
    g   ocultar / mostrar los paneles laterales
    w   ver mallas de colision (wireframe)
    ruedita del mouse   zoom
    ctrl + arrastrar    rotar camara
"""

import os
import sys
import time
import pybullet as p
import pybullet_data

# Rutas relativas a la raiz del proyecto (un nivel arriba de sim/)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URDF_PROPIO = os.path.join(RAIZ, "urdf", "planta_monedas_v1.urdf")
URDF_ORIGINAL = os.path.join(RAIZ, "urdf", "maqueta_original.urdf")

ALTURA_BANDA = 0.605   # superficie util de las cintas, en metros


def dibujar_ejes(largo=1.0, grosor=3):
    """Ejes de referencia en el origen: X rojo, Y verde, Z azul."""
    p.addUserDebugLine([0, 0, 0], [largo, 0, 0], [1, 0, 0], grosor)
    p.addUserDebugLine([0, 0, 0], [0, largo, 0], [0, 1, 0], grosor)
    p.addUserDebugLine([0, 0, 0], [0, 0, largo], [0, 0, 1], grosor)
    p.addUserDebugText("X", [largo, 0, 0], [1, 0, 0], 1.4)
    p.addUserDebugText("Y", [0, largo, 0], [0, 1, 0], 1.4)
    p.addUserDebugText("Z", [0, 0, largo], [0, 0, 1], 1.4)


def rotular(texto, xyz, color=(1, 1, 0)):
    p.addUserDebugText(texto, xyz, color, textSize=1.1)


def main():
    usar_original = "--original" in sys.argv
    urdf = URDF_ORIGINAL if usar_original else URDF_PROPIO

    if not os.path.isfile(urdf):
        print(f"[X] No encuentro {urdf}")
        sys.exit(1)

    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)          # sin paneles
    p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1)
    p.setGravity(0, 0, -9.81)
    p.loadURDF("plane.urdf")

    planta = p.loadURDF(urdf, basePosition=[0, 0, 0], useFixedBase=True)

    print("=" * 68)
    print("PLANTA CARGADA:", os.path.basename(urdf))
    print("=" * 68)
    n = p.getNumJoints(planta)
    print(f"Links (joints) reconocidos por PyBullet: {n}")
    print(f"Base link: {p.getBodyInfo(planta)[0].decode('utf-8')}\n")

    print("idx  link hijo")
    print("-" * 40)
    for i in range(n):
        print(f"{i:>3}  {p.getJointInfo(planta, i)[12].decode('utf-8')}")

    # --- Ayudas visuales ---
    dibujar_ejes(1.2)
    if not usar_original:
        rotular("MAQUINA CLASIFICADORA", [-1.9, 0, 2.1])
        rotular("cinta_1", [1.0, 0.45, 0.75])
        rotular("cinta_2", [-1.45, -2.0, 0.75])
        rotular("cinta_3", [1.0, -3.55, 0.75])
        rotular("ESP32", [0.2, 0.0, 1.25], (0.3, 0.9, 1.0))
        rotular("BRAZO 1", [1.5, -1.0, 1.0])
        rotular("BRAZO 2", [2.5, -5.0, 1.0])
        rotular("CARRO", [4.0, -4.0, 1.0])
        # linea que marca la altura util de las bandas
        p.addUserDebugLine([-1, 0.6, ALTURA_BANDA], [3, 0.6, ALTURA_BANDA],
                           [1, 1, 0], 2)

    p.resetDebugVisualizerCamera(cameraDistance=8.5, cameraYaw=45,
                                 cameraPitch=-35,
                                 cameraTargetPosition=[1.0, -2.0, 0.4])

    print("\nVentana abierta. Ctrl+C aqui para cerrar.")
    try:
        while p.isConnected():
            p.stepSimulation()
            time.sleep(1 / 240)
    except KeyboardInterrupt:
        pass
    finally:
        p.disconnect()


if __name__ == "__main__":
    main()
