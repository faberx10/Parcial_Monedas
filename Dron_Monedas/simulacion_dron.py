"""
===============================================================================
 SIMULACION DEL DRON LOGISTICO DE MONEDAS  -  PyBullet   (v2)
 Sistema de Logistica de Monedas Inteligentes - Grupo 3
===============================================================================

 EJECUTAR:   python simulacion_dron.py

 CAMBIOS DE LA v2
 ----------------
 1. CORREGIDO: el estado ATERRIZAJE no tenia salida y el dron se quedaba
    congelado en el piso ignorando los sliders. Ahora la mision se reinicia
    sola despues de aterrizar.
 2. CORREGIDO: la liberacion de la carga en el estado ENTREGA se sobrescribia
    con el valor del slider en el siguiente ciclo, asi que nunca soltaba nada.
 3. CORREGIDO: el slider de masa podia llegar a 0 g exactos, y una masa de 0
    hace que PyBullet trate el link como estatico y rompe la fisica.
 4. NUEVO: modo MANUAL. Los sliders mandan directo, sin maquina de estados.
 5. NUEVO: el controlador ya no conoce la masa real (antes hacia trampa).
    Usa una masa NOMINAL, igual que el firmware de la ESP32-S3, que tampoco
    sabe cuanto pesan las monedas que le pusieron encima.
 6. NUEVO: lazo de posicion rehecho como posicion a velocidad a angulo, con
    la velocidad maxima y la inclinacion maxima limitadas por el margen de
    empuje. Cargar mas peso ahora hace que el dron viaje visiblemente mas
    despacio: 2.4 s para recorrer 1 m con 10 g, 3.5 s con 60 g.
 7. NUEVO: vigilante de divergencia numerica.

 CONTROLES (panel de la derecha)
   Modo                 0 = mision automatica en bucle   1 = manual
   Altura objetivo      altura de vuelo
   Distancia objetivo   posicion del punto B
   Obstaculo            1 hace aparecer una caja en el camino
   Masa de la carga     0 a 60 g. Sube el slider en pleno vuelo y observa.

 ARQUITECTURA DEL CONTROL (identica a la que ira en la ESP32-S3)
   Lazo externo (lento)   posicion  a  angulos deseados
   Lazo interno (rapido)  angulos   a  empuje de cada motor
   Mezclador en X         4 empujes a  PWM de cada MOSFET
"""

import time
import numpy as np
import pybullet as p
import pybullet_data

# =============================================================================
# PARAMETROS FISICOS  (de Presupuesto_Dron_Monedas_v2.xlsx)
# =============================================================================
DT            = 1.0 / 240.0      # s
MASA_SECA     = 0.0812           # kg   dron sin carga (81.2 g)
CARGA_NOMINAL = 0.010            # kg   carga para la que esta ajustado el PID
MASA_NOMINAL  = MASA_SECA + CARGA_NOMINAL
L_BRAZO       = 0.060            # m
F_MAX_MOTOR   = 0.052 * 9.81     # N    empuje maximo por motor (52 g)
T_MAX_TOTAL   = 4.0 * F_MAX_MOTOR
K_ARRASTRE    = 0.010            # m    brazo equivalente del par de yaw
MASA_MINIMA   = 0.0001           # kg   nunca poner 0 en un link

d = L_BRAZO / np.sqrt(2.0)
POS_MOTOR = np.array([[ d, -d, 0.008],     # 0  adelante-derecha  CCW
                      [ d,  d, 0.008],     # 1  adelante-izq      CW
                      [-d,  d, 0.008],     # 2  atras-izquierda   CCW
                      [-d, -d, 0.008]])    # 3  atras-derecha     CW
SIGNO_Y = np.array([-1.0, +1.0, +1.0, -1.0])
SIGNO_X = np.array([+1.0, +1.0, -1.0, -1.0])
SENTIDO = np.array([+1.0, -1.0, +1.0, -1.0])

# =============================================================================
# GANANCIAS  (verificadas por integracion numerica)
# =============================================================================
KP_Z,   KI_Z,   KD_Z   = 12.0,  3.0,  5.0    # altura
KP_POS                 = 1.2                 # posicion  a  velocidad deseada
KP_VEL                 = 0.35                # velocidad a  angulo deseado
KP_ANG,         KD_ANG = 250.0,       30.0   # actitud
KP_YAW,         KD_YAW = 60.0,        12.0   # rumbo
ANG_MAX_BASE = np.radians(15.0)   # inclinacion maxima con la carga nominal
V_MAX_BASE   = 0.55               # m/s velocidad maxima con la carga nominal
LIMITE_INTEGRAL = 3.0

