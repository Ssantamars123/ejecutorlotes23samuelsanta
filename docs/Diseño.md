# Documento de Diseño — Ejecutor de Lotes

**Asignatura:** ST0257 — Sistemas Operativos
**Práctica:** V-II — Ejecutor de Lotes
**Autor:** Samuel Santamaría
**Lenguaje:** Python 3 (sólo biblioteca estándar)
**Plataforma objetivo:** Linux (probado en WSL/Ubuntu sobre Windows)

---

## Tabla de contenido

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura general](#2-arquitectura-general)
3. [Mecanismo de comunicación](#3-mecanismo-de-comunicación)
4. [Protocolo de mensajes](#4-protocolo-de-mensajes)
5. [Componentes en detalle](#5-componentes-en-detalle)
6. [Máquinas de estado](#6-máquinas-de-estado)
7. [Almacenamiento (`aralmac`)](#7-almacenamiento-aralmac)
8. [Decisiones de diseño](#8-decisiones-de-diseño)
9. [Flujos de ejecución típicos](#9-flujos-de-ejecución-típicos)
10. [Manejo de errores](#10-manejo-de-errores)
11. [Pruebas](#11-pruebas)
12. [Cómo ejecutar](#12-cómo-ejecutar)
13. [Mapa del repositorio](#13-mapa-del-repositorio)

---

## 1. Resumen ejecutivo

El sistema simula el **ejecutor de lotes** de un *mainframe*: un usuario
solicita la ejecución de programas que reciben entrada de ficheros
almacenados, generan salida en otros ficheros, y cuyo ciclo de vida puede
controlarse (suspender, reasumir, matar). Todo se hace mediante un
cliente que dialoga con un controlador central, el cual reenvía las
peticiones a los tres servicios especializados.

**Cuatro procesos principales** (+ cliente):

| Proceso     | Rol                                                          |
|-------------|--------------------------------------------------------------|
| `cliente`   | Envía una petición JSON y muestra la respuesta.              |
| `ctrllt`    | Controlador / enrutador. Único punto de entrada del sistema. |
| `gesfich`   | Gestor de ficheros (CRUD en `aralmac/ficheros/`).            |
| `gesprog`   | Gestor de programas (metadatos en `aralmac/programas/`).     |
| `ejecutor`  | Lanza programas como subprocesos reales del SO.              |

**Comunicación:** tuberías nombradas POSIX (`os.mkfifo`) con mensajes
JSON terminados en `\n`, máximo 4096 bytes (requisito del enunciado).

**Almacenamiento:** carpeta `aralmac/` compartida en disco (no es un
proceso). Es el único acoplamiento entre `gesprog` y `ejecutor`.

---

## 2. Arquitectura general

### 2.1 Diagrama de bloques

```
   ┌───────────┐
   │  cliente  │
   └─────┬─────┘
         │ FIFO cli.pet / cli.resp
         ▼
   ┌───────────┐         FIFO gf.pet/gf.resp        ┌───────────┐
   │           │ ──────────────────────────────────►│  gesfich  │
   │           │ ◄──────────────────────────────────│           │
   │           │         FIFO gp.pet/gp.resp        ┌───────────┐
   │  ctrllt   │ ──────────────────────────────────►│  gesprog  │
   │ (enruta-  │ ◄──────────────────────────────────│           │
   │   dor)    │         FIFO ej.pet/ej.resp        ┌───────────┐
   │           │ ──────────────────────────────────►│ ejecutor  │
   │           │ ◄──────────────────────────────────│           │
   └───────────┘                                    └─────┬─────┘
                                                          │ Popen()
                                                          ▼
                                                    [procesos hijos]
   ┌────────────────────────────────────────────────────────────────┐
   │                       aralmac/  (disco)                        │
   │   ficheros/   programas/   .contador                            │
   └────────────────────────────────────────────────────────────────┘
        ▲                ▲                  ▲
     gesfich          gesprog            ejecutor (lectura)
```

### 2.2 Reglas de acoplamiento

- El cliente **solo** habla con `ctrllt`.
- Los tres servicios internos **solo** hablan con `ctrllt`.
- **Nunca** un servicio interno habla con otro servicio interno por
  tuberías. Si necesitan compartir datos lo hacen vía `aralmac/`.
- `aralmac/` es **memoria estable compartida**, no un proceso.

### 2.3 Razones de la arquitectura

- **Separación de responsabilidades** (PDF, principio explícito): cada
  servicio tiene un único dominio.
- **Enrutador centralizado**: simplifica el cliente (sólo conoce una
  pareja de FIFOs) y permite cambiar internamente cualquier servicio sin
  afectar al resto.
- **Acoplamiento por disco**: evita dependencias circulares entre
  servicios y permite que `ejecutor` recupere programas guardados aunque
  `gesprog` no esté activo en ese instante (siempre que el JSON exista).

---

## 3. Mecanismo de comunicación

### 3.1 Tuberías nombradas (FIFOs)

Una FIFO es un archivo especial del sistema de ficheros POSIX que se
comporta como una cola. Se crea con `os.mkfifo(ruta)`. Características:

- **Unidireccional**: un extremo escribe, el otro lee.
- **Bloqueante**: `open()` bloquea hasta que el otro extremo abre.
- **Pequeña**: el kernel reserva un *buffer* (típ. 64 KB).
- Vive en el sistema de ficheros, lo que permite que procesos sin
  relación parentesco se conecten por nombre.

### 3.2 Modelo half-duplex con dos FIFOs por conexión

Como cada FIFO es de un solo sentido, cada par de procesos que se
comunica usa **dos**: una para peticiones, otra para respuestas. Es lo
que el enunciado llama modelo *half-duplex* y motiva las opciones
`-a/-b/-c/-d` (un extremo por opción).

```
       fifo_peticion
ctrllt ─────────────► gesfich
ctrllt ◄───────────── gesfich
       fifo_respuesta
```

### 3.3 Sincronización implícita

`open(fifo, "w")` bloquea hasta que algún proceso abra el mismo fifo
para lectura; y viceversa. Eso ordena los procesos **sin necesidad de
hilos ni cerrojos**. El patrón usado en todo el código:

```python
# Escritor:                      # Lector:
with open(fifo, "w") as f:       with open(fifo, "r") as f:
    f.write(linea)                   linea = f.readline()
```

### 3.4 Capa común `protocolo.py`

Toda la complejidad de la comunicación está centralizada en un único
módulo de ~30 líneas:

```python
crear_fifo(ruta)       # os.mkfifo si no existe
enviar(ruta, objeto)   # dict -> JSON + '\n' -> escribe
recibir(ruta)          # readline -> JSON -> dict (o None)
ok(**campos)           # {"estado":"ok", ...}
error(mensaje)         # {"estado":"error","mensaje":"..."}
```

### 3.5 Ubicación de las tuberías

En WSL las FIFOs se crean en **`/tmp/ejlotes/`** (sistema de archivos
nativo de Linux, `ext4`). En `/mnt/c` (NTFS) `mkfifo` falla, por lo que
el proyecto separa:

- **FIFOs**: `/tmp/ejlotes/`
- **Código y `aralmac`**: carpeta del proyecto (puede estar en NTFS).

---

## 4. Protocolo de mensajes

### 4.1 Sintaxis

Cada mensaje es **una línea** de JSON UTF-8 terminada en `\n`, con un
máximo de **4096 bytes** (requisito del enunciado).

### 4.2 Petición

```jsonc
{
  "servicio": "gesfich",     // gesfich | gesprog | ejecutor | ctrllt
  "operacion": "Crear",      // depende del servicio
  ...                        // campos propios de la operacion
}
```

### 4.3 Respuesta

Éxito:
```json
{ "estado": "ok", "...": "..." }
```

Error:
```json
{ "estado": "error", "mensaje": "descripcion corta" }
```

### 4.4 Identificadores

| Tipo      | Formato | Ejemplo  | Generador                       |
|-----------|---------|----------|---------------------------------|
| Fichero   | `f-XXXX`| `f-0001` | Contador en `aralmac/ficheros/.contador` |
| Programa  | `p-XXXX`| `p-0001` | Contador en `aralmac/programas/.contador`|
| Ejecución | `e-XXXX`| `e-0001` | Contador en memoria del ejecutor |

Los contadores en disco sobreviven a reinicios de los servicios. El
contador del ejecutor es en memoria porque las ejecuciones (procesos
vivos) no sobreviven al apagado.

---

## 5. Componentes en detalle

### 5.1 Bucle común de los servicios

Los cuatro siguen el mismo esqueleto (sólo cambia `procesar`):

```python
while estado != "Terminado":
    pet  = proto.recibir(fifo_peticiones)   # 1. lee (bloquea)
    if pet is None: continue
    resp = servicio.procesar(pet)           # 2. ejecuta
    proto.enviar(fifo_respuestas, resp)     # 3. responde
```

### 5.2 `gesfich` — Gestor de Ficheros

**Sinopsis CLI:**
```
gesfich.py -f <fifo_peticiones> -b <fifo_respuestas> -x <ruta_aralmac>
```

**Operaciones:**

| Operación   | Campos                          | Devuelve                                  |
|-------------|---------------------------------|-------------------------------------------|
| `Crear`     | —                               | `id-fichero`                              |
| `Leer`      | `id-fichero` (opc.)             | `contenido` o lista `ficheros`            |
| `Actualizar`| `id-fichero`, `ruta`            | —                                         |
| `Borrar`    | `id-fichero`                    | —                                         |
| `Suspender` | —                               | —                                         |
| `Reasumir`  | —                               | —                                         |
| `Terminar`  | —                               | —                                         |

### 5.3 `gesprog` — Gestor de Programas

**Sinopsis CLI:**
```
gesprog.py -p <fifo_peticiones> -c <fifo_respuestas> -x <ruta_aralmac>
```

**Formato persistido** (`aralmac/programas/p-XXXX.json`):
```json
{
  "id-programa": "p-0001",
  "nombre":      "cat",
  "ejecutable":  "/bin/cat",
  "args":        [],
  "env":         []
}
```

**Operaciones:** `Guardar`, `Leer` (id o todos), `Actualizar`, `Borrar`,
`Suspender`, `Reasumir`, `Terminar`.

### 5.4 `ejecutor` — Ejecutor de Procesos

**Sinopsis CLI:**
```
ejecutor.py -e <fifo_peticiones> -d <fifo_respuestas> -x <ruta_aralmac>
```

**Operaciones:**

| Operación   | Campos                                                       |
|-------------|--------------------------------------------------------------|
| `Ejecutar`  | `id-programa`, `stdin`/`stdout`/`stderr` (ids de fichero, opc.) |
| `Estado`    | `id-ejecucion` (opc.; sin él, lista todos)                    |
| `Matar`     | `id-ejecucion`                                                |
| `Suspender` | — (SIGSTOP a todos los procesos vivos)                        |
| `Reasumir`  | — (SIGCONT a los suspendidos)                                  |
| `Parar`     | — (no acepta nuevas ejecuciones; espera a las activas)        |

**Detalles de implementación:**

- Lee el JSON del programa **directamente** de `aralmac/programas/p-XXXX.json`.
- Resuelve los campos `stdin/stdout/stderr` (ids `f-XXXX`) a rutas reales
  en `aralmac/ficheros/` y los abre en el modo adecuado.
- Construye `env` partiendo de `os.environ` y aplicando los pares
  `clave=valor` del programa.
- Usa `subprocess.Popen(comando, stdin=..., stdout=..., stderr=..., env=...)`.
- `proc.poll()` distingue Ejecutando (None) / Terminado (int).
- `Suspender` envía `SIGSTOP`; `Reasumir`, `SIGCONT`.
- `Matar` envía `SIGKILL` y hace `wait()`.
- Excepción intencionada al PDF: `Estado` y `Matar` siguen disponibles
  con el servicio `Suspendido`. Suspender el servicio sólo bloquea
  **nuevas** ejecuciones (PDF 3.11.1).

### 5.5 `ctrllt` — Controlador / Enrutador

**Sinopsis CLI:**
```
ctrllt.py \
  -c <cli_pet> -a <cli_resp> \
  -f <gf_pet>  -b <gf_resp> \
  -p <gp_pet>  --pc <gp_resp> \
  -e <ej_pet>  -d <ej_resp>
```

**Lógica:**

```python
rutas = {
  "gesfich":  (gf_pet, gf_resp),
  "gesprog":  (gp_pet, gp_resp),
  "ejecutor": (ej_pet, ej_resp),
}

while corriendo:
    pet = recibir(cli_pet)
    svc = pet["servicio"]
    if svc == "ctrllt":
        ...   # operacion Terminar => propagar y salir
    elif svc in rutas:
        enviar(rutas[svc][0], pet)
        resp = recibir(rutas[svc][1])
        enviar(cli_resp, resp)
    else:
        enviar(cli_resp, error("servicio desconocido"))
```

**Única operación propia:** `Terminar`. Propaga `Terminar` a `gesfich` y
`gesprog`, `Parar` al `ejecutor`, devuelve `ok` al cliente y finaliza.

**Nota sobre opciones:** el enunciado reutiliza `-c` para dos cosas
distintas (controlador y respuesta de `gesprog`). Para evitar colisión
de `argparse`, la respuesta de `gesprog` se pasa con `--pc`.

### 5.6 `cliente.py`

Trivial. Lee una petición JSON desde la línea de comandos, la envía a
`ctrllt` y muestra la respuesta. No mantiene estado.

---

## 6. Máquinas de estado

### 6.1 `gesfich` y `gesprog`

```
        Suspender                  Terminar
Corriendo ─────────► Suspendido ───────────► Terminado
       ◄──────────
         Reasumir
```

- En **Suspendido**, las operaciones de **datos** devuelven
  `{"estado":"error","mensaje":"servicio suspendido"}`.
- Las transiciones se permiten siempre.

### 6.2 `ejecutor`

```
        Suspender                   Parar
Corriendo ─────────► Suspendido ──────────► Terminado
       ◄──────────                    (cuando ya no quedan procesos)
         Reasumir
```

- En **Suspendido** se bloquean **nuevas** ejecuciones; `Estado` y
  `Matar` siguen funcionando.
- `Parar` no acepta nuevas ejecuciones y hace `wait()` por cada proceso
  activo antes de pasar a `Terminado`.

### 6.3 Estados de un PROCESO ejecutado

Para cada `id-ejecucion` (no del servicio):

| Estado       | Condición                                              |
|--------------|--------------------------------------------------------|
| `Ejecutando` | `proc.poll() is None` y no está marcado como suspendido. |
| `Suspendido` | Marcado tras `SIGSTOP` y aún no reanudado.              |
| `Terminado`  | `proc.poll()` devuelve un entero (=`codigo-salida`).    |

---

## 7. Almacenamiento (`aralmac`)

Carpeta compartida en disco. Es la **única** memoria persistente del
sistema. Estructura:

```
aralmac/
├── ficheros/
│   ├── .contador           # último id emitido por gesfich
│   ├── f-0001              # contenido del fichero
│   ├── f-0002
│   └── ...
└── programas/
    ├── .contador           # último id emitido por gesprog
    ├── p-0001.json         # metadatos del programa
    ├── p-0002.json
    └── ...
```

- `gesfich` es **dueño** de `ficheros/`.
- `gesprog` es **dueño** de `programas/`.
- `ejecutor` sólo tiene **lectura**: nunca crea, modifica o borra nada
  en `aralmac/`.

---

## 8. Decisiones de diseño

1. **Una sola capa de comunicación** (`protocolo.py`) reutilizada por
   los 4 servicios. Cambiar el formato del mensaje toca un único módulo.
2. **Atención secuencial en `ctrllt`**. Es simple, correcto y suficiente
   para la práctica. La concurrencia se podría añadir luego con un *pool*
   de hilos sin tocar los servicios.
3. **Servicios autocontenidos**: no se hablan entre sí. Esto elimina
   dependencias circulares y facilita el testeo aislado.
4. **Contadores en disco** para los ids de fichero y programa: sobreviven
   a reinicios. El contador del ejecutor es en memoria porque los PIDs
   no sobreviven al apagado del proceso.
5. **FIFOs en `/tmp/ejlotes/`**: WSL no permite FIFOs sobre NTFS.
6. **`--pc` en lugar de `-c`** para la respuesta de `gesprog` en
   `ctrllt`, evitando colisión con `-c` (controlador).
7. **`Estado` y `Matar` siguen disponibles** con el ejecutor suspendido.
   Sólo se bloquea `Ejecutar`. (Coherente con PDF 3.11.1.)
8. **Sin dependencias externas**: sólo biblioteca estándar de Python 3.
   Funciona en cualquier Ubuntu/WSL con `python3` instalado.

---

## 9. Flujos de ejecución típicos

### 9.1 Crear un fichero

```
cliente ──{servicio:gesfich, operacion:Crear}──► ctrllt
ctrllt  ──(reenvia)──► gesfich
gesfich ── crea aralmac/ficheros/f-0001 ──► gesfich
gesfich ──{estado:ok, id-fichero:f-0001}──► ctrllt ──► cliente
```

### 9.2 Ejecutar un programa con redirecciones

```
1) cliente ► gesprog: Guardar (ejecutable=/bin/cat)
            ◄ ok, id-programa=p-0001
2) cliente ► gesfich: Crear  (entrada)
            ◄ ok, id-fichero=f-0001
3) cliente ► gesfich: Crear  (salida)
            ◄ ok, id-fichero=f-0002
   (relleno manual de f-0001 desde shell para la demo)
4) cliente ► ejecutor: Ejecutar p-0001, stdin=f-0001, stdout=f-0002
            ◄ ok, id-ejecucion=e-0001
5) cliente ► ejecutor: Estado de e-0001
            ◄ ok, proceso-estado=Terminado, codigo-salida=0
6) cliente ► gesfich: Leer f-0002
            ◄ ok, contenido="..."
```

### 9.3 Apagado ordenado

```
cliente ► ctrllt: Terminar
ctrllt  ► gesfich: Terminar      (propaga)
ctrllt  ► gesprog: Terminar      (propaga)
ctrllt  ► ejecutor: Parar        (espera procesos vivos)
ctrllt  ◄ ok → cliente
ctrllt  finaliza.
```

---

## 10. Manejo de errores

| Situación                                       | Respuesta                                                                 |
|-------------------------------------------------|---------------------------------------------------------------------------|
| Servicio en `pet["servicio"]` no existe          | `{"estado":"error","mensaje":"servicio desconocido"}`                     |
| Operación desconocida del servicio              | `{"estado":"error","mensaje":"operacion desconocida"}`                    |
| Operación de `ctrllt` desconocida               | `{"estado":"error","mensaje":"operacion ctrllt desconocida"}`             |
| Faltan campos en la petición                    | `{"estado":"error","mensaje":"faltan campos: <lista>"}` o `falta campo: <x>` |
| Servicio de datos suspendido                    | `{"estado":"error","mensaje":"servicio suspendido"}`                      |
| Recurso no existe (fichero/programa/ejecucion)  | `... "no encontrado"`                                                     |
| Error de E/S del SO                             | Mensaje específico por operación                                          |
| Mensaje > 4096 bytes                            | `ValueError` en el remitente (no es respuesta — es bug del cliente)        |

Los servicios **nunca caen** por una petición malformada: devuelven
error y siguen escuchando.

---

## 11. Pruebas

Batería automática en `tests_completos.py`. **40 tests** distribuidos:

| Suite     | N° tests | Cubre                                                                  |
|-----------|----------|------------------------------------------------------------------------|
| gesfich   | 13       | CRUD, listado, errores, suspensión/reanudación, operación desconocida.|
| gesprog   | 8        | Guardar, leer/listar, actualizar, errores de campos faltantes.        |
| ejecutor  | 16       | Ejecutar, redirecciones, estado, matar, suspender/reasumir, errores.  |
| ctrllt    | 3        | Servicio desconocido, operación inválida, apagado completo.           |
| **Total** | **40**   |                                                                        |

Resultado actual: **40 PASARON, 0 FALLARON** (último ejecutado el
2026-05-31, todos los servicios sin errores en `stderr`).

Para ejecutarla:

```bash
bash correr_tests.sh
```

El script limpia el entorno, lanza los servicios, ejecuta los tests,
mata los servicios y devuelve el código de salida.

---

## 12. Cómo ejecutar

En WSL, dentro de la carpeta del proyecto:

```bash
# (1) arranque interactivo
bash arrancar.sh

# (2) en otra terminal: demo guiada de 9 pasos
bash demo.sh

# (3) verificación rápida
bash prueba_local.sh

# (4) batería completa de tests
bash correr_tests.sh
```

Para una petición individual:

```bash
python3 cliente.py -c /tmp/ejlotes/cli.pet -a /tmp/ejlotes/cli.resp \
    '{"servicio":"gesfich","operacion":"Crear"}'
```

Apagar el sistema:

```bash
python3 cliente.py -c /tmp/ejlotes/cli.pet -a /tmp/ejlotes/cli.resp \
    '{"servicio":"ctrllt","operacion":"Terminar"}'
```

---

## 13. Mapa del repositorio

```
ejecutorlotes23samuelsanta/
├── protocolo.py          ← capa común de comunicación
├── gesfich.py            ← servicio: ficheros
├── gesprog.py            ← servicio: programas
├── ejecutor.py           ← servicio: ejecuta programas
├── ctrllt.py             ← enrutador / pasarela
├── cliente.py            ← cliente de prueba
├── tests_completos.py    ← batería de 40 tests
├── arrancar.sh           ← lanza el sistema
├── demo.sh               ← demo de sustentación (9 pasos)
├── prueba_local.sh       ← verificación rápida
├── correr_tests.sh       ← lanza tests
├── README.md             ← guía rápida
├── docs/
│   └── Diseño.md         ← este documento
├── explicacion/          ← guía didáctica complementaria
│   ├── README.md
│   ├── como_se_hizo.md
│   ├── tuberias.md
│   ├── gesfich_y_gesprog.md
│   ├── archivos_y_carpetas.md
│   └── makefile.md
└── aralmac/              ← almacenamiento (autogenerado)
    ├── ficheros/
    └── programas/
```

---

## Apéndice A — Tabla resumen de FIFOs

| FIFO                | Sentido            | Quién escribe → quién lee |
|---------------------|--------------------|---------------------------|
| `/tmp/ejlotes/cli.pet`  | cliente → ctrllt   | `cliente`  → `ctrllt`     |
| `/tmp/ejlotes/cli.resp` | ctrllt → cliente   | `ctrllt`   → `cliente`    |
| `/tmp/ejlotes/gf.pet`   | ctrllt → gesfich   | `ctrllt`   → `gesfich`    |
| `/tmp/ejlotes/gf.resp`  | gesfich → ctrllt   | `gesfich`  → `ctrllt`     |
| `/tmp/ejlotes/gp.pet`   | ctrllt → gesprog   | `ctrllt`   → `gesprog`    |
| `/tmp/ejlotes/gp.resp`  | gesprog → ctrllt   | `gesprog`  → `ctrllt`     |
| `/tmp/ejlotes/ej.pet`   | ctrllt → ejecutor  | `ctrllt`   → `ejecutor`   |
| `/tmp/ejlotes/ej.resp`  | ejecutor → ctrllt  | `ejecutor` → `ctrllt`     |

**Total: 8 FIFOs** (2 por cada par half-duplex).

---

## Apéndice B — Glosario rápido

- **FIFO / pipe nombrado / tubería nombrada**: archivo especial POSIX
  que se comporta como una cola entre procesos.
- **Aralmac**: nombre del almacenamiento compartido del sistema. Es una
  carpeta en disco.
- **Half-duplex**: comunicación unidireccional. Cada par de procesos
  usa dos FIFOs para tener ida y vuelta.
- **SIGSTOP / SIGCONT**: señales POSIX para suspender y reanudar un
  proceso desde el exterior.
- **Popen**: API de Python para lanzar subprocesos con control sobre
  stdin/stdout/stderr y env.
