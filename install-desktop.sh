#!/usr/bin/env bash
# Instala OBSBOT Control en el menú de aplicaciones del escritorio.
# Tras ejecutarlo una vez, podrás abrir la app desde tu lanzador (sin consola).
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APP_DIR/obsbot-control.desktop"

mkdir -p "$APP_DIR"

chmod +x "$DIR/run.sh"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=OBSBOT Control
Comment=Control de cámara OBSBOT Tiny para Linux
Exec=$DIR/run.sh
Icon=$DIR/obsbot_logo.png
Terminal=false
Categories=AudioVideo;Video;
StartupNotify=true
Path=$DIR
EOF

chmod +x "$DESKTOP_FILE"

# Marcar como confiable y refrescar la base de datos del menú.
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
fi

echo "Instalado: $DESKTOP_FILE"
echo "Busca 'OBSBOT Control' en tu menú de aplicaciones."