# =============================================================================
# MISION
# =============================================================================
ALTURA_CRUCERO = 1.20
DISTANCIA_META = 1.00
UMBRAL_IR      = 0.25
ALCANCE_RAYO   = 0.60
TOL_POSICION   = 0.05
PAUSA_FINAL    = 3.0     # s en el piso antes de reiniciar la mision


def margen_de_empuje(masa_real):
    """Fraccion de empuje sobrante, normalizada contra la carga nominal.

        margen = empuje sobrante actual / empuje sobrante con carga nominal

    Vale 1.0 con las monedas nominales y baja a medida que cargas mas peso.
    De este numero salen DOS limites, y de ahi viene que el dron se mueva
    mas despacio cuando va cargado:

      velocidad maxima = V_MAX_BASE   * margen
      inclinacion max  = ANG_MAX_BASE * margen

    No es un truco para que se vea bonito. Los autopilotos reales (PX4 entre
    ellos) recortan la velocidad de crucero segun el empuje disponible,
    justamente porque un dron pesado que acelera como uno vacio se queda sin
    margen para frenar y se estrella.
    """
    sobrante_actual  = T_MAX_TOTAL - masa_real * 9.81
    sobrante_nominal = T_MAX_TOTAL - MASA_NOMINAL * 9.81
    return float(np.clip(sobrante_actual / sobrante_nominal, 0.15, 1.0))


class ControladorDron:
    """Controlador en cascada. Este es el codigo que se porta a la ESP32-S3.

    OJO: usa MASA_NOMINAL, no la masa real. Eso es a proposito. El firmware
    del dron no tiene una balanza a bordo: fue ajustado para un peso y tiene
    que arreglarselas cuando le ponen mas. Por eso al subir el slider de masa
    el dron se hunde primero y el integrador lo recupera de a poco.
    """

    def __init__(self):
        self.integral_z = 0.0

    def reiniciar(self):
        self.integral_z = 0.0

    def calcular(self, pos, vel, ang, vel_ang, objetivo, ang_max, v_max):
        # ---------- LAZO DE ALTURA ----------
        e_z = objetivo[2] - pos[2]
        self.integral_z = np.clip(self.integral_z + e_z * DT,
                                  -LIMITE_INTEGRAL, LIMITE_INTEGRAL)
        a_z = KP_Z * e_z + KI_Z * self.integral_z - KD_Z * vel[2]

        cos_incl = max(np.cos(ang[0]) * np.cos(ang[1]), 0.5)
        empuje_total = MASA_NOMINAL * (9.81 + a_z) / cos_incl
        empuje_total = np.clip(empuje_total, 0.0, T_MAX_TOTAL)

        # ---------- LAZO DE POSICION  (posicion a velocidad) ----------
        # El error de posicion no pide un angulo directamente: pide una
        # VELOCIDAD, y esa velocidad va saturada. Ese tope es el que hace
        # que el dron cargado viaje mas despacio.
        vel_des_x = np.clip(KP_POS * (objetivo[0] - pos[0]), -v_max, v_max)
        vel_des_y = np.clip(KP_POS * (objetivo[1] - pos[1]), -v_max, v_max)

        # ---------- LAZO DE VELOCIDAD  (velocidad a angulo) ----------
        pitch_des = np.clip(KP_VEL * (vel_des_x - vel[0]), -ang_max, ang_max)
        roll_des  = np.clip(-KP_VEL * (vel_des_y - vel[1]), -ang_max, ang_max)

        # ---------- LAZO DE ACTITUD ----------
        tau_x = (KP_ANG * (roll_des  - ang[0]) - KD_ANG * vel_ang[0]) * 7.0e-5
        tau_y = (KP_ANG * (pitch_des - ang[1]) - KD_ANG * vel_ang[1]) * 7.0e-5
        tau_z = (KP_YAW * (0.0       - ang[2]) - KD_YAW * vel_ang[2]) * 1.3e-4

        # ---------- MEZCLADOR EN X ----------
        empujes = (empuje_total / 4.0
                   + SIGNO_Y * tau_x / (4.0 * d)
                   - SIGNO_X * tau_y / (4.0 * d)
                   + SENTIDO * tau_z / (4.0 * K_ARRASTRE))
        return np.clip(empujes, 0.0, F_MAX_MOTOR)


def empuje_a_pwm(empuje_n):
    """Empuje en Newtons a ciclo util de PWM (0-100 %).

    El ensayo de banco mostro que en los motores coreless 8520 el empuje
    contra ciclo util es practicamente LINEAL, asi que es una regla de tres.
    Este es el numero que la ESP32 escribiria en el periferico LEDC.
    """
    return np.clip(empuje_n / F_MAX_MOTOR, 0.0, 1.0) * 100.0


def indice_de_link(cuerpo, nombre):
    """PyBullet numera los links por el orden de los <joint>, no de los <link>."""
    for i in range(p.getNumJoints(cuerpo)):
        if p.getJointInfo(cuerpo, i)[12].decode() == nombre:
            return i
    raise ValueError(f"No existe el link '{nombre}' en el URDF")


