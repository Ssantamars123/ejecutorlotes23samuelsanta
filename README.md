# Ejecutor de Lotes

Simulación en Python de un sistema de ejecución de procesos por lotes tipo
mainframe. Los procesos se comunican por **tuberías nombradas** con mensajes
**JSON**. Diseñado para ejecutarse en **Linux / WSL**.

## Componentes

| Archivo        | Rol                                                        |
|----------------|------------------------------------------------------------|
| `protocolo.py` | Capa compartida de comunicación (FIFOs + JSON).            |
| `gesfich.py`   | Gestor de ficheros (CRUD).                                 |
| `gesprog.py`   | Gestor de programas (metadatos).                           |
| `ejecutor.py`  | Lanza y administra procesos por lotes.                     |
| `ctrllt.py`    | Controlador / enrutador. Único punto de contacto del cliente. |
| `cliente.py`   | Cliente de prueba.                                         |

## Uso rápido (en WSL)

```bash
bash arrancar.sh        # terminal 1: arranca los servicios
bash demo.sh            # terminal 2: demo del flujo completo
# o todo de una vez:
bash prueba_local.sh
```

## Documentación

El diseño detallado está en [`docs/Diseño.md`](docs/Dise%C3%B1o.md).
