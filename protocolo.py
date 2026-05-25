"""
protocolo.py
============
Codigo COMPARTIDO por todos los servicios (gesfich, gesprog, ejecutor, ctrllt).

Implementa la comunicacion del PDF:
  - Tuberias nombradas  -> os.mkfifo (named pipes de Linux)
  - Mensajes JSON terminados en salto de linea '\\n'
  - Tamano maximo de mensaje: 4096 bytes

Como una FIFO es de UN solo sentido, cada "conexion" usa DOS tuberias
(modelo half-duplex que menciona el PDF):
    - una para PETICIONES
    - otra para RESPUESTAS

Patron de sincronizacion (el truco que hace todo simple):
  abrir una FIFO BLOQUEA hasta que el otro extremo tambien la abre.
  Por eso, con abrir->escribir/leer->cerrar en cada mensaje, el orden
  de los procesos queda sincronizado solo, sin hilos ni locks.
"""

import os
import json

MSG_MAX_LEN = 4096  # bytes por mensaje (requisito del PDF)


def crear_fifo(ruta):
    """Crea la tuberia nombrada si no existe todavia."""
    if not os.path.exists(ruta):
        os.mkfifo(ruta)


def enviar(ruta_fifo, objeto):
    """Convierte 'objeto' (dict) a JSON + '\\n' y lo escribe en la FIFO.

    open(..., 'w') se BLOQUEA hasta que alguien abra el otro extremo
    para leer. Eso sincroniza los dos procesos automaticamente.
    """
    linea = json.dumps(objeto, ensure_ascii=False) + "\n"
    datos = linea.encode("utf-8")
    if len(datos) > MSG_MAX_LEN:
        raise ValueError("mensaje excede MSG_MAX_LEN (4096 bytes)")
    with open(ruta_fifo, "w", encoding="utf-8") as f:
        f.write(linea)


def recibir(ruta_fifo):
    """Lee una linea de la FIFO y la convierte de JSON a dict.

    open(..., 'r') se BLOQUEA hasta que alguien abra el otro extremo
    para escribir. Devuelve None si el otro extremo cerro sin enviar nada.
    """
    with open(ruta_fifo, "r", encoding="utf-8") as f:
        linea = f.readline()
    if not linea:
        return None
    return json.loads(linea)


# --- Atajos para construir respuestas estandar del PDF -----------------------

def ok(**campos):
    """Respuesta de exito: {'estado':'ok', ...campos extra...}"""
    resp = {"estado": "ok"}
    resp.update(campos)
    return resp


def error(mensaje):
    """Respuesta de error: {'estado':'error','mensaje':'...'}"""
    return {"estado": "error", "mensaje": mensaje}
