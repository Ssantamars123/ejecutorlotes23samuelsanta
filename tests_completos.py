"""
tests_completos.py  -  Bateria de pruebas automaticas del sistema.

Habla con ctrllt como un cliente y verifica TODAS las operaciones de los
cuatro servicios, incluidos los casos de error. Requiere que el sistema este
arrancado (lo hace el script correr_tests.sh).

Uso:  python3 tests_completos.py <carpeta_pipes> <carpeta_aralmac>
"""

import sys
import time

import protocolo as proto

P = sys.argv[1]
ARALMAC = sys.argv[2]
CLI_PET = P + "/cli.pet"
CLI_RESP = P + "/cli.resp"

passed = 0
failed = 0


def pedir(obj):
    proto.enviar(CLI_PET, obj)
    return proto.recibir(CLI_RESP)


def check(nombre, condicion, got=None):
    global passed, failed
    if condicion:
        passed += 1
        print("  PASS  " + nombre)
    else:
        failed += 1
        print("  FAIL  " + nombre + "   -> " + repr(got))


print("==================== GESFICH ====================")
r = pedir({"servicio": "gesfich", "operacion": "Crear"})
check("Crear devuelve f-0001", r.get("id-fichero") == "f-0001", r)

r = pedir({"servicio": "gesfich", "operacion": "Crear"})
check("Crear devuelve f-0002", r.get("id-fichero") == "f-0002", r)

r = pedir({"servicio": "gesfich", "operacion": "Leer"})
check("Leer (listar) ve f-0001 y f-0002",
      r.get("ficheros") == ["f-0001", "f-0002"], r)

# Actualizar f-0001 con el contenido de un archivo fuente real
fuente = ARALMAC + "/fuente.txt"
with open(fuente, "w") as f:
    f.write("contenido de prueba")
r = pedir({"servicio": "gesfich", "operacion": "Actualizar",
           "id-fichero": "f-0001", "ruta": fuente})
check("Actualizar f-0001 ok", r.get("estado") == "ok", r)

r = pedir({"servicio": "gesfich", "operacion": "Leer", "id-fichero": "f-0001"})
check("Leer f-0001 devuelve el contenido copiado",
      r.get("contenido") == "contenido de prueba", r)

r = pedir({"servicio": "gesfich", "operacion": "Leer", "id-fichero": "f-9999"})
check("Leer id inexistente -> error 'fichero no encontrado'",
      r.get("mensaje") == "fichero no encontrado", r)

r = pedir({"servicio": "gesfich", "operacion": "Actualizar", "id-fichero": "f-0001"})
check("Actualizar sin ruta -> 'faltan campos: id-fichero, ruta'",
      r.get("mensaje") == "faltan campos: id-fichero, ruta", r)

r = pedir({"servicio": "gesfich", "operacion": "Borrar", "id-fichero": "f-0002"})
check("Borrar f-0002 ok", r.get("estado") == "ok", r)
r = pedir({"servicio": "gesfich", "operacion": "Leer", "id-fichero": "f-0002"})
check("Leer f-0002 borrado -> error", r.get("estado") == "error", r)

r = pedir({"servicio": "gesfich", "operacion": "Suspender"})
check("Suspender ok", r.get("estado") == "ok", r)
r = pedir({"servicio": "gesfich", "operacion": "Crear"})
check("Crear con servicio suspendido -> 'servicio suspendido'",
      r.get("mensaje") == "servicio suspendido", r)
r = pedir({"servicio": "gesfich", "operacion": "Reasumir"})
check("Reasumir ok", r.get("estado") == "ok", r)

r = pedir({"servicio": "gesfich", "operacion": "OpInventada"})
check("Operacion desconocida -> 'operacion desconocida'",
      r.get("mensaje") == "operacion desconocida", r)


print("==================== GESPROG ====================")
r = pedir({"servicio": "gesprog", "operacion": "Guardar",
           "ejecutable": "/bin/echo", "args": ["hola"], "env": ["X=1"]})
check("Guardar devuelve p-0001", r.get("id-programa") == "p-0001", r)

r = pedir({"servicio": "gesprog", "operacion": "Guardar"})
check("Guardar sin ejecutable -> 'falta campo: ejecutable'",
      r.get("mensaje") == "falta campo: ejecutable", r)

r = pedir({"servicio": "gesprog", "operacion": "Leer", "id-programa": "p-0001"})
prog = r.get("programa", {})
check("Leer p-0001: nombre=echo", prog.get("nombre") == "echo", r)
check("Leer p-0001: args y env presentes",
      prog.get("args") == ["hola"] and prog.get("env") == ["X=1"], r)

r = pedir({"servicio": "gesprog", "operacion": "Leer"})
check("Leer (listar) ve p-0001", r.get("programas") == ["p-0001"], r)

r = pedir({"servicio": "gesprog", "operacion": "Actualizar",
           "id-programa": "p-0001", "ruta": "/usr/bin/python3"})
check("Actualizar ruta ok", r.get("estado") == "ok", r)
r = pedir({"servicio": "gesprog", "operacion": "Leer", "id-programa": "p-0001"})
check("Tras actualizar, nombre=python3",
      r.get("programa", {}).get("nombre") == "python3", r)

