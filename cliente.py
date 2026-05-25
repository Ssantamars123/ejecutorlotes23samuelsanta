"""
cliente.py  -  Cliente de prueba
================================
Envia UNA peticion JSON a ctrllt y muestra la respuesta. Sirve para la
demostracion y las pruebas.

Sinopsis (PDF 3.2.1):
    cliente.py -c <fifo_peticiones> [-a <fifo_respuestas>] '<json>'

Ejemplo:
    python3 cliente.py -c /tmp/ejlotes/cli.pet -a /tmp/ejlotes/cli.resp \\
        '{"servicio":"gesfich","operacion":"Crear"}'
"""

import json
import argparse

import protocolo as proto


def main():
    ap = argparse.ArgumentParser(description="cliente de prueba")
    ap.add_argument("-c", required=True, help="FIFO de peticiones a ctrllt")
    ap.add_argument("-a", help="FIFO de respuestas de ctrllt")
    ap.add_argument("mensaje", help="peticion en formato JSON")
    args = ap.parse_args()

    fifo_pet = args.c
    fifo_resp = args.a or (args.c.replace(".pet", ".resp"))

    peticion = json.loads(args.mensaje)   # valida que el JSON sea correcto
    proto.enviar(fifo_pet, peticion)
    respuesta = proto.recibir(fifo_resp)
    print(json.dumps(respuesta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
