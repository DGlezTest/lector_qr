#!/bin/bash

# 1. Asegurar que el script se ejecute como ROOT
if [ "$EUID" -ne 0 ]; then
  echo "❌ Por favor, ejecuta este script usando sudo: sudo ./setup.sh"
  exit 1
fi

echo "====================================================="
echo "⚙️  INICIANDO CONFIGURACIÓN AUTOMÁTICA DEL PI + KIOSCO ⚙️"
echo "====================================================="

# Obtener rutas absolutas dinámicas
SETUP_DIR=$(dirname "$(readlink -f "$0")")
PROYECTO_DIR=$(dirname "$SETUP_DIR")

# 2. Actualizar e instalar dependencias (Incluyendo entorno gráfico mínimo para Kiosco)
echo "📦 1/6 Instalando Supervisor, dependencias de red y entorno gráfico Kiosco..."
apt-get update -y
apt-get install -y supervisor python3-pip python3-dev libzbar0 wpa-supplicant \
                   xserver-xorg xinit x11-xserver-utils unclutter chromium-browser

# 3. Configurar Red Wi-Fi de forma interactiva (Opcional)
echo "-----------------------------------------------------"
read -p "❓ ¿Deseas configurar una red Wi-Fi en este momento? (s/n): " CONFIG_WIFI
if [ "$CONFIG_WIFI" = "s" ] || [ "$CONFIG_WIFI" = "S" ]; then
    read -p "⌨️  Ingresa el nombre de la red (SSID): " WIFI_SSID
    read -s -p "⌨️  Ingresa la contraseña de la red: " WIFI_PASS
    echo ""
    
    cp "$SETUP_DIR/wpa_supplicant.conf.template" /etc/wpa_supplicant/wpa_supplicant.conf
    sed -i "s/REPLACE_SSID/$WIFI_SSID/g" /etc/wpa_supplicant/wpa_supplicant.conf
    sed -i "s/REPLACE_PASSWORD/$WIFI_PASS/g" /etc/wpa_supplicant/wpa_supplicant.conf
    
    echo "📶 Red Wi-Fi escrita en el sistema."
    wpa_cli -i wlan0 reconfigure
fi

# 4. Instalar los requerimientos de Python
echo "-----------------------------------------------------"
echo "🐍 2/6 Instalando librerías de Python desde requirements.txt..."
pip3 install -r "$SETUP_DIR/requirements.txt" --break-system-packages

# 5. Mover el config.json a la raíz si no existe
echo "-----------------------------------------------------"
echo "⚙️  3/6 Desplegando archivo de configuración config.json..."
if [ ! -f "$PROYECTO_DIR/config.json" ]; then
    cp "$SETUP_DIR/config.json" "$PROYECTO_DIR/config.json"
    echo "📄 Plantilla config.json copiada a la raíz."
else
    echo "ℹ️  Ya existe un archivo config.json en la raíz."
fi

# 6. CONFIGURACIÓN DEL MODO KIOSCO (Inicio automático en pantalla HDMI)
echo "-----------------------------------------------------"
echo "🖥️  4/6 Configurando arranque en Modo Kiosco..."

# Copiar el script de lanzamiento a la raíz y darle permisos
cp "$SETUP_DIR/kiosco.sh.template" "$PROYECTO_DIR/kiosco.sh"
chmod +x "$PROYECTO_DIR/kiosco.sh"

# Configurar el archivo .xinitrc del sistema para que sepa qué ejecutar al abrir los gráficos
cat <<EOT > /root/.xinitrc
exec $PROYECTO_DIR/kiosco.sh
EOT

# Crear un servicio en Supervisor o añadirlo al bashrc/systemd para que lance el entorno gráfico al bootear.
# La forma más limpia en Raspberry Pi OS Lite es indicarle a la terminal que si está en la tty1 (pantalla física), inicie X.
if ! grep -q "startx" /root/.bashrc; then
    cat <<EOT >> /root/.bashrc

# Lanzar el modo kiosco automáticamente al iniciar sesión en la terminal física 1
if [ -z "\$DISPLAY" ] && [ "\$(tty)" = "/dev/tty1" ]; then
    startx
fi
EOT
fi

# 7. Preparar y mover la configuración de Supervisor para los Orquestadores Backend
echo "-----------------------------------------------------"
echo "📋 5/6 Registrando rutas en la configuración de Supervisor..."

cat <<EOT > /etc/supervisor/conf.d/mi_escaner.conf
[program:server_orchestrator]
command=/usr/bin/python3 $PROYECTO_DIR/server_orchestrator.py
directory=$PROYECTO_DIR
autostart=true
autorestart=true
stderr_logfile=/var/log/server_orchestrator.err.log
stdout_logfile=/var/log/server_orchestrator.out.log
user=root

[program:hardware_orchestrator]
command=/usr/bin/python3 $PROYECTO_DIR/hardware_orchestrator.py
directory=$PROYECTO_DIR
autostart=true
autorestart=true
stderr_logfile=/var/log/hardware_orchestrator.err.log
stdout_logfile=/var/log/hardware_orchestrator.out.log
user=root
EOT

# 8. Levantar los servicios en la Raspberry Pi
echo "-----------------------------------------------------"
echo "🚀 6/6 Lanzando servicios y orquestadores independientes..."
supervisorctl reread
supervisorctl update
supervisorctl restart all

echo "====================================================="
echo "✅ ¡PROVISIONAMIENTO COMPLETO CON MODO KIOSCO!"
echo "📍 Tu pantalla HDMI se actualizará automáticamente al reiniciar."
echo "🤖 Para aplicar los cambios gráficos por completo, ejecuta: sudo reboot"
echo "====================================================="