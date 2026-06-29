#!/usr/bin/env python3
import os
import sys
import json
import time
import cv2
import requests
from pyzbar.pyzbar import decode
import RPi.GPIO as GPIO

# --- CONFIGURACIÓN DE RUTAS Y CONSTANTES ---
CONFIG_PATH = "/home/pi/lector_qr/setup/config.json"
URL_SERVIDOR = "http://localhost:8000/api/qr"  # Servidor local FastAPI

print(f"[ORQUESTADOR] 📂 Abriendo configuración desde: {CONFIG_PATH}")

# --- LEER CONFIGURACIÓN DEL JSON ---
try:
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    
    # Extraer la configuración de la cámara (Soporta mayúsculas y minúsculas)
    config_lowercase = {k.lower(): v for k, v in config.items()}
    camera_config = config_lowercase.get("camera", {})
    camera_config_lowercase = {k.lower(): v for k, v in camera_config.items()}
    
    # Capturar el tipo exacto de cámara
    TIPO_CAMARA = camera_config_lowercase.get("type", "webcam").lower().strip()
    
    # Extraer GPIOs mapeando los diccionarios internos
    gpio_config = config_lowercase.get("gpio_pins", {})
    gpio_config_lowercase = {k.lower(): v for k, v in gpio_config.items()}
    
    # Mantener soporte si tus claves internas están en mayúsculas ("ENTRADAS", "SALIDAS")
    entradas_raw = gpio_config_lowercase.get("entradas", {})
    ENTRADAS = {k.upper(): v for k, v in entradas_raw.items()}
    
    salidas_raw = gpio_config_lowercase.get("salidas", {})
    SALIDAS = {k.upper(): v for k, v in salidas_raw.items()}
    
    # Tiempos de automatización de relés
    tiempos_raw = config_lowercase.get("tiempos_puerta", {})
    TIEMPOS = {k.upper(): v for k, v in tiempos_raw.items()}

    print(f"[✅ CONFIG] Archivo JSON cargado correctamente.")
    print(f"[ORQUESTADOR HARDWARE] 🚀 Modo de cámara seleccionado: {TIPO_CAMARA.upper()}")

except Exception as e:
    print(f"[❌ CONFIG ERROR] Hubo un problema al parsear el JSON: {e}")
    print("[⚠️ FALLBACK] Usando 'webcam' por seguridad general.")
    TIPO_CAMARA = "webcam"


# --- IMPORTACIÓN CONDICIONAL DE PICAMERA2 ---
if TIPO_CAMARA == "raspberry_pi":
    try:
        from picamera2 import Picamera2
        print("[📸 HARDWARE] Librería Picamera2 importada con éxito desde el sistema.")
    except ImportError as e:
        print(f"[❌ COMPILACIÓN] Se configuró 'raspberry_pi' pero Picamera2 no está instalada: {e}")
        sys.exit(1)


# --- FUNCIONES DE CONTROL DE VIDEO ---
def inicializar_camara_pi():
    """Inicia el flujo de captura nativo para sensores CSI M2"""
    try:
        picam2 = Picamera2()
        picam2.configure(picam2.create_preview_configuration(main={"size": (640, 480)}))
        picam2.start()
        print("[📸 HARDWARE] Sensor nativo de Raspberry Pi M2 inicializado.")
        return picam2
    except Exception as e:
        print(f"[❌ HARDWARE] Error físico crítico en cámara del Pi: {e}")
        sys.exit(1)

def capturar_frame_pi(picam2):
    frame_rgb = picam2.capture_array()
    frame_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    return frame_gray

def inicializar_webcam():
    """Inicia el flujo de captura para webcams USB genéricas"""
    try:
        idx = camera_config.get("DEVICE_INDEX", 0) if isinstance(camera_config, dict) else 0
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError("No se detecta dispositivo USB en /dev/video")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("[📸 HARDWARE] Puerto de Webcam USB inicializado.")
        return cap
    except Exception as e:
        print(f"[❌ HARDWARE] Error físico crítico en Webcam USB: {e}")
        sys.exit(1)

def capturar_frame_webcam(cap):
    ret, frame_bgr = cap.read()
    if not ret:
        return None
    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return frame_gray


# --- CONTROL DE PERIFÉRICOS ELECTRONICOS (GPIO) ---
def inicializar_gpios():
    """Configura el mapeo inicial de relés, sensores y LEDs"""
    print("[⚙️ GPIO] Configurando pines digitales en la placa...")
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Mapear Entradas
    for nombre, pin in ENTRADAS.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print(f"  📥 Entrada -> {nombre}: Pin BCM {pin}")
        
    # Mapear Salidas
    for nombre, pin in SALIDAS.items():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
        print(f"  📤 Salida  -> {nombre}: Pin BCM {pin}")

