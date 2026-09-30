/*
 * Carrito de transporte - Sistema de Logística de Monedas Inteligentes (Grupo 3)
 * ESP32 + L298N + motores TT, controlado desde el celular por WiFi.
 *
 * Uso:
 *   1. Carga este programa en la ESP32.
 *   2. En el celular conéctate a la red WiFi "Carrito_G3" (clave: monedas123).
 *      Si el celular avisa "sin internet", elige "Mantener conexión" y apaga los datos móviles.
 *   3. Abre el navegador en  http://192.168.4.1
 *
 * Simulación: compilando con el entorno "wokwi" de platformio.ini (define WOKWI_SIM)
 * la ESP32 se conecta a la red virtual de Wokwi y la página se abre en http://localhost:8180
 *
 * Seguridad: si el celular deja de mandar órdenes (se sale de la página, se cae el WiFi,
 * sueltas el botón), el carrito se detiene solo en menos de medio segundo.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

// ================== CONFIGURACIÓN ==================
const char* AP_SSID = "Carrito_G3";
const char* AP_PASS = "monedas123";   // mínimo 8 caracteres

// Pines hacia el L298N (ESP32 DevKit clásica). Si usas ESP32-S3, cámbialos por pines libres.
const int ENA = 13;  // PWM lado izquierdo  (quita el jumper ENA del L298N)
const int IN1 = 27;
const int IN2 = 26;
const int IN3 = 25;
const int IN4 = 33;
const int ENB = 32;  // PWM lado derecho    (quita el jumper ENB del L298N)

// Si un lado gira al revés, cambia a true (o intercambia los dos cables de ese motor).
const bool INVERTIR_IZQ = false;
const bool INVERTIR_DER = false;

const int PWM_MAX = 255;
const int PWM_MIN_ARRANQUE = 90;       // debajo de esto los motores TT zumban pero no giran
const float FACTOR_GIRO = 0.7;         // giros en el sitio más suaves que el avance
const unsigned long TIMEOUT_MS = 400;  // sin órdenes por este tiempo -> se detiene
const int PASO_SUBIDA = 6;             // rampa de aceleración (suave, para no tumbar los vasos)
const int PASO_BAJADA = 15;            // rampa de frenado (más rápida)
const unsigned long PERIODO_RAMPA_MS = 10;
// ===================================================

WebServer server(80);

int objetivoIzq = 0, objetivoDer = 0;  // -255 .. 255
int actualIzq = 0, actualDer = 0;
unsigned long ultimoComando = 0;
unsigned long timeoutActual = TIMEOUT_MS;  // 400 ms desde la página, 2 s desde el monitor serial

// ---------- Página web (se guarda dentro de la ESP32) ----------
const char PAGINA[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>Carrito G3</title>
<style>
  * { box-sizing: border-box; -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #14181f; color: #e8ecf2;
         display: flex; flex-direction: column; align-items: center; min-height: 100vh; padding: 16px; }
  h1 { font-size: 20px; margin: 4px 0 2px; }
  #estado { font-size: 14px; margin-bottom: 14px; }
  .ok { color: #4ade80; } .mal { color: #f87171; }
  .pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; width: min(92vw, 360px); }
  .pad button { aspect-ratio: 1; font-size: 34px; border: none; border-radius: 16px;
                background: #2a3240; color: #e8ecf2; touch-action: none; }
  .pad button.activo { background: #3b82f6; }
  .pad .centro { background: #1d232d; font-size: 14px; color: #8a94a6; }
  .vel { width: min(92vw, 360px); margin: 22px 0 10px; }
  .vel label { display: flex; justify-content: space-between; font-size: 15px; margin-bottom: 6px; }
  input[type=range] { width: 100%; height: 36px; }
  #parar { width: min(92vw, 360px); padding: 18px; font-size: 22px; font-weight: 700; border: none;
           border-radius: 16px; background: #dc2626; color: white; touch-action: none; margin-top: 6px; }
  p.ayuda { font-size: 13px; color: #8a94a6; text-align: center; max-width: 360px; }
</style>
</head>
<body>
  <h1>Carrito Grupo 3</h1>
  <div id="estado" class="mal">Conectando...</div>

  <div class="pad">
    <button data-d="FL">&#8598;</button>
    <button data-d="F">&#8593;</button>
    <button data-d="FR">&#8599;</button>
    <button data-d="L">&#8634;</button>
    <button class="centro" disabled>mantén<br>presionado</button>
    <button data-d="R">&#8635;</button>
    <button data-d="BL">&#8601;</button>
    <button data-d="B">&#8595;</button>
    <button data-d="BR">&#8600;</button>
  </div>

  <div class="vel">
    <label><span>Velocidad</span><span id="velTxt">60%</span></label>
    <input type="range" id="vel" min="35" max="100" value="60">
  </div>

  <button id="parar">PARAR</button>
  <p class="ayuda">Con vasos llenos usa velocidad baja. Si sueltas el botón o pierdes la señal, el carrito se detiene solo.</p>

<script>
  const vel = document.getElementById('vel');
  const velTxt = document.getElementById('velTxt');
  const estado = document.getElementById('estado');
  let dir = null, timer = null, enVuelo = false;

  vel.oninput = () => velTxt.textContent = vel.value + '%';

  function enviar(d) {
    if (enVuelo && d !== 'S' && d !== 'X') return;   // no acumular peticiones
    enVuelo = true;
    fetch('/cmd?d=' + d + '&s=' + vel.value, { cache: 'no-store' })
      .then(r => { estado.textContent = 'Conectado'; estado.className = 'ok'; })
      .catch(() => { estado.textContent = 'Sin conexión con el carrito'; estado.className = 'mal'; })
      .finally(() => enVuelo = false);
  }

  function iniciar(d, boton) {
    dir = d;
    document.querySelectorAll('.pad button').forEach(b => b.classList.remove('activo'));
    if (boton) boton.classList.add('activo');
    enviar(d);
    clearInterval(timer);
    timer = setInterval(() => enviar(dir), 150);   // repetir mientras se mantenga presionado
  }

  function soltar() {
    clearInterval(timer); timer = null; dir = null;
    document.querySelectorAll('.pad button').forEach(b => b.classList.remove('activo'));
    enviar('S');
  }

  document.querySelectorAll('.pad button[data-d]').forEach(b => {
    b.addEventListener('pointerdown', e => { e.preventDefault(); b.setPointerCapture(e.pointerId); iniciar(b.dataset.d, b); });
    b.addEventListener('pointerup', soltar);
    b.addEventListener('pointercancel', soltar);
    b.addEventListener('contextmenu', e => e.preventDefault());
  });

  document.getElementById('parar').addEventListener('pointerdown', e => {
    e.preventDefault(); clearInterval(timer); timer = null; dir = null; enviar('X');
  });

  // Control con teclado (para probar desde el computador): flechas o WASD
  const teclas = { ArrowUp:'F', w:'F', ArrowDown:'B', s:'B', ArrowLeft:'L', a:'L', ArrowRight:'R', d:'R' };
  document.addEventListener('keydown', e => { const d = teclas[e.key]; if (d && dir !== d && !e.repeat) iniciar(d, null); });
  document.addEventListener('keyup',   e => { if (teclas[e.key]) soltar(); });

  // Si la página se oculta (bloqueas el celular, cambias de app), detener
  document.addEventListener('visibilitychange', () => { if (document.hidden) soltar(); });

  // Latido para mostrar el estado de conexión
  setInterval(() => { if (!timer) fetch('/ping', { cache: 'no-store' })
      .then(() => { estado.textContent = 'Conectado'; estado.className = 'ok'; })
      .catch(() => { estado.textContent = 'Sin conexión con el carrito'; estado.className = 'mal'; }); }, 2000);
</script>
</body>
</html>
)rawliteral";

// ---------- Motores ----------
void aplicarMotor(int pinEn, int pinA, int pinB, int valor, bool invertir) {
  if (invertir) valor = -valor;

  // Zona muerta: si hay que moverse, no bajar del mínimo que realmente mueve el motor
  if (valor != 0 && abs(valor) < PWM_MIN_ARRANQUE) {
    valor = (valor > 0) ? PWM_MIN_ARRANQUE : -PWM_MIN_ARRANQUE;
  }

  if (valor > 0) {
    digitalWrite(pinA, HIGH);
    digitalWrite(pinB, LOW);
  } else if (valor < 0) {
    digitalWrite(pinA, LOW);
    digitalWrite(pinB, HIGH);
  } else {
    digitalWrite(pinA, LOW);
    digitalWrite(pinB, LOW);
  }
  analogWrite(pinEn, abs(valor));
}

int acercar(int actual, int objetivo) {
  bool frenando = (abs(objetivo) < abs(actual)) || ((long)objetivo * actual < 0);
  int paso = frenando ? PASO_BAJADA : PASO_SUBIDA;
  if (actual < objetivo) return min(actual + paso, objetivo);
  if (actual > objetivo) return max(actual - paso, objetivo);
  return actual;
}

void pararYa() {
  objetivoIzq = objetivoDer = 0;
  actualIzq = actualDer = 0;
  aplicarMotor(ENA, IN1, IN2, 0, INVERTIR_IZQ);
  aplicarMotor(ENB, IN3, IN4, 0, INVERTIR_DER);
}

// ---------- Servidor web ----------
void manejarRaiz() {
  server.send_P(200, "text/html", PAGINA);
}

void manejarPing() {
  server.send(200, "text/plain", "ok");
}

void manejarComando() {
  String d = server.arg("d");
  int s = constrain(server.arg("s").toInt(), 0, 100);
  float v = s * PWM_MAX / 100.0;

  float izq = 0, der = 0;
  if      (d == "F")  { izq =  1.0; der =  1.0; }
  else if (d == "B")  { izq = -1.0; der = -1.0; }
  else if (d == "L")  { izq = -FACTOR_GIRO; der =  FACTOR_GIRO; }
  else if (d == "R")  { izq =  FACTOR_GIRO; der = -FACTOR_GIRO; }
  else if (d == "FL") { izq =  0.35; der =  1.0; }
  else if (d == "FR") { izq =  1.0;  der =  0.35; }
  else if (d == "BL") { izq = -0.35; der = -1.0; }
  else if (d == "BR") { izq = -1.0;  der = -0.35; }
  else if (d == "X")  { pararYa(); }          // botón PARAR: frena de una
  // "S" (soltar) o cualquier otra cosa: objetivo 0, frena con rampa

  objetivoIzq = (int)(izq * v);
  objetivoDer = (int)(der * v);
  ultimoComando = millis();
  timeoutActual = TIMEOUT_MS;
  server.send(200, "text/plain", "ok");
}

void setup() {
  Serial.begin(115200);

  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  pararYa();

#ifdef WOKWI_SIM
  // Simulación en Wokwi: el simulador no admite modo punto de acceso (AP),
  // así que la ESP32 se conecta como estación a la red virtual "Wokwi-GUEST".
  WiFi.mode(WIFI_STA);
  WiFi.begin("Wokwi-GUEST", "", 6);
  Serial.print("Conectando a Wokwi-GUEST");
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.println(" conectado");
#else
  // Carrito real: la ESP32 crea su propia red WiFi
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
#endif
  WiFi.setSleep(false);  // menos retraso en la respuesta

  server.on("/", manejarRaiz);
  server.on("/cmd", manejarComando);
  server.on("/ping", manejarPing);
  server.begin();

  Serial.println();
#ifdef WOKWI_SIM
  Serial.println("Simulacion lista: abre http://localhost:8180 en el navegador del PC");
#else
  Serial.print("Red WiFi: "); Serial.println(AP_SSID);
  Serial.print("Abrir en el celular: http://"); Serial.println(WiFi.softAPIP());
#endif
}

// Control alterno por monitor serial (sirve para probar sin la página, p. ej. en wokwi.com):
//   w = adelante, s = atrás, a = girar izq, d = girar der, espacio o x = parar.
// Cada orden dura 2 s y luego el carrito se detiene solo.

void leerSerial() {
  while (Serial.available()) {
    char c = tolower(Serial.read());
    float izq = 0, der = 0;
    bool valido = true;
    if      (c == 'w') { izq =  1.0; der =  1.0; }
    else if (c == 's') { izq = -1.0; der = -1.0; }
    else if (c == 'a') { izq = -FACTOR_GIRO; der =  FACTOR_GIRO; }
    else if (c == 'd') { izq =  FACTOR_GIRO; der = -FACTOR_GIRO; }
    else if (c == ' ' || c == 'x') { izq = 0; der = 0; }
    else valido = false;   // ignora Enter y otros caracteres
    if (valido) {
      float v = 0.6 * PWM_MAX;   // 60 % de velocidad
      objetivoIzq = (int)(izq * v);
      objetivoDer = (int)(der * v);
      ultimoComando = millis();
      timeoutActual = 2000;
    }
  }
}

// Muestra por el monitor serial cada cambio de orden (útil para evidenciar la simulación)
void reportarCambios() {
  static int ultIzq = 9999, ultDer = 9999;
  if (objetivoIzq != ultIzq || objetivoDer != ultDer) {
    ultIzq = objetivoIzq;
    ultDer = objetivoDer;
    Serial.print("Objetivo PWM  izq=");
    Serial.print(objetivoIzq);
    Serial.print("  der=");
    Serial.println(objetivoDer);
  }
}

void loop() {
  server.handleClient();
  leerSerial();

  // Seguridad: sin órdenes recientes -> detenerse
  if (millis() - ultimoComando > timeoutActual) {
    objetivoIzq = objetivoDer = 0;
  }
  reportarCambios();

  static unsigned long tRampa = 0;
  if (millis() - tRampa >= PERIODO_RAMPA_MS) {
    tRampa = millis();
    actualIzq = acercar(actualIzq, objetivoIzq);
    actualDer = acercar(actualDer, objetivoDer);
    aplicarMotor(ENA, IN1, IN2, actualIzq, INVERTIR_IZQ);
    aplicarMotor(ENB, IN3, IN4, actualDer, INVERTIR_DER);
  }
}
