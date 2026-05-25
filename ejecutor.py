"""
ejecutor.py  -  Ejecutor de procesos por lotes
==============================================
Lanza programas REALES como subprocesos. Cada ejecucion tiene id  e-XXXX.
Lee los metadatos del programa (ejecutable, args, env) directamente del
aralmac (carpeta compartida con gesprog) y redirige stdin/stdout/stderr a
los ficheros gestionados por gesfich.

Sinopsis (PDF 3.6.1):
    ejecutor.py -e <fifo_peticiones> [-d <fifo_respuestas>] -x <ruta_aralmac>

Estados del proceso (PDF): "Ejecutando", "Suspendido", "Terminado".
"""

import os
import json
import signal
import argparse
import subprocess

import protocolo as proto


class Ejecutor:
    def __init__(self, aralmac):
        self.aralmac = aralmac
        self.dir_prog = os.path.join(aralmac, "programas")
        self.dir_fich = os.path.join(aralmac, "ficheros")
        self.estado = "Corriendo"          # Corriendo | Suspendido | Terminado
        self.contador = 0
        # id-ejecucion -> info del proceso
        self.procesos = {}                 # {e-XXXX: {"proc":Popen, "id-programa":..., "suspendido":bool}}

    def _siguiente_id(self):
        self.contador += 1
        return "e-%04d" % self.contador

    def _ruta_fichero(self, id_f):
        return os.path.join(self.dir_fich, id_f)

    # ---- operaciones (PDF 3.6.3 / 3.11) ------------------------------------
    def ejecutar(self, pet):
        id_p = pet.get("id-programa")
        if not id_p:
            return proto.error("falta campo: id-programa")
        meta_path = os.path.join(self.dir_prog, id_p + ".json")
        if not os.path.exists(meta_path):
            return proto.error("no se pudo ejecutar el programa")
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        # Preparar la linea de comando: ejecutable + argumentos
        comando = [meta["ejecutable"]] + list(meta.get("args", []))

        # Variables de entorno: partimos del entorno actual y agregamos las del programa
        entorno = dict(os.environ)
        for par in meta.get("env", []):
            if "=" in par:
                clave, valor = par.split("=", 1)
                entorno[clave] = valor

        # Redirecciones: stdin/stdout/stderr son ids de fichero (opcionales)
        f_in = f_out = f_err = None
        try:
            if pet.get("stdin"):
                f_in = open(self._ruta_fichero(pet["stdin"]), "r")
            if pet.get("stdout"):
                f_out = open(self._ruta_fichero(pet["stdout"]), "w")
            if pet.get("stderr"):
                f_err = open(self._ruta_fichero(pet["stderr"]), "w")
            proc = subprocess.Popen(comando, stdin=f_in, stdout=f_out,
                                    stderr=f_err, env=entorno)
        except OSError:
            return proto.error("no se pudo ejecutar el programa")

        id_e = self._siguiente_id()
        self.procesos[id_e] = {"proc": proc, "id-programa": id_p, "suspendido": False}
        return proto.ok(**{"id-ejecucion": id_e})

    def _estado_de(self, id_e):
        """Construye el objeto de estado de un proceso (PDF 3.11.2)."""
        info = self.procesos[id_e]
        proc = info["proc"]
        obj = {"id-ejecucion": id_e, "id-programa": info["id-programa"]}
        codigo = proc.poll()
        if info["suspendido"]:
            obj["proceso-estado"] = "Suspendido"
        elif codigo is None:
            obj["proceso-estado"] = "Ejecutando"
        else:
            obj["proceso-estado"] = "Terminado"
            obj["codigo-salida"] = codigo
        return obj

    def estado_op(self, pet):
        id_e = pet.get("id-ejecucion")
        if id_e is None:
            # listar todos
            return proto.ok(procesos=[self._estado_de(e) for e in self.procesos])
        if id_e not in self.procesos:
            return proto.error("proceso no encontrado")
        return proto.ok(**self._estado_de(id_e))

    def matar(self, pet):
        id_e = pet.get("id-ejecucion")
        if not id_e or id_e not in self.procesos:
            return proto.error("falta campo: id-ejecucion")
        proc = self.procesos[id_e]["proc"]
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        return proto.ok()

    def suspender(self):
        # Detiene (SIGSTOP) todos los procesos activos y bloquea nuevas ejecuciones
        for info in self.procesos.values():
            if info["proc"].poll() is None:
                info["proc"].send_signal(signal.SIGSTOP)
                info["suspendido"] = True
        self.estado = "Suspendido"
        return proto.ok()

    def reasumir(self):
        for info in self.procesos.values():
            if info["suspendido"] and info["proc"].poll() is None:
                info["proc"].send_signal(signal.SIGCONT)
                info["suspendido"] = False
        self.estado = "Corriendo"
        return proto.ok()

    def parar(self):
        # No acepta nuevas ejecuciones y espera a que terminen las activas
        for info in self.procesos.values():
            if info["proc"].poll() is None:
                info["proc"].wait()
        self.estado = "Terminado"
        return proto.ok()

    def procesar(self, pet):
        op = pet.get("operacion")
        if op == "Suspender":
            return self.suspender()
        if op == "Reasumir":
            return self.reasumir()
        if op == "Parar":
            return self.parar()

        # Solo se bloquean NUEVAS ejecuciones cuando el servicio esta suspendido;
        # Estado y Matar siguen disponibles (PDF 3.11.1).
        if op == "Ejecutar":
            if self.estado == "Suspendido":
                return proto.error("servicio suspendido")
            return self.ejecutar(pet)
        if op == "Estado":
            return self.estado_op(pet)
        if op == "Matar":
            return self.matar(pet)
        return proto.error("operacion desconocida")


def main():
    ap = argparse.ArgumentParser(description="ejecutor - ejecutor de procesos")
    ap.add_argument("-e", required=True, help="FIFO de peticiones")
    ap.add_argument("-d", help="FIFO de respuestas (half-duplex)")
    ap.add_argument("-x", required=True, help="ruta del aralmac")
    args = ap.parse_args()

    fifo_pet = args.e
    fifo_resp = args.d or (args.e + ".resp")
    proto.crear_fifo(fifo_pet)
    proto.crear_fifo(fifo_resp)

    servicio = Ejecutor(args.x)
    print("[ejecutor] Corriendo. peticiones=%s respuestas=%s" % (fifo_pet, fifo_resp))

    while servicio.estado != "Terminado":
        pet = proto.recibir(fifo_pet)
        if pet is None:
            continue
        resp = servicio.procesar(pet)
        proto.enviar(fifo_resp, resp)

    print("[ejecutor] Terminado.")


if __name__ == "__main__":
    main()
