#!/bin/bash
set -e

# Detectar la raíz real del proyecto (si el script está en /setup, sube a la carpeta raíz)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SCRIPT_DIR" == */setup ]]; then
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
else
    PROJECT_DIR="$SCRIPT_DIR"
fi

CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo "~$CURRENT_USER")

echo "📂 [CONFIG] Raíz del proyecto detectada en: $PROJECT_DIR"
echo "👤 [CONFIG] Usuario detectado: $CURRENT_USER"

# 1. Actualizar el sistema e instalar dependencias nativas de Linux
echo "📦 [1/7] Actualizando repositorios e instalando paquetes del sistema..."
sudo apt-get update

sudo apt-get install -y python3-pip python3-venv python3-dev \
                        build-essential libzbar0 supervisor \
                        xserver-xorg xinit x11-xserver-utils unclutter chromium lightdm \
                        libgl1 libglib2.0-0 libcap-dev python3-libcamera libcamera-apps \
                        i2c-tools python3-smbus

# Habilitar I2C en el firmware de arranque
echo "🔌 Habilitando bus I2C en el sistema operativo..."
CONFIG_FILE="/boot/firmware/config.txt"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"

if ! grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE" 2>/dev/null; then
    echo "dtparam=i2c_arm=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "✅ Parámetro dtparam=i2c_arm=on agregado a $CONFIG_FILE"
fi

# Instalación global de picamera2
echo "📸 Instalando picamera2 de forma global en el sistema operativo..."
sudo apt-get install -y python3-picamera2 || sudo pip3 install picamera2 --break-system-packages

# 2. Configurar el Entorno Virtual (venv) en la RAÍZ del proyecto
echo "🐍 [2/7] Configurando entorno virtual integrado en $PROJECT_DIR/.venv..."
cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
else
    echo "⚙️ El entorno .venv ya existe. Asegurando acceso a paquetes globales..."
    sed -i 's/include-system-site-packages = false/include-system-site-packages = true/g' .venv/pyvenv.cfg
fi

source .venv/bin/activate

echo "📥 Instalando librerías de Python dentro del entorno aislado..."
pip install --upgrade pip
pip install fastapi uvicorn[standard] opencv-python-headless pyzbar smbus2 requests httpx

deactivate
echo "✅ Entorno virtual de Python preparado con éxito."

# Limpiar venv accidental en /setup si existía
if [ -d "$SCRIPT_DIR/.venv" ] && [ "$SCRIPT_DIR" != "$PROJECT_DIR" ]; then
    echo "🧹 Eliminando .venv redundante en la subcarpeta setup..."
    rm -rf "$SCRIPT_DIR/.venv"
fi

# 3. Crear el script definitivo de Kiosco (kiosco.sh)
echo "🌐 [3/7] Generando script de arranque para Chromium en modo Kiosco..."
cat << 'EOF' > "$PROJECT_DIR/kiosco.sh"
#!/bin/bash
xset s off 2>/dev/null
xset s noblank 2>/dev/null
xset -dpms 2>/dev/null

echo "🌐 Lanzando Chromium en modo Kiosco..."
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
if [ -f "$PROJECT_DIR/hardware_orchestrator.py" ]; then
    chmod +x "$PROJECT_DIR/hardware_orchestrator.py"
fi

# 4. Configurar Autologin en consola pura
echo "🖥️ [4/7] Configurando Autologin en consola pura..."
sudo systemctl set-default multi-user.target
sudo systemctl disable lightdm 2>/dev/null || true

sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $CURRENT_USER --noclear %I \$TERM
EOF

sudo systemctl daemon-reload

# 5. Permisos de Hardware, Gráficos e I2C
echo "🔑 [5/7] Asignando permisos de GPU, renderizado e I2C al usuario $CURRENT_USER..."
sudo usermod -a -G video,render,input,i2c "$CURRENT_USER"
sudo chmod +s /usr/bin/Xorg

sudo tee /etc/X11/Xwrapper.config > /dev/null << 'EOF'
allowed_users=anybody
EOF

# 6. Configurar Supervisor apuntando SIEMPRE a la raíz del proyecto
echo "🤖 [6/7] Configurando Supervisor con rutas absolutas a $PROJECT_DIR..."
sudo tee /etc/supervisor/conf.d/lector_qr.conf > /dev/null << EOF
[program:web_server]
command=$PROJECT_DIR/.venv/bin/uvicorn server_orchestrator:app --host 0.0.0.0 --port 8000
directory=$PROJECT_DIR
user=$CURRENT_USER
environment=PYTHONPATH="$PROJECT_DIR",PATH="$PROJECT_DIR/.venv/bin:%(ENV_PATH)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/web_server.err.log
stdout_logfile=/var/log/web_server.out.log

[program:hardware_orchestrator]
command=$PROJECT_DIR/.venv/bin/python3 hardware_orchestrator.py
directory=$PROJECT_DIR
user=root
autostart=true
autorestart=true
stderr_logfile=/var/log/hardware_orchestrator.err.log
stdout_logfile=/var/log/hardware_orchestrator.out.log
EOF

sudo supervisorctl reread
sudo supervisorctl update

# 7. Inyectar disparador gráfico de Kiosco en .bashrc
echo "🚀 [7/7] Inyectando disparador startx en el archivo .bashrc..."
if ! grep -q "startx $PROJECT_DIR/kiosco.sh" "$USER_HOME/.bashrc"; then
    cat << EOF >> "$USER_HOME/.bashrc"

# Lanzar el modo kiosco dinámico directo desde la terminal física 1 (HDMI)
if [ -z "\$DISPLAY" ] && [ "\$(tty)" = "/dev/tty1" ]; then
    echo "🚀 Levantando entorno gráfico optimizado para el Kiosco..."
    sleep 2
    startx $PROJECT_DIR/kiosco.sh -- -nocursor
    read -r
fi
EOF
fi

echo "================================================================="
echo " 🎉 ¡INSTALACIÓN Y CONFIGURACIÓN COMPLETADA! "
echo "================================================================="
