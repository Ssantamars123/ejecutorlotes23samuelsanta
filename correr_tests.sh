#!/usr/bin/env bash
# Arranca el sistema, corre la bateria de tests automaticos y limpia.
# Uso:  wsl bash correr_tests.sh
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

python3 tests_completos.py "$P" "$(pwd)/aralmac"
RC=$?

kill $PID1 $PID2 $PID3 $PID4 2>/dev/null
echo "--- errores de servicios (vacio = ninguno) ---"
cat "$P"/*.err 2>/dev/null
exit $RC
