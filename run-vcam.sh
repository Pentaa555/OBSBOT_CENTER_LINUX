#!/usr/bin/env bash
# Arranca solo el pipeline de la cámara virtual (sin interfaz gráfica).
# Lo usa la entrada de autostart cuando activas "Iniciar cámara virtual al
# encender el equipo".
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

LOG="$DIR/obsbot-vcam.log"
exec > >(tee -a "$LOG") 2>&1
echo "===== $(date) : iniciando cámara virtual OBSBOT ====="

source .venv/bin/activate
export PYTHONPATH="$PYTHONPATH:$DIR/bridge/build"

exec python3 -m app.virtualcam_service "$@"
