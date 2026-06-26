import cv2
import json
import time
import os
import requests
from pyzbar.pyzbar import decode
from requests.auth import HTTPBasicAuth
import RPi.GPIO as GPIO 

class HardwareOrchestrator:
    def __init__(self, config_name="setup/config.json"):
        # Calcular ruta absoluta de forma dinámica
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_dir, config_name)
        
        print(f"[ORQUESTADOR] Cargando configuración desde: {self.config_path}")
        self.load_config()
        self.setup_gpio()
        self.setup_camera()

    def load_config(self):
        with open(self.config_path, "r") as f:
            self.config = json.load(f)

    def setup_gpio(self):
        try:
            GPIO.setmode(GPIO.BCM)
        except Exception:
            pass
            
        entradas = self.config["GPIO_PINS"]["ENTRADAS"]
        salidas = self.config["GPIO_PINS"]["SALIDAS"]
        
        for pin in entradas.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            
        for pin in salidas.values():
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    def setup_camera(self):
        # 1. Extraer la subconfiguración de la cámara
        cam_conf = self.config["CAMERA"]
        
        # 2. Definir dinámicamente el índice leyendo tu clave del JSON (asume "device_id" o "index")
        # Si en tu JSON la clave está en mayúsculas (ej. "DEVICE_ID"), cámbialo aquí a "DEVICE_ID"
        camera_idx = cam_conf.get("device_id", cam_conf.get("index", 0))
        
        # 3. Forzar el backend V4L2 nativo de Linux usando la variable local
        # Intentar con el índice del JSON (ej. 0)
        self.cap = cv2.VideoCapture(camera_idx, cv2.CAP_V4L2)

        # Si no abre, forzar el índice 1 o autodetectar con -1
        if not self.cap.isOpened():
            print(f"[WARN] No se pudo abrir index {camera_idx}. Intentando con index 1...")
            self.cap = cv2.VideoCapture(1, cv2.CAP_V4L2)

        if not self.cap.isOpened():
            print("[WARN] Intentando con autodetectar (-1)...")
            self.cap = cv2.VideoCapture(-1, cv2.CAP_V4L2)
        
        # 4. Configurar el formato MJPEG para evitar que el buffer de frames se congele en Trixie
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_conf["WIDTH"])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_conf["HEIGHT"])

    def aplicar_giro_camara(self, frame):
        cam_conf = self.config["CAMERA"]
        if cam_conf["FLIP_VERTICAL"] and cam_conf["FLIP_HORIZONTAL"]:
            return cv2.flip(frame, -1)
        elif cam_conf["FLIP_VERTICAL"]:
            return cv2.flip(frame, 0)
        elif cam_conf["FLIP_HORIZONTAL"]:
            return cv2.flip(frame, 1)
        return frame

    def secuenciar_puerta(self):
        salidas = self.config["GPIO_PINS"]["SALIDAS"]
        tiempos = self.config["TIEMPOS_PUERTA"]
        
        print("[HARDWARE] Iniciando secuencia de acceso...")
        GPIO.output(salidas["LED_ESTADO_VERDE"], GPIO.HIGH)
        
        print("[HARDWARE] Abriendo puerta...")
        GPIO.output(salidas["RELAY_ABRIR_MOTOR"], GPIO.HIGH)
        time.sleep(tiempos["TIEMPO_APERTURA_MOTOR"])
        GPIO.output(salidas["RELAY_ABRIR_MOTOR"], GPIO.LOW)
        
        print("[HARDWARE] Puerta abierta. Esperando peatón...")
        time.sleep(tiempos["TIEMPO_ESPERA_PEATON"])
        
        print("[HARDWARE] Cerrando puerta...")
        GPIO.output(salidas["RELAY_CERRAR_MOTOR"], GPIO.HIGH)
        time.sleep(tiempos["TIEMPO_CIERRE_MOTOR"])
        GPIO.output(salidas["RELAY_CERRAR_MOTOR"], GPIO.LOW)
        
        GPIO.output(salidas["LED_ESTADO_VERDE"], GPIO.LOW)
        print("[HARDWARE] Secuencia finalizada.")

    def encender_led_error(self):
        salidas = self.config["GPIO_PINS"]["SALIDAS"]
        GPIO.output(salidas["LED_ESTADO_ROJO"], GPIO.HIGH)
        time.sleep(2.0)
        GPIO.output(salidas["LED_ESTADO_ROJO"], GPIO.LOW)

    def consultar_servidor_central(self, qr_token):
        try:
            auth = HTTPBasicAuth(self.config["PI_USERNAME"], self.config["PI_PASSWORD"])
            payload = {"qr_token": qr_token, "device_id": "pi_acceso_01"}
            response = requests.post(self.config["SERVER_URL"], json=payload, auth=auth, timeout=5)
            if response.status_code == 200:
                return True, response.json().get("nombre", "Usuario")
            return False, None
        except Exception as e:
            print(f"[API ERROR] No se pudo conectar al servidor central: {e}")
            return False, None

    def notificar_pantalla_local(self, status, nombre=""):
        try:
            requests.post("http://localhost:8000/api/evento-local", json={"status": status, "nombre": nombre}, timeout=2)
        except Exception:
            pass

    def run(self):
        print("[ORQUESTADOR HARDWARE] 🚀 MODO DESARROLLO: Cámara permanentemente encendida...")
        ultimo_qr = None

        try:
            while True:
                # 1. Capturar frame directamente sin esperar sensor
                ret, frame = self.cap.read()
                if not ret:
                    # Si falla un frame, duerme un instante y reintenta en la siguiente vuelta
                    time.sleep(0.1)
                    continue

                # 2. Aplicar rotación configurada
                frame = self.aplicar_giro_camara(frame)
                
                # 3. Convertir a escala de grises (Evita que PyZbar se congele en Debian Trixie)
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # 4. Buscar y decodificar códigos QR
                qr_codes = decode(gray_frame)

                for qr in qr_codes:
                    contenido_qr = qr.data.decode("utf-8")
                    if contenido_qr != ultimo_qr:
                        print(f"[ORQUESTADOR] 🎯 ¡Código QR detectado!: {contenido_qr}")
                        ultimo_qr = contenido_qr
                        
                        # Consultar al backend local
                        exito, nombre_usuario = self.consultar_servidor_central(contenido_qr)
                        if exito:
                            print(f"[ORQUESTADOR] ✅ Acceso concedido a: {nombre_usuario}")
                            self.notificar_pantalla_local("success", nombre_usuario)
                            self.secuenciar_puerta()
                        else:
                            print("[ORQUESTADOR] ❌ Acceso denegado")
                            self.notificar_pantalla_local("denied")
                            self.encender_led_error()
                            
                        # Limpiar el caché del último QR para permitir lecturas consecutivas rápidas
                        ultimo_qr = None
                
                # Pequeña pausa de control para no saturar la CPU (aprox. 30 FPS)
                time.sleep(0.03)

        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass
            self.cap.release()
            print("[ORQUESTADOR] Recursos de hardware liberados correctamente.")

if __name__ == "__main__":
    orchestrator = HardwareOrchestrator()
    orchestrator.run()
