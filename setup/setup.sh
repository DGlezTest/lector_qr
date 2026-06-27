#!/bin/bash

# Terminar inmediatamente si algún comando falla
set -e

PROJECT_DIR="/home/pi/lector_qr"
USER_HOME="/home/pi"
CURRENT_USER="pi"

echo "================================================================="
echo "   INICIANDO INSTALACIÓN MAESTRA: LECTOR QR & KIOSCO INDUSTRIAL  "
echo "================================================================="

# 1. Actualizar el sistema e instalar dependencias nativas de Linux
echo "📦 [1/7] Actualizando repositorios e instalando paquetes del sistema..."
sudo apt-get update

# Se añade 'libcap-dev' para compilación de python-prctl.
# Se añade 'libcamera-apps' para asegurar binarios de la cámara M2.
sudo apt-get install -y python3-pip python3-venv python3-dev \
                        build-essential libzbar0 supervisor \
                        xserver-xorg xinit x11-xserver-utils unclutter chromium lightdm \
                        libgl1 libglib2.0-0 libcap-dev python3-libcamera libcamera-apps

# 2. Crear y configurar el Entorno Virtual (venv) heredando paquetes del sistema
echo "🐍 [2/7] Configurando entorno virtual con acceso al sistema operativo (.venv)..."
cd "$PROJECT_DIR"

# IMPORTANTE: Se añade --system-site-packages para que el .venv pueda morder libcamera
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
else
    echo "⚙️ El entorno .venv ya existe. Asegurando herencia de paquetes del sistema..."
    sed -i 's/include-system-site-packages = false/include-system-site-packages = true/g' .venv/pyvenv.cfg
fi

# Activar venv de forma segura para instalar pip packs
source .venv/bin/activate

echo "📥 Instalando librerías de Python dentro del entorno..."
pip install --upgrade pip
pip install fastapi uvicorn[standard] opencv-python-headless pyzbar RPi.GPIO requests

# Instalación de picamera2 localmente dentro del entorno virtual
echo "📸 Instalando picamera2 para soporte de cámara nativa M2..."
pip install picamera2

deactivate
echo "✅ Entorno virtual de Python preparado con éxito."

# 3. Crear el script definitivo de Kiosco (kiosco.sh)
echo "🌐 [3/7] Generando script de arranque para Chromium en modo Kiosco..."
cat << 'EOF' > "$PROJECT_DIR/kiosco.sh"
#!/bin/bash

# Desactivar protectores de pantalla e hibernación de hardware X11
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

# Dar permisos de ejecución a los scripts
chmod +x "$PROJECT_DIR/kiosco.sh"
if [ -f "$PROJECT_DIR/hardware_orchestrator.py" ]; then
    chmod +x "$PROJECT_DIR/hardware_orchestrator.py"
fi

# 4. Configurar el inicio automático en Consola con Login Automático (Bypass de contraseña)
echo "🖥️ [4/7] Configurando Autologin en consola pura (Evitando escritorio pesado)..."
sudo systemctl set-default multi-user.target
sudo systemctl disable lightdm

# Sobrescribir el getty de la terminal física 1 para inyectar al usuario pi de inmediato
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
EOF

sudo systemctl daemon-reload

# 5. Permisos de Hardware Gráfico para el usuario 'pi' (Solución al loop de render)
echo "🔑 [5/7] Asignando permisos de GPU, renderizado y envoltura X11..."
sudo usermod -a -G video,render,input "$CURRENT_USER"
sudo chmod +s /usr/bin/Xorg

# Permitir que startx sea invocado por cualquiera desde la consola tty
sudo tee /etc/X11/Xwrapper.config > /dev/null << 'EOF'
allowed_users=anybody
EOF

# 6. Configurar Supervisor para Orquestador de Hardware y Servidor FastAPI Corregido
echo "🤖 [6/7] Configurando Supervisor para procesos en segundo plano..."
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
# Ejecutamos con la ruta absoluta del Python aislado de root para asegurar los bindings de hardware
command=$PROJECT_DIR/.venv/bin/python3 hardware_orchestrator.py
directory=$PROJECT_DIR
user=root
autostart=true
autorestart=true
stderr_logfile=/var/log/hardware_orchestrator.err.log
stdout_logfile=/var/log/hardware_orchestrator.out.log
EOF

# Forzar a Supervisor a leer la nueva configuración y levantar hilos
sudo supervisorctl reread
sudo supervisorctl update

# 7. Inyectar disparador gráfico de Kiosco Minimalista en .bashrc
echo "🚀 [7/7] Inyectando disparador startx en el archivo .bashrc..."
if ! grep -q "startx $PROJECT_DIR/kiosco.sh" "$USER_HOME/.bashrc"; then
    cat << EOF >> "$USER_HOME/.bashrc"

# Lanzar el modo kiosco dinámico directo desde la terminal física 1 (HDMI)
if [ -z "\$DISPLAY" ] && [ "\$(tty)" = "/dev/tty1" ]; then
    echo "🚀 Levantando entorno gráfico optimizado para el Kiosco..."
    sleep 2
    startx $PROJECT_DIR/kiosco.sh -- -nocursor
    
    echo "⚠️ El entorno gráfico se detuvo. Presiona Ctrl+C para interactuar."
    read -r
fi
EOF
fi

echo "================================================================="
echo " 🎉 ¡INSTALACIÓN COMPLETADA EXITOSAMENTE! "
echo "================================================================="
echo " Todo ha sido configurado bajo los estándares correctos para Debian Trixie."
echo " Por favor, ejecuta el siguiente comando para reiniciar tu Raspberry Pi:"
echo " -> sudo reboot"
echo "================================================================="