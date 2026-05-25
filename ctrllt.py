"""
ctrllt.py  -  Controlador / Enrutador (el corazon del sistema)
==============================================================
Recibe peticiones del cliente, mira el campo "servicio" y REENVIA la
peticion al servicio correspondiente (gesfich/gesprog/ejecutor), espera su
respuesta y la devuelve al cliente SIN modificarla. Es una pasarela.

La unica operacion propia del controlador es "Terminar", que apaga todo
el sistema.

Sinopsis (PDF 3.3.1) -- el PDF reutiliza '-c' para dos cosas, asi que para
la respuesta de gesprog usamos '--pc' y lo documentamos en docs/Diseno.md:
    ctrllt.py -c <cli_pet> -a <cli_resp> \\
              -f <gesfich_pet> -b <gesfich_resp> \\
              -p <gesprog_pet> --pc <gesprog_resp> \\
              -e <ejecutor_pet> -d <ejecutor_resp>
"""

import argparse

import protocolo as proto


def main():
    ap = argparse.ArgumentParser(description="ctrllt - controlador/enrutador")
    ap.add_argument("-c", required=True, help="FIFO peticiones del cliente")
    ap.add_argument("-a", required=True, help="FIFO respuestas al cliente")
    ap.add_argument("-f", required=True, help="FIFO peticiones -> gesfich")
    ap.add_argument("-b", required=True, help="FIFO respuestas <- gesfich")
    ap.add_argument("-p", required=True, help="FIFO peticiones -> gesprog")
    ap.add_argument("--pc", required=True, help="FIFO respuestas <- gesprog")
    ap.add_argument("-e", required=True, help="FIFO peticiones -> ejecutor")
    ap.add_argument("-d", required=True, help="FIFO respuestas <- ejecutor")
    args = ap.parse_args()

    # Tuberias hacia el cliente: ctrllt las crea (PDF 3.3)
    proto.crear_fifo(args.c)
    proto.crear_fifo(args.a)

    # Tabla de enrutamiento: servicio -> (fifo_peticion, fifo_respuesta)
    rutas = {
        "gesfich": (args.f, args.b),
        "gesprog": (args.p, args.pc),
        "ejecutor": (args.e, args.d),
    }

    print("[ctrllt] Corriendo. Esperando peticiones del cliente en %s" % args.c)

    corriendo = True
    while corriendo:
        pet = proto.recibir(args.c)      # 1. leer peticion del cliente
        if pet is None:
            continue

        servicio = pet.get("servicio")

        # --- Operacion propia del controlador: Terminar el sistema ----------
        if servicio == "ctrllt":
            if pet.get("operacion") == "Terminar":
                # Propaga Terminar a gesfich y gesprog, Parar a ejecutor
                _propagar(rutas, "gesfich", {"servicio": "gesfich", "operacion": "Terminar"})
                _propagar(rutas, "gesprog", {"servicio": "gesprog", "operacion": "Terminar"})
                _propagar(rutas, "ejecutor", {"servicio": "ejecutor", "operacion": "Parar"})
                proto.enviar(args.a, proto.ok())
                corriendo = False
                continue
            proto.enviar(args.a, proto.error("operacion ctrllt desconocida"))
            continue

        # --- Enrutar a un servicio ------------------------------------------
        if servicio not in rutas:
            proto.enviar(args.a, proto.error("servicio desconocido"))
            continue

        fifo_pet, fifo_resp = rutas[servicio]
        try:
            proto.enviar(fifo_pet, pet)          # 2. reenviar al servicio
        except OSError:
            proto.enviar(args.a, proto.error("error enviando solicitud al servicio"))
            continue
        try:
            resp = proto.recibir(fifo_resp)      # 3. esperar su respuesta
        except OSError:
            proto.enviar(args.a, proto.error("error leyendo respuesta del servicio"))
            continue

        proto.enviar(args.a, resp)               # 4. devolver al cliente

    print("[ctrllt] Terminado. Sistema apagado.")


def _propagar(rutas, servicio, mensaje):
    """Envia un mensaje a un servicio y consume su respuesta (best-effort)."""
    fifo_pet, fifo_resp = rutas[servicio]
    try:
        proto.enviar(fifo_pet, mensaje)
        proto.recibir(fifo_resp)
    except OSError:
        pass


if __name__ == "__main__":
    main()
