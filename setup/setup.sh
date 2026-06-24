#!/bin/bash

# 1. Asegurar que el script se ejecute como ROOT
if [ "$EUID" -ne 0 ]; then
  echo "❌ Por favor, ejecuta este script usando sudo: sudo ./setup.sh"
  exit 1
fi

echo "====================================================="
echo "⚙️  CONFIGURACIÓN AUTOMÁTICA COMPLETA PARA TRIXIE ⚙️"
echo "====================================================="

# Obtener rutas absolutas dinámicas
SETUP_DIR=$(dirname "$(readlink -f "$0")")
PROYECTO_DIR=$(dirname "$SETUP_DIR")

# 2. Actualizar e instalar dependencias del sistema operativo (Corregido para Trixie)
echo "📦 1/6 Instalando dependencias base del sistema..."
apt-get update -y

echo "📥 Instalando Supervisor, SWIG y Python venv..."
apt-get install -y supervisor python3-pip python3-dev python3-venv swig -y

echo "📥 Instalando entorno de ventanas y herramientas gráficas..."
apt-get install -y xserver-xorg xinit x11-xserver-utils unclutter chromium-browser -y

echo "📥 Instalando decodificador de QR nativo..."
apt-get install -y libzbar0t64 || apt-get install -y libzbar0

# 3. Mover el config.json a la raíz si no existe
echo "-----------------------------------------------------"
echo "⚙️  2/6 Desplegando archivo de configuración config.json..."
if [ ! -f "$PROYECTO_DIR/config.json" ]; then
    if [ -f "$SETUP_DIR/config.json" ]; then
        cp "$SETUP_DIR/config.json" "$PROYECTO_DIR/config.json"
        echo "📄 Plantilla config.json copiada a la raíz con éxito."
    else
        echo "❌ Error crítico: No se encontró config.json en $SETUP_DIR"
        exit 1
    fi
else
    echo "ℹ️  Ya existe un archivo config.json en la raíz. No se sobrescribió."
fi

# 4. CREACIÓN DEL VENV E INSTALACIÓN DE DEPENDENCIAS (Con soporte SWIG para lgpio)
echo "-----------------------------------------------------"
echo "🐍 3/6 Creando Entorno Virtual (venv) en la raíz del proyecto..."

if [ ! -d "$PROYECTO_DIR/.venv" ]; then
    python3 -m venv "$PROYECTO_DIR/.venv"
    echo "✅ Entorno virtual creado con éxito."
fi

echo "📥 Instalando librerías desde requirements.txt dentro del venv..."
"$PROYECTO_DIR/.venv/bin/pip" install --upgrade pip
"$PROYECTO_DIR/.venv/bin/pip" install -r "$SETUP_DIR/requirements.txt"

# 5. CONFIGURACIÓN DEL MODO KIOSCO
echo "-----------------------------------------------------"
echo "🖥️  4/6 Configurando arranque en Modo Kiosco..."
if [ -f "$SETUP_DIR/kiosco.sh.template" ]; then
    cp "$SETUP_DIR/kiosco.sh.template" "$PROYECTO_DIR/kiosco.sh"
    chmod +x "$PROYECTO_DIR/kiosco.sh"
else
    # Si no existiera el template por alguna razón, lo creamos de seguridad
    cat <<EOT > "$PROYECTO_DIR/kiosco.sh"
#!/bin/bash
xset s off
xset s noblank
xset -dpms
unclutter -idle 0.5 -root &
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8000
EOT
    chmod +x "$PROYECTO_DIR/kiosco.sh"
fi

cat <<EOT > /root/.xinitrc
exec $PROYECTO_DIR/kiosco.sh
EOT

if ! grep -q "startx" /root/.bashrc; then
    cat <<EOT >> /root/.bashrc

# Lanzar el modo kiosco automáticamente al iniciar sesión en la terminal física 1
if [ -z "\$DISPLAY" ] && [ "\$(tty)" = "/dev/tty1" ]; then
    startx
fi
EOT
fi

# 6. REGISTRO EN SUPERVISOR APUNTANDO AL VENV
echo "-----------------------------------------------------"
echo "📋 5/6 Registrando rutas en la configuración de Supervisor..."

mkdir -p /etc/supervisor/conf.d/

cat <<EOT > /etc/supervisor/conf.d/mi_escaner.conf
[program:server_orchestrator]
command=$PROYECTO_DIR/.venv/bin/python3 $PROYECTO_DIR/server_orchestrator.py
directory=$PROYECTO_DIR
autostart=true
autorestart=true
stderr_logfile=/var/log/server_orchestrator.err.log
stdout_logfile=/var/log/server_orchestrator.out.log
user=root

[program:hardware_orchestrator]
command=$PROYECTO_DIR/.venv/bin/python3 $PROYECTO_DIR/hardware_orchestrator.py
directory=$PROYECTO_DIR
autostart=true
autorestart=true
stderr_logfile=/var/log/hardware_orchestrator.err.log
stdout_logfile=/var/log/hardware_orchestrator.out.log
user=root
EOT

# 7. Habilitar, arrancar y sincronizar Supervisorctl
echo "-----------------------------------------------------"
echo "🚀 6/6 Lanzando servicios y orquestadores independientes..."
systemctl enable supervisor
systemctl start supervisor
supervisorctl reread
supervisorctl update
supervisorctl restart all

echo "====================================================="
echo "✅ ¡PROVISIONAMIENTO CON VENV COMPLETADO CON ÉXITO!"
echo "📍 Directorio raíz: $PROYECTO_DIR"
echo "🤖 Entorno virtual listo."
echo "🖥️  Para ver la pantalla en modo Kiosco, ejecuta: sudo reboot"
echo "====================================================="