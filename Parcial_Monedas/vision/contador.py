"""
contador.py
===========
Logica de conteo estable (sin dependencias de camara ni de modelo, para
poder probarla aparte).

Regla:
  1. Una moneda se cuenta solo si el modelo predice LA MISMA clase con
     confianza >= UMBRAL_CONFIANZA durante FRAMES_ESTABLES frames seguidos.
  2. Despues de contar, el contador queda "desarmado": aunque la moneda
     siga frente a la camara no se vuelve a contar.
  3. Se "rearma" solo cuando ve el fondo vacio FRAMES_VACIO frames seguidos
     (es decir, retiraste la moneda).
"""

import config


class ContadorEstable:
    def __init__(self, umbral=None, frames_estables=None, frames_vacio=None):
        self.umbral = umbral if umbral is not None else config.UMBRAL_CONFIANZA
        self.n_estable = frames_estables or config.FRAMES_ESTABLES
        self.n_vacio = frames_vacio or config.FRAMES_VACIO
        self.reiniciar()

    def reiniciar(self):
        self.conteo = {c: 0 for c in config.CLASES_MONEDA}
        self.armado = True
        self._racha_clase = None
        self._racha = 0
        self._racha_vacio = 0

    # ------------------------------------------------------------------
    def actualizar(self, clase, confianza):
        """Procesa la prediccion de un frame.

        Devuelve el nombre de la clase si en ESTE frame se conto una
        moneda nueva; si no, None.
        """
        # Prediccion dudosa: no suma a ninguna racha
        if confianza < self.umbral:
            self._racha_clase, self._racha = None, 0
            self._racha_vacio = 0
            return None

        if clase == config.CLASE_FONDO:
            self._racha_clase, self._racha = None, 0
            self._racha_vacio += 1
            if self._racha_vacio >= self.n_vacio:
                self.armado = True
            return None

        # Es una moneda
        self._racha_vacio = 0
        if not self.armado:
            return None
        if clase == self._racha_clase:
            self._racha += 1
        else:
            self._racha_clase, self._racha = clase, 1

        if self._racha >= self.n_estable:
            self.conteo[clase] += 1
            self.armado = False
            self._racha_clase, self._racha = None, 0
            return clase
        return None

    # ------------------------------------------------------------------
    @property
    def progreso(self):
        """0..1: que tan cerca esta de confirmar la moneda actual."""
        if not self.armado or self._racha_clase is None:
            return 0.0
        return min(1.0, self._racha / self.n_estable)

    @property
    def total_monedas(self):
        return sum(self.conteo.values())

    @property
    def total_pesos(self):
        return sum(n * config.CLASES[c][1] for c, n in self.conteo.items())
