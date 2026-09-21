#!/bin/bash
xset s off 2>/dev/null
xset s noblank 2>/dev/null
xset -dpms 2>/dev/null

# Forzar modo espejo idéntico en ambas pantallas
xrandr --output HDMI-1 --mode 1280x800 --primary \
       --output HDMI-2 --mode 1280x800 --same-as HDMI-1 2>/dev/null || true

echo "🌐 Lanzando Chromium en modo Kiosco Fullscreen..."
exec chromium \
  --window-size=1280,800 \
  --window-position=0,0 \
  --kiosk \
  --start-fullscreen \
  --noerrdialogs \
  --disable-infobars \
  --disable-gpu \
  --disable-software-rasterizer \
  --force-device-scale-factor=1.0 \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  --disable-pinch \
  http://localhost:8000
