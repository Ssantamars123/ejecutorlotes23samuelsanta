#!/usr/bin/env bash
# Runner de verificacion: arranca los 4 servicios, ejecuta el flujo completo
# y limpia. Se ejecuta con:  wsl bash prueba_local.sh
set -u
cd "$(dirname "$0")"

P=/tmp/ejlotes
rm -rf "$P" ./aralmac
mkdir -p "$P" ./aralmac

python3 gesfich.py  -f "$P/gf.pet" -b "$P/gf.resp"  -x ./aralmac 2>"$P/gf.err" & PID1=$!
python3 gesprog.py  -p "$P/gp.pet" -c "$P/gp.resp"  -x ./aralmac 2>"$P/gp.err" & PID2=$!
python3 ejecutor.py -e "$P/ej.pet" -d "$P/ej.resp"  -x ./aralmac 2>"$P/ej.err" & PID3=$!
sleep 1
python3 ctrllt.py -c "$P/cli.pet" -a "$P/cli.resp" \
    -f "$P/gf.pet" -b "$P/gf.resp" \
    -p "$P/gp.pet" --pc "$P/gp.resp" \
    -e "$P/ej.pet" -d "$P/ej.resp" 2>"$P/ct.err" & PID4=$!
sleep 1

echo "=== errores de arranque (vacio = todo OK) ==="
cat "$P"/*.err 2>/dev/null

cli() { python3 cliente.py -c "$P/cli.pet" -a "$P/cli.resp" "$1"; }

echo; echo "1) gesprog Guardar /bin/cat"
cli '{"servicio":"gesprog","operacion":"Guardar","ejecutable":"/bin/cat"}'
echo "2) gesprog Leer (listar)"
cli '{"servicio":"gesprog","operacion":"Leer"}'
echo "3) gesfich Crear (entrada f-0001)"
cli '{"servicio":"gesfich","operacion":"Crear"}'
echo "4) gesfich Crear (salida f-0002)"
cli '{"servicio":"gesfich","operacion":"Crear"}'

echo "Hola mundo desde ejecutor de lotes" > ./aralmac/ficheros/f-0001

echo "5) ejecutor Ejecutar p-0001 (cat f-0001 -> f-0002)"
cli '{"servicio":"ejecutor","operacion":"Ejecutar","id-programa":"p-0001","stdin":"f-0001","stdout":"f-0002"}'
sleep 0.5
echo "6) ejecutor Estado e-0001"
cli '{"servicio":"ejecutor","operacion":"Estado","id-ejecucion":"e-0001"}'
echo "7) gesfich Leer f-0002 (salida producida)"
cli '{"servicio":"gesfich","operacion":"Leer","id-fichero":"f-0002"}'
echo "8) error: servicio inexistente"
cli '{"servicio":"noexiste","operacion":"Algo"}'
echo "9) gesfich Suspender + intentar Crear (debe dar error)"
cli '{"servicio":"gesfich","operacion":"Suspender"}'
cli '{"servicio":"gesfich","operacion":"Crear"}'
cli '{"servicio":"gesfich","operacion":"Reasumir"}'
echo "10) ctrllt Terminar (apaga todo)"
cli '{"servicio":"ctrllt","operacion":"Terminar"}'

kill $PID1 $PID2 $PID3 $PID4 2>/dev/null
echo "=== FIN ==="