r = pedir({"servicio": "gesprog", "operacion": "Leer", "id-programa": "p-9999"})
check("Leer programa inexistente -> 'programa no encontrado'",
      r.get("mensaje") == "programa no encontrado", r)


print("==================== EJECUTOR ====================")
# Guardamos un programa de larga duracion para probar Estado/Matar/Suspender
r = pedir({"servicio": "gesprog", "operacion": "Guardar",
           "ejecutable": "/bin/sleep", "args": ["5"]})
id_sleep = r.get("id-programa")
check("Guardar /bin/sleep ok", id_sleep is not None, r)

r = pedir({"servicio": "ejecutor", "operacion": "Ejecutar", "id-programa": id_sleep})
id_e = r.get("id-ejecucion")
check("Ejecutar devuelve id de ejecucion", id_e == "e-0001", r)

r = pedir({"servicio": "ejecutor", "operacion": "Estado", "id-ejecucion": id_e})
check("Estado del proceso = Ejecutando",
      r.get("proceso-estado") == "Ejecutando", r)

r = pedir({"servicio": "ejecutor", "operacion": "Suspender"})
check("Suspender ejecutor ok", r.get("estado") == "ok", r)
r = pedir({"servicio": "ejecutor", "operacion": "Estado", "id-ejecucion": id_e})
check("Proceso = Suspendido tras Suspender",
      r.get("proceso-estado") == "Suspendido", r)
r = pedir({"servicio": "ejecutor", "operacion": "Ejecutar", "id-programa": id_sleep})
check("Ejecutar con servicio suspendido -> error",
      r.get("mensaje") == "servicio suspendido", r)
r = pedir({"servicio": "ejecutor", "operacion": "Reasumir"})
check("Reasumir ejecutor ok", r.get("estado") == "ok", r)
r = pedir({"servicio": "ejecutor", "operacion": "Estado", "id-ejecucion": id_e})
check("Proceso vuelve a Ejecutando tras Reasumir",
      r.get("proceso-estado") == "Ejecutando", r)

r = pedir({"servicio": "ejecutor", "operacion": "Matar", "id-ejecucion": id_e})
check("Matar ok", r.get("estado") == "ok", r)
r = pedir({"servicio": "ejecutor", "operacion": "Estado", "id-ejecucion": id_e})
check("Proceso = Terminado tras Matar",
      r.get("proceso-estado") == "Terminado", r)
check("codigo-salida presente tras terminar", "codigo-salida" in r, r)

# Proceso corto que termina con codigo 0, redirigiendo salida a un fichero
pedir({"servicio": "gesfich", "operacion": "Crear"})            # f-0003 (salida)
r = pedir({"servicio": "gesprog", "operacion": "Guardar", "ejecutable": "/bin/echo",
           "args": ["salida-redirigida"]})
id_echo = r.get("id-programa")
r = pedir({"servicio": "ejecutor", "operacion": "Ejecutar",
           "id-programa": id_echo, "stdout": "f-0003"})
id_e2 = r.get("id-ejecucion")
time.sleep(0.4)
r = pedir({"servicio": "ejecutor", "operacion": "Estado", "id-ejecucion": id_e2})
check("Proceso echo = Terminado con codigo 0",
      r.get("proceso-estado") == "Terminado" and r.get("codigo-salida") == 0, r)
r = pedir({"servicio": "gesfich", "operacion": "Leer", "id-fichero": "f-0003"})
check("La salida redirigida quedo en el fichero",
      r.get("contenido") == "salida-redirigida\n", r)

r = pedir({"servicio": "ejecutor", "operacion": "Estado"})
check("Estado (todos) devuelve una lista de procesos",
      isinstance(r.get("procesos"), list) and len(r["procesos"]) >= 2, r)

r = pedir({"servicio": "ejecutor", "operacion": "Ejecutar", "id-programa": "p-9999"})
check("Ejecutar programa inexistente -> error",
      r.get("estado") == "error", r)
r = pedir({"servicio": "ejecutor", "operacion": "Estado", "id-ejecucion": "e-9999"})
check("Estado de ejecucion inexistente -> 'proceso no encontrado'",
      r.get("mensaje") == "proceso no encontrado", r)


print("==================== CTRLLT ====================")
r = pedir({"servicio": "noexiste", "operacion": "X"})
check("Servicio desconocido -> 'servicio desconocido'",
      r.get("mensaje") == "servicio desconocido", r)
r = pedir({"servicio": "ctrllt", "operacion": "Inventada"})
check("Operacion ctrllt invalida -> 'operacion ctrllt desconocida'",
      r.get("mensaje") == "operacion ctrllt desconocida", r)

r = pedir({"servicio": "ctrllt", "operacion": "Terminar"})
check("ctrllt Terminar -> ok (apaga el sistema)", r.get("estado") == "ok", r)


print("")
print("=================================================")
print("RESULTADO:  %d PASARON,  %d FALLARON" % (passed, failed))
print("=================================================")
sys.exit(1 if failed else 0)
