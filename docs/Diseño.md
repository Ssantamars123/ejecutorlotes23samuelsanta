# Diseño — Ejecutor de Lotes

Implementación en **Python 3** de un sistema que simula el ejecutor de lotes
de un mainframe. Los procesos se comunican mediante **tuberías nombradas**
(named pipes) intercambiando **mensajes JSON** terminados en salto de línea.

- **Sistema operativo objetivo:** Linux (se ejecuta en WSL sobre Windows).
- **Lenguaje:** Python 3 (solo biblioteca estándar: `os`, `json`, `subprocess`, `signal`, `argparse`).

---

## 1. Arquitectura general

```
  cliente  ──►  ctrllt  ──►  gesfich ─┐
                   │     ──►  gesprog ─┼──►  aralmac  (carpeta en disco)
                   │     ──►  ejecutor ┘
                   └── (respuesta) ──► cliente
```

- **cliente**: envía peticiones y muestra respuestas. Se conecta **solo** a `ctrllt`.
- **ctrllt** (Control de Lotes): enrutador/pasarela. Recibe del cliente, reenvía
  al servicio del campo `servicio`, espera la respuesta y la devuelve sin modificarla.
- **gesfich**: gestor de ficheros (CRUD sobre `aralmac/ficheros/`).
- **gesprog**: gestor de programas (metadatos en `aralmac/programas/`).
- **ejecutor**: lanza programas como procesos reales y administra su ciclo de vida.
- **aralmac**: no es un proceso, es una **carpeta compartida** en disco.

Los tres servicios internos **nunca se comunican entre sí**: solo hablan con
`ctrllt`. Comparten datos únicamente a través del `aralmac` (por ejemplo, el
`ejecutor` lee del disco los metadatos que guardó `gesprog`).

---

## 2. Comunicación

### 2.1 Tuberías nombradas (half-duplex)

Una FIFO de Linux es **unidireccional**, así que cada conexión usa **dos**
tuberías: una para peticiones y otra para respuestas (modelo *half-duplex*
descrito en la práctica con las opciones `-a -b -c -d`).

La sincronización es automática y no requiere hilos ni locks: abrir una FIFO
**bloquea** hasta que el otro extremo también la abre. Por eso el patrón
*abrir → leer/escribir → cerrar* en cada mensaje ordena los procesos solo.

Toda esta lógica está en `protocolo.py` (funciones `crear_fifo`, `enviar`,
`recibir`). Los cuatro componentes la reutilizan.

### 2.2 Formato de mensajes

- **Petición:** `{"servicio":"<svc>","operacion":"<op>", ...}`
- **Respuesta de éxito:** `{"estado":"ok", ...}`
- **Respuesta de error:** `{"estado":"error","mensaje":"<descripcion>"}`
- Cada mensaje es una línea JSON terminada en `\n`, con máximo **4096 bytes**.

### 2.3 Identificadores

| Tipo      | Formato | Ejemplo |
|-----------|---------|---------|
| Fichero   | `f-XXXX`| `f-0001`|
| Programa  | `p-XXXX`| `p-0001`|
| Ejecución | `e-XXXX`| `e-0001`|

---

## 3. Patrón común de los servicios

Los cuatro componentes comparten el mismo esqueleto. Solo cambia *qué hace*
cada operación:

```python
while estado != "Terminado":
    pet  = recibir(fifo_peticiones)   # 1. leer peticion (bloquea)
    resp = procesar(pet)              # 2. ejecutar la operacion
    enviar(fifo_respuestas, resp)     # 3. responder
```

---

## 4. Componentes en detalle

### 4.1 gesfich — `aralmac/ficheros/`
Operaciones: `Crear`, `Leer` (por id o listar todos), `Actualizar`, `Borrar`,
`Suspender`, `Reasumir`, `Terminar`. Los ids se generan con un contador
persistido en disco para garantizar unicidad.

### 4.2 gesprog — `aralmac/programas/`
Guarda un JSON por programa con `{id-programa, nombre, ejecutable, args, env}`.
Operaciones: `Guardar`, `Leer`, `Actualizar`, `Borrar`, `Suspender`,
`Reasumir`, `Terminar`. El campo `ejecutable` (ruta completa) lo consume
después el `ejecutor` leyéndolo directamente del `aralmac`.

### 4.3 ejecutor
Operaciones: `Ejecutar`, `Estado` (por id o todos), `Matar`, `Suspender`,
`Reasumir`, `Parar`.
- `Ejecutar` lee los metadatos del programa, resuelve `stdin/stdout/stderr`
  (que son ids de fichero) a rutas reales del `aralmac` y lanza el proceso con
  `subprocess.Popen`.
- `Estado` consulta con `proc.poll()`: `Ejecutando`, `Suspendido` o
  `Terminado` (con `codigo-salida`).
- `Suspender`/`Reasumir` envían `SIGSTOP`/`SIGCONT` a los procesos hijos.
- `Parar` deja de aceptar nuevas ejecuciones y espera a que terminen las activas.

### 4.4 ctrllt
Enruta según el campo `servicio` usando una tabla
`servicio → (fifo_peticion, fifo_respuesta)`. Su única operación propia es
`Terminar`: propaga `Terminar` a `gesfich` y `gesprog`, envía `Parar` al
`ejecutor` y finaliza. Devuelve errores propios como `servicio desconocido`.

---

## 5. Máquinas de estado

- **gesfich / gesprog**: `Corriendo ⇄ Suspendido → Terminado`. En `Suspendido`
  las operaciones de datos devuelven `{"estado":"error","mensaje":"servicio suspendido"}`;
  las transiciones siempre se permiten.
- **ejecutor**: `Corriendo ⇄ Suspendido`, y `Parar → Terminado` cuando ya no
  quedan procesos activos.

---

## 6. Decisiones de diseño

1. **Una sola capa de comunicación** (`protocolo.py`) reutilizada por todos:
   menos código y más fácil de explicar.
2. **Tuberías en `/tmp`** (sistema de archivos de Linux, donde `mkfifo`
   funciona) y **código + aralmac en la carpeta del proyecto**. En WSL no se
   pueden crear FIFOs sobre el disco de Windows montado (`/mnt/c`), pero los
   archivos normales sí.
3. **Atención secuencial**: `ctrllt` procesa una petición a la vez. Es simple,
   correcto y suficiente para la práctica.
4. **El PDF reutiliza la opción `-c`** (controlador y respuesta de `gesprog`).
   Para evitar el choque, la respuesta de `gesprog` en `ctrllt` usa `--pc`.

---

## 7. Cómo ejecutar

En una terminal WSL, dentro de la carpeta del proyecto:

```bash
bash arrancar.sh      # lanza gesfich, gesprog, ejecutor y ctrllt
```

En otra terminal:

```bash
bash demo.sh          # recorre el flujo completo de ejemplo
```

O una verificación todo-en-uno:

```bash
bash prueba_local.sh
```

Para enviar una petición individual:

```bash
python3 cliente.py -c /tmp/ejlotes/cli.pet -a /tmp/ejlotes/cli.resp \
    '{"servicio":"gesfich","operacion":"Crear"}'
```
