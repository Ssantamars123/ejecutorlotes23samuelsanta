"""
gesprog.py  -  Gestor de Programas
==================================
Guarda los METADATOS de programas ejecutables en 'aralmac/programas/'.
Cada programa tiene un id  p-XXXX  y se guarda como  p-XXXX.json  con:
    { id-programa, nombre, ejecutable, args, env }

El campo 'ejecutable' (ruta completa) lo leera despues el ejecutor
directamente del disco (los servicios comparten el aralmac, no se hablan).

Sinopsis (PDF 3.5.1):
    gesprog.py -p <fifo_peticiones> [-c <fifo_respuestas>] -x <ruta_aralmac>
"""

import os
import json
import argparse

import protocolo as proto


class Gesprog:
    def __init__(self, aralmac):
        self.dir = os.path.join(aralmac, "programas")
        os.makedirs(self.dir, exist_ok=True)
        self.contador_path = os.path.join(self.dir, ".contador")
        self.estado = "Corriendo"

    def _siguiente_id(self):
        n = 0
        if os.path.exists(self.contador_path):
            with open(self.contador_path) as f:
                n = int(f.read().strip() or "0")
        n += 1
        with open(self.contador_path, "w") as f:
            f.write(str(n))
        return "p-%04d" % n

    def _ruta(self, id_programa):
        return os.path.join(self.dir, id_programa + ".json")

    # ---- operaciones (PDF 3.5.3 / 3.10) ------------------------------------
    def guardar(self, pet):
        ejecutable = pet.get("ejecutable")
        if not ejecutable:
            return proto.error("falta campo: ejecutable")
        id_p = self._siguiente_id()
        meta = {
            "id-programa": id_p,
            "nombre": os.path.basename(ejecutable),
            "ejecutable": ejecutable,
            "args": pet.get("args", []),
            "env": pet.get("env", []),
        }
        try:
            with open(self._ruta(id_p), "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except OSError:
            return proto.error("no se pudo guardar el programa")
        return proto.ok(**{"id-programa": id_p})

    def leer(self, pet):
        id_p = pet.get("id-programa")
        if id_p is None:
            # listar todos
            try:
                ids = sorted(x[:-5] for x in os.listdir(self.dir)
                             if x.startswith("p-") and x.endswith(".json"))
            except OSError:
                return proto.error("error al listar programas")
            return proto.ok(programas=ids)
        if not os.path.exists(self._ruta(id_p)):
            return proto.error("programa no encontrado")
        with open(self._ruta(id_p), encoding="utf-8") as f:
            meta = json.load(f)
        # PDF: el objeto 'programa' expone id-programa, nombre, args, env
        programa = {
            "id-programa": meta["id-programa"],
            "nombre": meta["nombre"],
            "args": meta["args"],
            "env": meta["env"],
        }
        return proto.ok(programa=programa)

    def actualizar(self, pet):
        id_p = pet.get("id-programa")
        ruta = pet.get("ruta")
        if not id_p or not ruta:
            return proto.error("faltan campos: id-programa, ruta")
        if not os.path.exists(self._ruta(id_p)):
            return proto.error("programa no encontrado")
        with open(self._ruta(id_p), encoding="utf-8") as f:
            meta = json.load(f)
        meta["ejecutable"] = ruta
        meta["nombre"] = os.path.basename(ruta)
        with open(self._ruta(id_p), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return proto.ok()

    def borrar(self, pet):
        id_p = pet.get("id-programa")
        if not id_p or not os.path.exists(self._ruta(id_p)):
            return proto.error("programa no encontrado")
        os.remove(self._ruta(id_p))
        return proto.ok()

    def procesar(self, pet):
        op = pet.get("operacion")
        if op == "Suspender":
            self.estado = "Suspendido"
            return proto.ok()
        if op == "Reasumir":
            self.estado = "Corriendo"
            return proto.ok()
        if op == "Terminar":
            self.estado = "Terminado"
            return proto.ok()

        if self.estado == "Suspendido":
            return proto.error("servicio suspendido")

        if op == "Guardar":
            return self.guardar(pet)
        if op == "Leer":
            return self.leer(pet)
        if op == "Actualizar":
            return self.actualizar(pet)
        if op == "Borrar":
            return self.borrar(pet)
        return proto.error("operacion desconocida")


def main():
    ap = argparse.ArgumentParser(description="gesprog - gestor de programas")
    ap.add_argument("-p", required=True, help="FIFO de peticiones")
    ap.add_argument("-c", help="FIFO de respuestas (half-duplex)")
    ap.add_argument("-x", required=True, help="ruta del aralmac")
    args = ap.parse_args()

    fifo_pet = args.p
    fifo_resp = args.c or (args.p + ".resp")
    proto.crear_fifo(fifo_pet)
    proto.crear_fifo(fifo_resp)

    servicio = Gesprog(args.x)
    print("[gesprog] Corriendo. peticiones=%s respuestas=%s" % (fifo_pet, fifo_resp))

    while servicio.estado != "Terminado":
        pet = proto.recibir(fifo_pet)
        if pet is None:
            continue
        resp = servicio.procesar(pet)
        proto.enviar(fifo_resp, resp)

    print("[gesprog] Terminado.")


if __name__ == "__main__":
    main()
