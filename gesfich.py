"""
gesfich.py  -  Gestor de Ficheros
=================================
Crea, lee, actualiza y borra ficheros guardados en la carpeta 'aralmac'.
Cada fichero tiene un id con formato  f-XXXX  (f-0001, f-0002, ...).

Sinopsis (PDF 3.4.1):
    gesfich.py -f <fifo_peticiones> [-b <fifo_respuestas>] -x <ruta_aralmac>

Maquina de estados (PDF fig.3): Corriendo <-> Suspendido -> Terminado.
Cuando esta Suspendido, las operaciones de datos devuelven error.
"""

import os
import shutil
import argparse

import protocolo as proto


class Gesfich:
    def __init__(self, aralmac):
        # 'aralmac' es la carpeta de almacenamiento. Los ficheros van en
        # aralmac/ficheros/  y un contador para generar ids unicos.
        self.dir = os.path.join(aralmac, "ficheros")
        os.makedirs(self.dir, exist_ok=True)
        self.contador_path = os.path.join(self.dir, ".contador")
        self.estado = "Corriendo"  # Corriendo | Suspendido | Terminado

    # ---- utilidades de ids -------------------------------------------------
    def _siguiente_id(self):
        """Devuelve el siguiente id unico f-XXXX usando un contador en disco."""
        n = 0
        if os.path.exists(self.contador_path):
            with open(self.contador_path) as f:
                n = int(f.read().strip() or "0")
        n += 1
        with open(self.contador_path, "w") as f:
            f.write(str(n))
        return "f-%04d" % n

    def _ruta(self, id_fichero):
        return os.path.join(self.dir, id_fichero)

    # ---- operaciones (PDF 3.4.3 / 3.9) -------------------------------------
    def crear(self):
        id_f = self._siguiente_id()
        try:
            open(self._ruta(id_f), "w").close()  # fichero vacio
        except OSError:
            return proto.error("no se pudo crear el fichero")
        return proto.ok(**{"id-fichero": id_f})

    def leer(self, pet):
        id_f = pet.get("id-fichero")
        if id_f is None:
            # Sin id -> listar todos los ficheros existentes
            try:
                ids = sorted(x for x in os.listdir(self.dir)
                             if x.startswith("f-"))
            except OSError:
                return proto.error("error al listar ficheros")
            return proto.ok(ficheros=ids)
        # Con id -> devolver contenido
        if not os.path.exists(self._ruta(id_f)):
            return proto.error("fichero no encontrado")
        with open(self._ruta(id_f), encoding="utf-8") as f:
            return proto.ok(contenido=f.read())

    def actualizar(self, pet):
        id_f = pet.get("id-fichero")
        ruta = pet.get("ruta")
        if not id_f or not ruta:
            return proto.error("faltan campos: id-fichero, ruta")
        if not os.path.exists(self._ruta(id_f)) or not os.path.exists(ruta):
            return proto.error("no se pudo actualizar el fichero")
        try:
            shutil.copyfile(ruta, self._ruta(id_f))
        except OSError:
            return proto.error("no se pudo actualizar el fichero")
        return proto.ok()

    def borrar(self, pet):
        id_f = pet.get("id-fichero")
        if not id_f or not os.path.exists(self._ruta(id_f)):
            return proto.error("fichero no encontrado")
        os.remove(self._ruta(id_f))
        return proto.ok()

    # ---- enrutador interno de operaciones ----------------------------------
    def procesar(self, pet):
        op = pet.get("operacion")

        # Transiciones de estado: siempre permitidas
        if op == "Suspender":
            self.estado = "Suspendido"
            return proto.ok()
        if op == "Reasumir":
            self.estado = "Corriendo"
            return proto.ok()
        if op == "Terminar":
            self.estado = "Terminado"
            return proto.ok()

        # Operaciones de datos: bloqueadas si esta suspendido
        if self.estado == "Suspendido":
            return proto.error("servicio suspendido")

        if op == "Crear":
            return self.crear()
        if op == "Leer":
            return self.leer(pet)
        if op == "Actualizar":
            return self.actualizar(pet)
        if op == "Borrar":
            return self.borrar(pet)

        return proto.error("operacion desconocida")


def main():
    ap = argparse.ArgumentParser(description="gesfich - gestor de ficheros")
    ap.add_argument("-f", required=True, help="FIFO de peticiones")
    ap.add_argument("-b", help="FIFO de respuestas (half-duplex)")
    ap.add_argument("-x", required=True, help="ruta del aralmac")
    args = ap.parse_args()

    fifo_pet = args.f
    fifo_resp = args.b or (args.f + ".resp")  # si no dan -b, derivamos uno
    proto.crear_fifo(fifo_pet)
    proto.crear_fifo(fifo_resp)

    servicio = Gesfich(args.x)
    print("[gesfich] Corriendo. peticiones=%s respuestas=%s" % (fifo_pet, fifo_resp))

    # Bucle principal: el MISMO esqueleto en los 4 servicios
    while servicio.estado != "Terminado":
        pet = proto.recibir(fifo_pet)   # 1. leer peticion (bloquea)
        if pet is None:
            continue
        resp = servicio.procesar(pet)   # 2. hacer la accion
        proto.enviar(fifo_resp, resp)   # 3. responder

    print("[gesfich] Terminado.")


if __name__ == "__main__":
    main()
