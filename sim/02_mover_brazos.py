"""
02_mover_brazos.py
===================
Sistema de Logistica de Monedas Inteligentes - Grupo 3
FASE 2: control interactivo de los brazos.

Abre la planta v2 y crea un slider en pantalla por cada articulacion
movil (hombro, codo, muneca y las dos pinzas de cada brazo). Mueve los
sliders para comprobar que cada joint responde y que la geometria no
se rompe ni se atraviesa a si misma en los extremos de su rango.

Uso:
    python sim/02_mover_brazos.py
"""

import os
import time
import pybullet as p
import pybullet_data

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URDF = os.path.join(RAIZ, "urdf", "planta_monedas_v2.urdf")


def main():
    if not os.path.isfile(URDF):
        print(f"[X] No encuentro {URDF}")
        return

    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1)
    p.setGravity(0, 0, -9.81)
    p.loadURDF("plane.urdf")

    planta = p.loadURDF(URDF, basePosition=[0, 0, 0], useFixedBase=True)

    # --- localizar articulaciones moviles y crear un slider por cada una ---
    sliders = []   # (joint_index, slider_id)
    n = p.getNumJoints(planta)
    print(f"Explorando {n} joints...")
    for i in range(n):
        info = p.getJointInfo(planta, i)
        nombre = info[1].decode("utf-8")
        tipo = info[2]
        if tipo in (p.JOINT_REVOLUTE, p.JOINT_PRISMATIC):
            lo, hi = info[8], info[9]
            valor_inicial = 0.0 if lo <= 0 <= hi else (lo + hi) / 2
            slider_id = p.addUserDebugParameter(nombre, lo, hi, valor_inicial)
            sliders.append((i, slider_id))
            print(f"  slider -> {nombre:<22} rango [{lo:.2f}, {hi:.2f}]")

    if not sliders:
        print("[!] No hay articulaciones moviles en este URDF.")

    # botones auxiliares
    boton_reset = p.addUserDebugParameter("RESET postura", 1, 0, 1)
    valor_reset_previo = p.readUserDebugParameter(boton_reset)

    p.resetDebugVisualizerCamera(cameraDistance=6.0, cameraYaw=35,
                                 cameraPitch=-30,
                                 cameraTargetPosition=[1.5, -1.0, 0.5])

    print("\nVentana abierta. Mueve los sliders del panel para mover los brazos.")
    print("Ctrl+C aqui para cerrar.\n")

    try:
        while p.isConnected():
            # reset si se pulsa el boton (cambia de valor cada click)
            valor_reset_actual = p.readUserDebugParameter(boton_reset)
            if valor_reset_actual != valor_reset_previo:
                for i, _ in sliders:
                    p.resetJointState(planta, i, targetValue=0.0)
                valor_reset_previo = valor_reset_actual

            # aplicar cada slider a su joint via control de posicion
            for i, slider_id in sliders:
                objetivo = p.readUserDebugParameter(slider_id)
                p.setJointMotorControl2(planta, i, p.POSITION_CONTROL,
                                         targetPosition=objetivo,
                                         force=200, maxVelocity=2.0)

            p.stepSimulation()
            time.sleep(1 / 240)
    except KeyboardInterrupt:
        pass
    finally:
        p.disconnect()


if __name__ == "__main__":
    main()
