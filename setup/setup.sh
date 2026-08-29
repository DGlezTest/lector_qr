#!/bin/bash
set -e

# 1. Detectar rutas y usuario
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SCRIPT_DIR" == */setup ]]; then
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
else
    PROJECT_DIR="$SCRIPT_DIR"
fi

CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo "~$CURRENT_USER")

echo "================================================================="
echo "🚀 INSTALACIÓN INTEGRAL AUTOMATIZADA (EDGE QR ACCESS CONTROL)"
echo "📂 Raíz del proyecto: $PROJECT_DIR"
echo "👤 Usuario destino:   $CURRENT_USER ($USER_HOME)"
echo "================================================================="

# 2. Actualizar sistema e instalar librerías nativas
echo "📦 [1/7] Actualizando repositorios e instalando paquetes del sistema..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-dev \
                        build-essential libzbar0 supervisor sqlite3 \
                        xserver-xorg xinit x11-xserver-utils unclutter chromium lightdm \
                        libgl1 libglib2.0-0 libcap-dev python3-libcamera libcamera-apps \
                        i2c-tools python3-smbus xdotool sed

# 3. Habilitar I2C en Kernel, Módulos y Firmware
echo "🔌 [2/7] Habilitando y forzando carga de módulos I2C..."
sudo raspi-config nonint do_i2c 0 2>/dev/null || true
sudo modprobe i2c-dev 2>/dev/null || true

if ! grep -q "^i2c-dev" /etc/modules 2>/dev/null; then
    echo "i2c-dev" | sudo tee -a /etc/modules > /dev/null
fi

CONFIG_FILE="/boot/firmware/config.txt"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"

if ! grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE" 2>/dev/null; then
    echo "dtparam=i2c_arm=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "✅ Parámetro dtparam=i2c_arm=on agregado a $CONFIG_FILE"
fi

# 4. Auto-detección en vivo de la dirección del HAT I2C
echo "🔍 [3/7] Escaneando bus I2C para auto-configuración..."
DETECTED_ADDR=$(i2cdetect -y 1 2>/dev/null | grep -E "^(00|10|20|30|40|50|60|70):" | grep -oE "\b[0-9a-f]{2}\b" | head -n 1 || true)

if [ -n "$DETECTED_ADDR" ]; then
    I2C_HEX="0x$DETECTED_ADDR"
    echo "🎯 HAT I2C detectado con éxito en: $I2C_HEX"
else
    I2C_HEX="0x13"
    echo "⚠️ No se detectó dirección en vivo (puede requerir reinicio). Usando: $I2C_HEX"
fi

mkdir -p "$PROJECT_DIR/setup"
CONFIG_PATH="$PROJECT_DIR/setup/config.json"

cat << EOF > "$CONFIG_PATH"
{
  "camera": {
    "type": "webcam",
    "device_index": 0,
    "width": 640,
    "height": 480
  },
  "i2c": {
    "bus": 1,
    "device_address": "$I2C_HEX"
  },
  "rele_canales": {
    "rele_abrir_motor": 1,
    "rele_cerrar_motor": 2
  },
  "tiempos": {
    "tiempo_apertura_motor": 2.5,
    "tiempo_espera_peaton": 5.0,
    "tiempo_cierre_motor": 2.5
  }
}
EOF
sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$PROJECT_DIR/setup"

# 5. Configurar el Entorno Virtual (venv) en la raíz
echo "🐍 [4/7] Configurando entorno virtual integrado en $PROJECT_DIR/.venv..."
cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
else
    sed -i 's/include-system-site-packages = false/include-system-site-packages = true/g' .venv/pyvenv.cfg
fi

source .venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn[standard] opencv-python-headless pyzbar smbus2 requests httpx pydantic qrcode[pil]
deactivate

# 6. Permisos de Hardware, Autologin y Kiosco
echo "🔑 [5/7] Configurando permisos, Autologin y Kiosco..."
sudo usermod -a -G video,render,input,i2c "$CURRENT_USER"
sudo chmod +s /usr/bin/Xorg 2>/dev/null || true

sudo tee /etc/X11/Xwrapper.config > /dev/null << 'EOF'
allowed_users=anybody
EOF

cat << 'EOF' > "$PROJECT_DIR/kiosco.sh"
#!/bin/bash
xset s off 2>/dev/null
xset s noblank 2>/dev/null
xset -dpms 2>/dev/null

exec chromium --window-size=1920,1080 \
              --window-position=0,0 \
              --kiosk \
              --noerrdialogs \
              --disable-infobars \
              --check-for-update-interval=31536000 \
              --disable-pinch \
              http://localhost:8000
EOF

chmod +x "$PROJECT_DIR/kiosco.sh"
[ -f "$PROJECT_DIR/hardware_orchestrator.py" ] && chmod +x "$PROJECT_DIR/hardware_orchestrator.py"

# Autologin en TTY1
sudo systemctl set-default multi-user.target
sudo systemctl disable lightdm 2>/dev/null || true

sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $CURRENT_USER --noclear %I \$TERM
EOF

sudo systemctl daemon-reload

# 7. Configuración de Supervisor
echo "🤖 [6/7] Registrando demonios en Supervisor..."
sudo tee /etc/supervisor/conf.d/lector_qr.conf > /dev/null << EOF
[program:web_server]
command=$PROJECT_DIR/.venv/bin/uvicorn server_orchestrator:app --host 0.0.0.0 --port 8000
directory=$PROJECT_DIR
user=$CURRENT_USER
environment=PYTHONUNBUFFERED="1",PYTHONPATH="$PROJECT_DIR",PATH="$PROJECT_DIR/.venv/bin:%(ENV_PATH)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/web_server.err.log
stdout_logfile=/var/log/web_server.out.log

[program:hardware_orchestrator]
command=$PROJECT_DIR/.venv/bin/python3 hardware_orchestrator.py
directory=$PROJECT_DIR
user=root
environment=PYTHONUNBUFFERED="1",PYTHONPATH="$PROJECT_DIR"
autostart=true
autorestart=true
stderr_logfile=/var/log/hardware_orchestrator.err.log
stdout_logfile=/var/log/hardware_orchestrator.out.log
EOF

sudo supervisorctl reread
sudo supervisorctl update

# Inyectar startx en .bashrc
echo "🚀 [7/7] Inyectando arranque gráfico en .bashrc..."
if ! grep -q "startx $PROJECT_DIR/kiosco.sh" "$USER_HOME/.bashrc"; then
    cat << EOF >> "$USER_HOME/.bashrc"

if [ -z "\$DISPLAY" ] && [ "\$(tty)" = "/dev/tty1" ]; then
    echo "🚀 Levantando entorno gráfico del Kiosco..."
    sleep 2
    startx $PROJECT_DIR/kiosco.sh -- -nocursor
    read -r
fi
EOF
fi

echo "================================================================="
echo " 🎉 ¡DESPLIEGUE FINALIZADO CON ÉXITO!"
echo " 💡 Ejecuta 'sudo reboot' para iniciar en modo autónomo."
echo "================================================================="
