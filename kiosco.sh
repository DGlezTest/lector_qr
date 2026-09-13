#!/bin/bash
xset s off 2>/dev/null
xset s noblank 2>/dev/null
xset -dpms 2>/dev/null

# 1. Configurar espejo/clonado forzado a 1280x800
xrandr --output HDMI-1 --mode 1024x650 --primary --output HDMI-2 --mode 1024x650 --same-as HDMI-1 2>/dev/null || \
xrandr --output HDMI-A-1 --mode 1024x650 --primary --output HDMI-A-2 --mode 1024x650 --same-as HDMI-A-1 2>/dev/null || true

echo "🌐 Lanzando Chromium en modo Kiosco Fullscreen..."
exec chromium \
  --window-size=1024,650 \
  --window-position=0,0 \
  --kiosk \
  --start-fullscreen \
  --noerrdialogs \
  --disable-infobars \
  --disable-gpu \
  --disable-software-rasterizer \
  --force-device-scale-factor=1.25 \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  --disable-pinch \
  http://localhost:8000
