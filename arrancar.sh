#!/usr/bin/env bash
# arrancar.sh - lanza los 4 procesos del sistema (ejecutar en WSL/Linux)
#
# Las TUBERIAS van en /tmp (sistema de archivos de Linux, donde mkfifo
# funciona). El ARALMAC y el codigo pueden quedarse en la carpeta de Windows.

set -e

P=/tmp/ejlotes                 # carpeta de las tuberias nombradas
ARALMAC="$(pwd)/aralmac"       # carpeta de almacenamiento
mkdir -p "$P" "$ARALMAC"

echo "Lanzando servicios..."
python3 gesfich.py  -f "$P/gf.pet" -b "$P/gf.resp"  -x "$ARALMAC" &
python3 gesprog.py  -p "$P/gp.pet" -c "$P/gp.resp"  -x "$ARALMAC" &
python3 ejecutor.py -e "$P/ej.pet" -d "$P/ej.resp"  -x "$ARALMAC" &

# Pequena espera para que los servicios creen sus FIFO antes de ctrllt
sleep 0.5

python3 ctrllt.py \
    -c "$P/cli.pet" -a "$P/cli.resp" \
    -f "$P/gf.pet"  -b "$P/gf.resp" \
    -p "$P/gp.pet"  --pc "$P/gp.resp" \
    -e "$P/ej.pet"  -d "$P/ej.resp" &

echo "Sistema arrancado."
echo "Tuberias del cliente:  peticiones=$P/cli.pet  respuestas=$P/cli.resp"
echo "Para enviar peticiones usa cliente.py o ejecuta ./demo.sh"
echo "Procesos en segundo plano: $(jobs -p | tr '\n' ' ')"
wait
