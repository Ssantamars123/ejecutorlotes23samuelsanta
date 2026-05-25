#!/usr/bin/env bash
# demo.sh - recorre el flujo completo del sistema para la SUSTENTACION.
# Requiere que ./arrancar.sh este corriendo en otra terminal.

P=/tmp/ejlotes
enviar() {
    echo ""
    echo ">>> PETICION: $1"
    python3 cliente.py -c "$P/cli.pet" -a "$P/cli.resp" "$1"
}

echo "================ DEMO Ejecutor de Lotes ================"

echo ""
echo "--- 1) gesprog: guardar un programa (el comando 'cat') ---"
enviar '{"servicio":"gesprog","operacion":"Guardar","ejecutable":"/bin/cat"}'

echo ""
echo "--- 2) gesprog: listar programas ---"
enviar '{"servicio":"gesprog","operacion":"Leer"}'

echo ""
echo "--- 3) gesfich: crear fichero de ENTRADA (f-0001) ---"
enviar '{"servicio":"gesfich","operacion":"Crear"}'

echo ""
echo "--- 4) gesfich: crear fichero de SALIDA (f-0002) ---"
enviar '{"servicio":"gesfich","operacion":"Crear"}'

echo ""
echo "    (rellenamos f-0001 con texto de prueba)"
echo "Hola mundo desde ejecutor de lotes" > "$(pwd)/aralmac/ficheros/f-0001"

echo ""
echo "--- 5) ejecutor: ejecutar p-0001 leyendo f-0001 y escribiendo f-0002 ---"
enviar '{"servicio":"ejecutor","operacion":"Ejecutar","id-programa":"p-0001","stdin":"f-0001","stdout":"f-0002"}'

sleep 0.5
echo ""
echo "--- 6) ejecutor: consultar estado de e-0001 ---"
enviar '{"servicio":"ejecutor","operacion":"Estado","id-ejecucion":"e-0001"}'

echo ""
echo "--- 7) gesfich: leer la SALIDA producida (f-0002) ---"
enviar '{"servicio":"gesfich","operacion":"Leer","id-fichero":"f-0002"}'

echo ""
echo "--- 8) prueba de error: servicio inexistente ---"
enviar '{"servicio":"noexiste","operacion":"Algo"}'

echo ""
echo "--- 9) ctrllt: terminar todo el sistema ---"
enviar '{"servicio":"ctrllt","operacion":"Terminar"}'

echo ""
echo "================ FIN DE LA DEMO ================"
