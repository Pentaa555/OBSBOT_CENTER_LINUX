#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Log para diagnóstico cuando se lanza desde el ícono (sin consola).
LOG="$DIR/obsbot-control.log"
exec > >(tee -a "$LOG") 2>&1
echo "===== $(date) : iniciando OBSBOT Control ====="

source .venv/bin/activate
export PYTHONPATH="$PYTHONPATH:$DIR/bridge/build"

# Compilar el bridge automáticamente si aún no existe.
if ! ls bridge/build/obsbot_bridge*.so >/dev/null 2>&1; then
    echo "Bridge no compilado; compilando..."
    cmake -S bridge -B bridge/build -Dpybind11_DIR="$(python3 -m pybind11 --cmakedir)"
    cmake --build bridge/build -j"$(nproc)"
fi

exec python3 -m app.main "$@"
