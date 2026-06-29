#!/bin/bash
# Forzar a que Chromium no busque sesiones anteriores rotas o alertas de cierre
rm -rf ~/.config/chromium/Default/Preferences
rm -rf ~/.config/chromium/Singleton*

# 🚫 DESACTIVAR PROTECTOR DE PANTALLA Y AHORRO DE ENERGÍA INFINITO
export DISPLAY=:0
xset s off       # Desactiva el salvapantallas nativo
xset _blank      # Evita que la pantalla se vaya a negro por inactividad
xset -dpms       # Desactiva la administración de energía del monitor (DPMS)

exec chromium \
  --window-size=1280,800 \
  --window-position=0,0 \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --check-for-update-interval=31536000 \
  --disable-pinch \
  --force-device-scale-factor=1.0 \
  http://localhost:8000