def ejecutar_secuencia_apertura():
    """Ejecuta la automatización física de la compuerta"""
    print("[🤖 AUTOMATIZACIÓN] 🔓 Ejecutando secuencia de apertura autorizada...")
    try:
        # 1. Indicadores visuales iniciales
        if "LED_ESTADO_VERDE" in SALIDAS and "LED_ESTADO_ROJO" in SALIDAS:
            GPIO.output(SALIDAS["LED_ESTADO_VERDE"], GPIO.HIGH)
            GPIO.output(SALIDAS["LED_ESTADO_ROJO"], GPIO.LOW)
        
        # 2. Accionar Motor de Apertura
        if "RELAY_ABRIR_MOTOR" in SALIDAS:
            print("  🔁 Activando relé de apertura del motor...")
            GPIO.output(SALIDAS["RELAY_ABRIR_MOTOR"], GPIO.HIGH)
            time.sleep(TIEMPOS.get("TIEMPO_APERTURA_MOTOR", 2.5))
            GPIO.output(SALIDAS["RELAY_ABRIR_MOTOR"], GPIO.LOW)
        
        # 3. Retraso peatonal seguro
        print("  🕒 Esperando cruce seguro del usuario...")
        time.sleep(TIEMPOS.get("TIEMPO_ESPERA_PEATON", 5.0))
        
        # 4. Accionar Motor de Cierre
        if "RELAY_CERRAR_MOTOR" in SALIDAS:
            print("  🔁 Activando relé de cierre del motor...")
            GPIO.output(SALIDAS["RELAY_CERRAR_MOTOR"], GPIO.HIGH)
            time.sleep(TIEMPOS.get("TIEMPO_CIERRE_MOTOR", 2.5))
            GPIO.output(SALIDAS["RELAY_CERRAR_MOTOR"], GPIO.LOW)
            
    except Exception as e:
        print(f"[❌ AUTOMATIZACIÓN] Error al conmutar relés: {e}")
    finally:
        # 5. Volver al estado de reposo (Espera de códigos)
        if "LED_ESTADO_VERDE" in SALIDAS and "LED_ESTADO_ROJO" in SALIDAS:
            GPIO.output(SALIDAS["LED_ESTADO_VERDE"], GPIO.LOW)
            GPIO.output(SALIDAS["LED_ESTADO_ROJO"], GPIO.HIGH)
        print("[🤖 AUTOMATIZACIÓN] 🔒 Ciclo finalizado. Esperando nuevo código.")

def ejecutar_secuencia_rechazo():
    """Parpadea el LED Rojo físico indicando acceso denegado en sincronía con la pantalla"""
    print("[🤖 AUTOMATIZACIÓN] 🔒 Acceso Rechazado por el servidor. Manteniendo traba cerrada.")
    if "LED_ESTADO_ROJO" in SALIDAS:
        try:
            # Simular un parpadeo rápido de advertencia en el gabinete del torniquete
            for _ in range(3):
                GPIO.output(SALIDAS["LED_ESTADO_ROJO"], GPIO.LOW)
                time.sleep(0.15)
                GPIO.output(SALIDAS["LED_ESTADO_ROJO"], GPIO.HIGH)
                time.sleep(0.15)
        except Exception as e:
            print(f"[❌ AUTOMATIZACIÓN] Error al parpadear LED de rechazo: {e}")


# --- BUCLE PRINCIPAL ---
def main():
    inicializar_gpios()
    
    # Encender LED Rojo inicial si existe en el cableado
    if "LED_ESTADO_ROJO" in SALIDAS:
        GPIO.output(SALIDAS["LED_ESTADO_ROJO"], GPIO.HIGH)

    # Iniciar la cámara correspondiente
    camara_objeto = inicializar_camara_pi() if TIPO_CAMARA == "raspberry_pi" else inicializar_webcam()

    print("[ORQUESTADOR] 🎯 Sistema de monitoreo activo. Coloque un código QR...")
    
    ultimo_codigo = ""
    tiempo_bloqueo = 0

    try:
        while True:
            # 1. Adquirir frame en escala de grises
            frame_gray = capturar_frame_pi(camara_objeto) if TIPO_CAMARA == "raspberry_pi" else capturar_frame_webcam(camara_objeto)

            if frame_gray is None:
                time.sleep(0.01)
                continue

            # 2. Buscar códigos QR utilizando el motor PyZbar
            codigos = decode(frame_gray)
            
            for qr in codigos:
                contenido = qr.data.decode('utf-8').strip()
                ahora = time.time()
                
                # Control anti-rebote (Evita ráfagas repetidas en el mismo segundo)
                if contenido == ultimo_codigo and (ahora - tiempo_bloqueo) < 3.0:
                    continue
                
                print(f"\n[🎯 HARDWARE] QR Detectado en lector: {contenido}")
                ultimo_codigo = contenido
                tiempo_bloqueo = ahora

                # 3. Enviar el paquete de datos al servidor web local
                try:
                    payload = {"data": contenido, "source_camera": TIPO_CAMARA}
                    respuesta = requests.post(URL_SERVIDOR, json=payload, timeout=2)
                    
                    if respuesta.status_code == 200:
                        # 🔌 DECODIFICAMOS LA RESPUESTA DE NUESTRA NUEVA API
                        datos_servidor = respuesta.json()
                        accion = datos_servidor.get("action", "lock")
                        mensaje = datos_servidor.get("message", "Sin mensaje")
                        
                        print(f"[📤 RED] API procesó trama correctamente. Decisión: {accion.upper()} ({mensaje})")
                        
                        # 🎛️ TOMAR ACCIÓN FÍSICA SEGÚN EL REGLAMENTO DEL ENRUTADOR
                        if accion == "unlock":
                            ejecutar_secuencia_apertura()
                        else:
                            ejecutar_secuencia_rechazo()
                    else:
                        print(f"[⚠️ RED] El servidor rechazó la trama. Código HTTP: {respuesta.status_code}")
                        ejecutar_secuencia_rechazo()
                        
                except Exception as e:
                    print(f"[❌ RED] No hay comunicación con server_orchestrator: {e}")
                    ejecutar_secuencia_rechazo()

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[ORQUESTADOR] Cierre manual solicitado.")
    finally:
        print("[ORQUESTADOR] Liberando periféricos...")
        if TIPO_CAMARA == "raspberry_pi" and camara_objeto:
            camara_objeto.stop()
            camara_objeto.close()
        elif TIPO_CAMARA == "webcam" and camara_objeto:
            camara_objeto.release()
            
        try:
            GPIO.cleanup()
        except:
            pass
        print("[ORQUESTADOR] 👋 Entorno limpio. Hilo finalizado.")

if __name__ == "__main__":
    main()