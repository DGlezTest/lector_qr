import cv2
import json
import time
import os
import requests
from pyzbar.pyzbar import decode
from requests.auth import HTTPBasicAuth
# RPi.GPIO se reemplaza internamente por la emulación de rpi-lgpio
import RPi.GPIO as GPIO 

class HardwareOrchestrator:
    def __init__(self, config_name="config.json"):
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
        # En rpi-lgpio / Trixie, setmode suele venir preconfigurado en BCM de forma nativa
        try:
            GPIO.setmode(GPIO.BCM)
        except Exception:
            pass # Si la emulación lo maneja directo, ignoramos la advertencia
            
        entradas = self.config["GPIO_PINS"]["ENTRADAS"]
        salidas = self.config["GPIO_PINS"]["SALIDAS"]
        
        # Configurar Entradas (PUD_DOWN se emula correctamente en chips modernos)
        for pin in entradas.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            
        # Configurar Salidas
        for pin in salidas.values():
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    def setup_camera(self):
        cam_conf = self.config["CAMERA"]
        self.cap = cv2.VideoCapture(cam_conf["DEVICE_INDEX"])
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
        print("[ORQUESTADOR HARDWARE] Ejecutándose en Trixie de forma independiente...")
        ultimo_qr = None
        entradas = self.config["GPIO_PINS"]["ENTRADAS"]
        
        try:
            while True:
                if GPIO.input(entradas["SENSOR_PROXIMIDAD"]) == GPIO.HIGH:
                    ret, frame = self.cap.read()
                    if not ret:
                        continue
                    
                    frame = self.aplicar_giro_camara(frame)
                    qr_codes = decode(frame)
                    
                    for qr in qr_codes:
                        contenido_qr = qr.data.decode("utf-8")
                        if contenido_qr != ultimo_qr:
                            ultimo_qr = contenido_qr
                            
                            exito, nombre_usuario = self.consultar_servidor_central(contenido_qr)
                            if exito:
                                self.notificar_pantalla_local("success", nombre_usuario)
                                self.secuenciar_puerta()
                            else:
                                self.notificar_pantalla_local("denied")
                                self.encender_led_error()
                                
                            ultimo_qr = None
                time.sleep(0.1)
        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass
            self.cap.release()

if __name__ == "__main__":
    orchestrator = HardwareOrchestrator()
    orchestrator.run()