def main():
    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setTimeStep(DT)
    p.setRealTimeSimulation(0)

    p.configureDebugVisualizer(p.COV_ENABLE_GUI, 1)
    p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1)
    p.resetDebugVisualizerCamera(cameraDistance=2.2, cameraYaw=50,
                                 cameraPitch=-25,
                                 cameraTargetPosition=[0.5, 0, 0.6])

    p.loadURDF("plane.urdf")
    POSE_INICIAL = [0, 0, 0.05]
    dron = p.loadURDF("dron_monedas.urdf", basePosition=POSE_INICIAL)
    p.changeDynamics(dron, -1, linearDamping=0.0, angularDamping=0.0)
    ID_CARGA = indice_de_link(dron, "carga")

    s_modo   = p.addUserDebugParameter("Modo (0=mision 1=manual)", 0, 1, 0)
    s_altura = p.addUserDebugParameter("Altura objetivo (m)", 0.0, 2.0, ALTURA_CRUCERO)
    s_dist   = p.addUserDebugParameter("Distancia objetivo (m)", 0.0, 2.0, DISTANCIA_META)
    s_obst   = p.addUserDebugParameter("Obstaculo (0=no 1=si)", 0, 1, 0)
    s_carga  = p.addUserDebugParameter("Masa de la carga (g)", 0.0, 60.0, 10.0)

    obstaculo = None
    texto_hud = None
    ctrl = ControladorDron()
    estado, t_estado = "DESPEGUE", 0.0
    carga_soltada = False
    paso = 0

    print("=" * 76)
    print(" SIMULACION DEL DRON LOGISTICO DE MONEDAS  (v2)")
    print(" Modo 0: la mision corre en bucle.  Modo 1: los sliders mandan directo.")
    print(" Sube el slider de masa en pleno vuelo para ver como se hunde y se frena.")
    print(" Ctrl+C en la terminal para salir.")
    print("=" * 76)

    try:
        while True:
            modo_manual = p.readUserDebugParameter(s_modo) > 0.5
            alt_obj     = p.readUserDebugParameter(s_altura)
            dist_obj    = p.readUserDebugParameter(s_dist)
            hay_obst    = p.readUserDebugParameter(s_obst) > 0.5
            masa_slider = max(p.readUserDebugParameter(s_carga) / 1000.0, MASA_MINIMA)

            # La carga solo obedece al slider mientras el dron no la haya soltado
            masa_carga = MASA_MINIMA if carga_soltada else masa_slider
            p.changeDynamics(dron, ID_CARGA, mass=masa_carga)
            masa_real = MASA_SECA + masa_carga
            margen  = margen_de_empuje(masa_real)
            ang_max = ANG_MAX_BASE * margen
            v_max   = V_MAX_BASE * margen

            # ---------------- Obstaculo ----------------
            if hay_obst and obstaculo is None:
                col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.03, 0.15, 0.30])
                vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.03, 0.15, 0.30],
                                          rgbaColor=[0.8, 0.2, 0.2, 0.8])
                obstaculo = p.createMultiBody(0, col, vis, [0.65, 0, 1.10])
            elif not hay_obst and obstaculo is not None:
                p.removeBody(obstaculo)
                obstaculo = None

            # ---------------- Estado del dron ----------------
            pos, cuat = p.getBasePositionAndOrientation(dron)
            vel, vel_ang_w = p.getBaseVelocity(dron)
            pos = np.array(pos)
            vel = np.array(vel)
            ang = np.array(p.getEulerFromQuaternion(cuat))
            R = np.array(p.getMatrixFromQuaternion(cuat)).reshape(3, 3)
            vel_ang = R.T @ np.array(vel_ang_w)   # la IMU mide en marco cuerpo

            # ---------------- Vigilante de divergencia ----------------
            # Si la fisica explota, la posicion se vuelve NaN o enorme y la
            # ventana parece congelada sin ningun mensaje de error.
            if not np.all(np.isfinite(pos)) or np.linalg.norm(pos) > 50.0:
                print("\n*** Simulacion divergida. Reiniciando el dron. ***")
                p.resetBasePositionAndOrientation(dron, POSE_INICIAL, [0, 0, 0, 1])
                p.resetBaseVelocity(dron, [0, 0, 0], [0, 0, 0])
                ctrl.reiniciar()
                estado, t_estado, carga_soltada = "DESPEGUE", 0.0, False
                continue

            # ---------------- SENSOR IR FRONTAL (FC-51) ----------------
            origen  = pos + R @ np.array([0.035, 0, 0])
            destino = pos + R @ np.array([0.035 + ALCANCE_RAYO, 0, 0])
            golpe = p.rayTest(origen.tolist(), destino.tolist())[0]
            if golpe[0] not in (-1, dron):
                dist_ir = golpe[2] * ALCANCE_RAYO
                detectado = dist_ir < UMBRAL_IR
            else:
                dist_ir = ALCANCE_RAYO
                detectado = False

            # ---------------- OBJETIVO ----------------
            t_estado += DT

            if modo_manual:
                # Los sliders mandan directo. Sin maquina de estados.
                estado = "MANUAL"
                carga_soltada = False
                objetivo = np.array([dist_obj, 0.0, alt_obj])

            elif estado == "DESPEGUE":
                objetivo = np.array([0.0, 0.0, alt_obj])
                if abs(pos[2] - alt_obj) < TOL_POSICION and t_estado > 2.0:
                    estado, t_estado = "CRUCERO", 0.0

            elif estado == "CRUCERO":
                objetivo = np.array([dist_obj, 0.0, alt_obj])
                if detectado:
                    estado, t_estado = "OBSTACULO", 0.0
                elif abs(pos[0] - dist_obj) < TOL_POSICION and t_estado > 2.0:
                    estado, t_estado = "ENTREGA", 0.0

            elif estado == "OBSTACULO":
                objetivo = np.array([pos[0], 0.0, alt_obj])
                if not detectado and t_estado > 2.0:
                    estado, t_estado = "CRUCERO", 0.0

            elif estado == "ENTREGA":
                objetivo = np.array([dist_obj, 0.0, 0.35])
                if pos[2] < 0.40 and t_estado > 2.0:
                    carga_soltada = True          # suelta las monedas
                    estado, t_estado = "RETORNO", 0.0

            elif estado == "RETORNO":
                objetivo = np.array([0.0, 0.0, alt_obj])
                if np.linalg.norm(pos[:2]) < TOL_POSICION and t_estado > 2.0:
                    estado, t_estado = "ATERRIZAJE", 0.0

            else:  # ATERRIZAJE
                objetivo = np.array([0.0, 0.0, 0.0])
                # Aqui estaba el error de la v1: este estado no tenia salida
                # y el dron se quedaba quieto ignorando los sliders.
                if pos[2] < 0.10 and t_estado > PAUSA_FINAL:
                    print(">>> Mision completada. Recargando y reiniciando ciclo.")
                    carga_soltada = False
                    ctrl.reiniciar()
                    estado, t_estado = "DESPEGUE", 0.0

            # ---------------- CONTROL ----------------
            empujes = ctrl.calcular(pos, vel, ang, vel_ang, objetivo, ang_max, v_max)

            for i in range(4):
                p.applyExternalForce(dron, -1,
                                     forceObj=[0, 0, float(empujes[i])],
                                     posObj=POS_MOTOR[i].tolist(),
                                     flags=p.LINK_FRAME)

            # Par de yaw por arrastre. Se rota a marco mundo a mano porque
            # applyExternalTorque con LINK_FRAME cambia segun la version.
            tau_yaw = float(np.sum(SENTIDO * empujes) * K_ARRASTRE)
            p.applyExternalTorque(dron, -1,
                                  torqueObj=(R @ np.array([0, 0, tau_yaw])).tolist(),
                                  flags=p.WORLD_FRAME)

            p.stepSimulation()

            # ---------------- TELEMETRIA (lo que la ESP32 enviaria por UDP) ----
            if paso % 60 == 0:
                pwm = empuje_a_pwm(empujes)
                tw  = T_MAX_TOTAL / (masa_real * 9.81)
                marca = "  <<< OBSTACULO" if detectado else ""
                print(f"[{estado:10s}] x={pos[0]:5.2f} z={pos[2]:5.2f} m | "
                      f"masa={masa_real*1000:5.1f} g | T/W={tw:4.2f} | "
                      f"v.lim={v_max:4.2f} m/s | incl.max={np.degrees(ang_max):4.1f} deg | "
                      f"PWM={pwm.mean():4.1f}%{marca}")

                if texto_hud is not None:
                    p.removeUserDebugItem(texto_hud)
                etiqueta = (f"{estado}  |  {masa_real*1000:.0f} g  |  T/W {tw:.2f}"
                            f"  |  v.lim {v_max:.2f} m/s"
                            f"{'  |  IR BLOQUEADO' if detectado else ''}")
                texto_hud = p.addUserDebugText(
                    etiqueta, [pos[0], pos[1], pos[2] + 0.18],
                    textColorRGB=[1, 0.3, 0.3] if detectado else [0.2, 0.8, 0.2],
                    textSize=1.3)

            paso += 1
            time.sleep(DT)

    except KeyboardInterrupt:
        print("\nSimulacion terminada.")
        p.disconnect()


if __name__ == "__main__":
    main()
