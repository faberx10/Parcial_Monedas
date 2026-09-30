"""
00_diagnostico_urdf.py
======================
Sistema de Logistica de Monedas Inteligentes - Grupo 3
Herramienta de diagnostico de archivos URDF.

Hace dos cosas:
  1) ANALISIS XML (no necesita PyBullet): recorre el URDF y reporta links,
     joints, raices del arbol y links huerfanos.
  2) CARGA EN PYBULLET (opcional, flag --gui): carga el URDF y lista lo que
     el motor de fisica realmente reconocio.

Uso:
    python sim/00_diagnostico_urdf.py urdf/maqueta_original.urdf
    python sim/00_diagnostico_urdf.py urdf/maqueta_original.urdf --gui
"""

import sys
import os
import xml.etree.ElementTree as ET


# ----------------------------------------------------------------------
# PARTE 1 - ANALISIS ESTATICO DEL XML
# ----------------------------------------------------------------------
def analizar_xml(ruta):
    print("=" * 68)
    print(f"ANALISIS XML  ->  {ruta}")
    print("=" * 68)

    raiz = ET.parse(ruta).getroot()

    links = [l.get("name") for l in raiz.findall("link")]
    joints = []
    for j in raiz.findall("joint"):
        joints.append({
            "nombre": j.get("name"),
            "tipo": j.get("type"),
            "padre": j.find("parent").get("link"),
            "hijo": j.find("child").get("link"),
        })

    hijos = {j["hijo"] for j in joints}
    padres = {j["padre"] for j in joints}
    raices = [l for l in links if l not in hijos]
    huerfanos = [l for l in raices if l not in padres]
    tipos = {}
    for j in joints:
        tipos[j["tipo"]] = tipos.get(j["tipo"], 0) + 1

    print(f"Robot            : {raiz.get('name')}")
    print(f"Links            : {len(links)}")
    print(f"Joints           : {len(joints)}  ->  {tipos}")
    print(f"Raices del arbol : {len(raices)}")

    print("\n--- RAICES ---")
    for r in raices:
        marca = "  [HUERFANO: sin padre y sin hijos]" if r in huerfanos else ""
        print(f"  * {r}{marca}")

    print("\n--- ARTICULACIONES MOVILES (revolute/prismatic/continuous) ---")
    moviles = [j for j in joints if j["tipo"] in ("revolute", "prismatic", "continuous")]
    if not moviles:
        print("  NINGUNA. El modelo es puramente decorativo: nada se puede accionar.")
    for j in moviles:
        print(f"  * {j['nombre']:<24} {j['tipo']:<12} {j['padre']} -> {j['hijo']}")

    # ---- Veredicto ----
    print("\n" + "-" * 68)
    print("VEREDICTO")
    print("-" * 68)
    if len(raices) > 1:
        print(f"[!] Hay {len(raices)} raices. Un URDF valido debe tener EXACTAMENTE 1.")
        print("    PyBullet cargara solo el arbol de la primera raiz y")
        print(f"    descartara la geometria de: {', '.join(huerfanos)}")
    else:
        print("[OK] Arbol cinematico con una sola raiz.")
    if not moviles:
        print("[!] Sin joints moviles: no hay nada que controlar desde codigo.")
    else:
        print(f"[OK] {len(moviles)} articulaciones controlables.")
    print()

    return raices, huerfanos, moviles


# ----------------------------------------------------------------------
# PARTE 2 - CARGA REAL EN PYBULLET
# ----------------------------------------------------------------------
def cargar_en_pybullet(ruta, gui=True):
    try:
        import pybullet as p
        import pybullet_data
    except ImportError:
        print("[X] PyBullet no esta instalado. Activa el entorno virtual e instala:")
        print("    pip install -r requirements.txt")
        return

    import time

    print("=" * 68)
    print("CARGA EN PYBULLET")
    print("=" * 68)

    p.connect(p.GUI if gui else p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.loadURDF("plane.urdf")

    cuerpo = p.loadURDF(ruta, basePosition=[0, 0, 0], useFixedBase=True)

    n = p.getNumJoints(cuerpo)
    print(f"Body ID          : {cuerpo}")
    print(f"Base link        : {p.getBodyInfo(cuerpo)[0].decode('utf-8')}")
    print(f"Joints cargados  : {n}")

    NOMBRE_TIPO = {
        p.JOINT_REVOLUTE: "REVOLUTE",
        p.JOINT_PRISMATIC: "PRISMATIC",
        p.JOINT_SPHERICAL: "SPHERICAL",
        p.JOINT_PLANAR: "PLANAR",
        p.JOINT_FIXED: "FIXED",
    }

    print("\nidx  joint                     tipo        link hijo")
    print("-" * 68)
    for i in range(n):
        info = p.getJointInfo(cuerpo, i)
        print(f"{i:>3}  {info[1].decode('utf-8'):<25} "
              f"{NOMBRE_TIPO.get(info[2], '?'):<11} {info[12].decode('utf-8')}")

    if gui:
        p.resetDebugVisualizerCamera(cameraDistance=9, cameraYaw=50,
                                     cameraPitch=-35, cameraTargetPosition=[0, -2, 0])
        print("\nVentana abierta. Cierra la ventana o pulsa Ctrl+C aqui para salir.")
        try:
            while p.isConnected():
                p.stepSimulation()
                time.sleep(1 / 240)
        except KeyboardInterrupt:
            pass
    p.disconnect()


# ----------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    ruta_urdf = sys.argv[1]
    if not os.path.isfile(ruta_urdf):
        print(f"[X] No existe el archivo: {ruta_urdf}")
        sys.exit(1)

    analizar_xml(ruta_urdf)

    if "--gui" in sys.argv:
        cargar_en_pybullet(ruta_urdf, gui=True)
    else:
        print("Sugerencia: agrega --gui para abrir la ventana de PyBullet.\n")
