import cv2
import json
import time 
import os
import request 
from pyzbar.pyzbar import decode
from requests.auth import HTTPBasicAuth
import Rpi.GPIO as GPIO

class HardwareOrchestrator:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.load_config()
        self.setup_gpio()
        self.setup_camera()


    def load_config(self):
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

    def save_config(self):
        with open(self.config_path, 'w')as f:
            json.dump(self.config, f, indent=4)

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        entradas = self.config["GPIO_PINS"]["ENTRADAS"]
        salidas = self.config["GPIO_PINS"]["SALIDAS"]

        # Configuramos los pines de entrada
        for pin in entradas.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        # Configuramos los pines de salida
        for pin in salidas.values():
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    def setup_camera(self):
        cam_conf = self.config["CAMERA"]
        self.cap = cv2.VideoCapture(cam_conf["CAMERA_INDEX"])
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_conf["FRAME_WIDTH"])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_conf["FRAME_HEIGHT"])

    def aplicar_giro_camara(self, frame):
        cam_conf = self.config["CAMERA"]
        if cam_conf["FLIP_VERTICAL"] and cam_conf["FLIP_HORIZONTAL"]:
            frame = cv2.flip(frame, -1)
        elif cam_conf["FLIP_VERTICAL"]:
            frame = cv2.flip(frame, 0)
        elif cam_conf["FLIP_HORIZONTAL"]:
            frame = cv2.flip(frame, 1)
        return frame
    
    def secuenciar_puerta(self):
        salidas = self.config["GPIO_PINS"]["SALIDAS"]
        tiempos = self.config["TIEMPOS_PUERTA"]
        
        
        print("[Hardware] iniciando secuencia de acceso...")
        GPIO.output(salidas["INDICADOR_VERDE"], GPIO.HIGH)

        #Abrimos puertas
        GPIO.output(salidas["RELAY_MOTOR_1"], GPIO.HIGH)
        GPIO.output(salidas["RELAY_MOTOR_2"], GPIO.HIGH)
        time.sleep(tiempos["TIEMPO:APERTURA_MOTOR"])

        #Duracion con la puerta abierta
        time.sleep(tiempos["PUERTA_ESPERA_PEATON"])

        #cerramos puertas
        GPIO.output(salidas["RELAY_MOTOR_1"], GPIO.LOW)
        GPIO.output(salidas["RELAY_MOTOR_2"], GPIO.LOW)
        time.sleep(tiempos["TIEMPO:CERRADO_MOTOR"])
        GPIO.output(salidas["INDICADOR_VERDE"], GPIO.LOW)

        print("[HARDWARE] Secuencia finalizada. Puerta Asegurada.")

    def encender_led_rojo(self):
        salidas = self.config["GPIO_PINS"]["SALIDAS"]
        GPIO.output(salidas["INDICADOR_ROJO"], GPIO.HIGH)  
        time.sleep(2.0)
        GPIO.output(salidas["INDICADOR_ROJO"], GPIO.LOW)

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
        """Envía el resultado al Orquestador del Servidor Local para que actualice el JS"""
        try:
            requests.post("http://localhost:8000/api/evento-local", json={"status": status, "nombre": nombre}, timeout=2)
        except Exception:
            pass # Si el servidor web está caído, el hardware no se detiene

    def run(self):
        print("[ORQUESTADOR HARDWARE] Ejecutándose de forma independiente...")
        ultimo_qr = None
        entradas = self.config["GPIO_PINS"]["ENTRADAS"]
        
        try:
            while True:
                # El sensor de proximidad activa la lectura para no gastar recursos continuos
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
                            
                            # 1. Validar remotamente
                            exito, nombre_usuario = self.consultar_servidor_central(contenido_qr)
                            
                            if exito:
                                # 2. Avisar al orquestador del servidor (Pantalla JS)
                                self.notificar_pantalla_local("success", nombre_usuario)
                                # 3. Mover motores/relevadores locales
                                self.secuenciar_puerta()
                            else:
                                self.notificar_pantalla_local("denied")
                                self.encender_led_error()
                                
                            ultimo_qr = None
                
                time.sleep(0.1)
        finally:
            GPIO.cleanup()
            self.cap.release()

if __name__ == "__main__":
    orchestrator = HardwareOrchestrator()
    orchestrator.run()
    
