import os
import sys
import time
import json
import threading
import requests
import cv2
from pyzbar.pyzbar import decode
from smbus2 import SMBus

# --- 1. CARGA DE CONFIGURACIÓN ---
CONFIG_PATH = "/home/pi/lector_qr/setup/config.json"
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup", "config.json")

print(f"[ORQUESTADOR] 📂 Abriendo configuración desde: {CONFIG_PATH}")

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Configuración de Cámara
    cam_cfg = config.get("camera", config.get("CAMERA", {}))
    TIPO_CAMARA = cam_cfg.get("type", cam_cfg.get("TYPE", "webcam")).lower().strip()
    DEVICE_INDEX = int(cam_cfg.get("device_index", cam_cfg.get("DEVICE_INDEX", 0)))
    CAM_WIDTH = int(cam_cfg.get("width", cam_cfg.get("WIDTH", 640)))
    CAM_HEIGHT = int(cam_cfg.get("height", cam_cfg.get("HEIGHT", 480)))

    # Configuración I2C (HAT 52Pi EP-0099)
    i2c_cfg = config.get("i2c", config.get("I2C", {}))
    I2C_BUS_NUM = int(i2c_cfg.get("bus", i2c_cfg.get("BUS", 1)))
    raw_addr = i2c_cfg.get("device_address", i2c_cfg.get("DEVICE_ADDRESS", "0x10"))
    I2C_ADDR = int(raw_addr, 16) if isinstance(raw_addr, str) else int(raw_addr)

    # Canales de Relé
    reles_cfg = config.get("rele_canales", config.get("RELE_CANALES", {}))
    CANAL_ABRIR = int(reles_cfg.get("rele_abrir_motor", reles_cfg.get("RELE_ABRIR_MOTOR", 1)))
    CANAL_CERRAR = int(reles_cfg.get("rele_cerrar_motor", reles_cfg.get("RELE_CERRAR_MOTOR", 2)))

    # Tiempos de maniobra
    tiempos_cfg = config.get("tiempos", config.get("TIEMPOS", {}))
    TIEMPO_APERTURA = float(tiempos_cfg.get("tiempo_apertura_motor", tiempos_cfg.get("TIEMPO_APERTURA_MOTOR", 2.5)))
    TIEMPO_ESPERA = float(tiempos_cfg.get("tiempo_espera_peaton", tiempos_cfg.get("TIEMPO_ESPERA_PEATON", 5.0)))
    TIEMPO_CIERRE = float(tiempos_cfg.get("tiempo_cierre_motor", tiempos_cfg.get("TIEMPO_CIERRE_MOTOR", 2.5)))

    print("[✅ CONFIG] Archivo JSON cargado correctamente.")
    print(f"[ORQUESTADOR HARDWARE] 🚀 Modo cámara: {TIPO_CAMARA.upper()} | HAT I2C: {hex(I2C_ADDR)} (Bus {I2C_BUS_NUM})")
    print(f"[ORQUESTADOR HARDWARE] 🔌 Relé Abrir: Ch {CANAL_ABRIR} ({TIEMPO_APERTURA}s) | Relé Cerrar: Ch {CANAL_CERRAR} ({TIEMPO_CIERRE}s)")

except Exception as e:
    print(f"[❌ CONFIG ERROR] Error al parsear JSON: {e}")
    sys.exit(1)

# --- 2. CONTROLADOR FÍSICO I2C (52Pi EP-0099) ---
class RelayController:
    def __init__(self, bus_num=1, address=0x10):
        self.bus_num = bus_num
        self.address = address
        try:
            self.bus = SMBus(self.bus_num)
            self.all_off()
            print(f"[🔌 I2C] Conexión establecida con HAT en {hex(self.address)}")
        except Exception as e:
            print(f"[❌ I2C ERROR] No se pudo inicializar bus I2C: {e}")
            self.bus = None

    def on(self, channel: int):
        if self.bus:
            try:
                self.bus.write_byte_data(self.address, channel, 0xFF)
            except Exception as e:
                print(f"[❌ I2C ERROR] Fallo al activar canal {channel}: {e}")

    def off(self, channel: int):
        if self.bus:
            try:
                self.bus.write_byte_data(self.address, channel, 0x00)
            except Exception as e:
                print(f"[❌ I2C ERROR] Fallo al apagar canal {channel}: {e}")

    def all_off(self):
        if self.bus:
            for ch in range(1, 5):
                try:
                    self.bus.write_byte_data(self.address, ch, 0x00)
                except Exception:
                    pass

relay = RelayController(I2C_BUS_NUM, I2C_ADDR)

# Variables de control de estado del motor y anti-rebote
bloqueo_motor = False
ultimo_qr_leido = ""
tiempo_ultimo_qr = 0

def secuencia_apertura_motor(nombre: str):
    """Secuencia ejecutada para registrar una ENTRADA"""
    global bloqueo_motor
    bloqueo_motor = True
    print(f"\n[🤖 AUTOMATIZACIÓN] 🔓 Iniciando secuencia de ENTRADA para: {nombre}")

    try:
        print(f"[🤖 AUTOMATIZACIÓN] ⚡ Activando Relé {CANAL_ABRIR} (Apertura) por {TIEMPO_APERTURA}s...")
        relay.on(CANAL_ABRIR)
        time.sleep(TIEMPO_APERTURA)
        relay.off(CANAL_ABRIR)
        print(f"[🤖 AUTOMATIZACIÓN] 🛑 Relé {CANAL_ABRIR} apagado.")

        print(f"[🤖 AUTOMATIZACIÓN] 🕒 Tiempo de cruce ({TIEMPO_ESPERA}s)...")
        time.sleep(TIEMPO_ESPERA)

    except Exception as e:
        print(f"[❌ ERROR MOTOR] Error en ciclo de apertura: {e}")
    finally:
        relay.all_off()
        bloqueo_motor = False
        print("[🤖 AUTOMATIZACIÓN] 🔒 Ciclo de entrada finalizado. Relés en reposo.\n")

def secuencia_cierre_motor(nombre: str):
    """Secuencia ejecutada para registrar una SALIDA"""
    global bloqueo_motor
    bloqueo_motor = True
    print(f"\n[🤖 AUTOMATIZACIÓN] 🚪 Iniciando secuencia de SALIDA para: {nombre}")

    try:
        print(f"[🤖 AUTOMATIZACIÓN] ⚡ Activando Relé {CANAL_CERRAR} (Cierre/Salida) por {TIEMPO_CIERRE}s...")
        relay.on(CANAL_CERRAR)
        time.sleep(TIEMPO_CIERRE)
        relay.off(CANAL_CERRAR)
        print(f"[🤖 AUTOMATIZACIÓN] 🛑 Relé {CANAL_CERRAR} apagado.")

        print(f"[🤖 AUTOMATIZACIÓN] 🕒 Tiempo de cruce ({TIEMPO_ESPERA}s)...")
        time.sleep(TIEMPO_ESPERA)

    except Exception as e:
        print(f"[❌ ERROR MOTOR] Error en ciclo de cierre: {e}")
    finally:
        relay.all_off()
        bloqueo_motor = False
        print("[🤖 AUTOMATIZACIÓN] 🔒 Ciclo de salida finalizado. Relés en reposo.\n")

# --- 3. PROCESAMIENTO Y COMUNICACIÓN CON FASTAPI ---
SERVER_API_URL = "http://localhost:8000/api/qr"

def enviar_qr_a_servidor(qr_data: str):
    global ultimo_qr_leido, tiempo_ultimo_qr

    ahora = time.time()
    # Anti-rebote: Evitar lecturas duplicadas continuas en menos de 4 segundos
    if qr_data == ultimo_qr_leido and (ahora - tiempo_ultimo_qr) < 4.0:
        return

    if bloqueo_motor:
        print(f"[⚠️ HARDWARE] QR detectado ({qr_data}), pero el mecanismo está en movimiento. Ignorando.")
        return

    ultimo_qr_leido = qr_data
    tiempo_ultimo_qr = ahora

    print(f"\n[🎯 HARDWARE] QR Detectado en lector: {qr_data}")

    payload = {
        "data": qr_data,
        "source_camera": TIPO_CAMARA
    }

    try:
        response = requests.post(SERVER_API_URL, json=payload, timeout=2.5)
        if response.status_code == 200:
            res_json = response.json()
            accion = res_json.get("action", "").lower()
            nombre = res_json.get("name", res_json.get("nombre", "Usuario"))
            movimiento = res_json.get("movimiento", "ENTRADA").upper()

            print(f"[📤 RED] API procesó trama. Decisión: {accion.upper()} | Tipo: {movimiento} ({res_json.get('message', '')})")

            if accion == "unlock":
                # Seleccionar la rutina según el estado devuelto por SQLite
                target_func = secuencia_apertura_motor if movimiento == "ENTRADA" else secuencia_cierre_motor
                hilo_motor = threading.Thread(target=target_func, args=(nombre,), daemon=True)
                hilo_motor.start()
            else:
                print("[🤖 AUTOMATIZACIÓN] 🔒 Acceso Rechazado por el servidor. Manteniendo relés apagados.")
        else:
            print(f"[⚠️ RED] El servidor respondió con código HTTP: {response.status_code}")

    except Exception as e:
        print(f"[❌ RED] No hay comunicación con server_orchestrator: {e}")

# --- 4. BUCLE DE CAPTURA DE CÁMARA (OPENCV / V4L2) ---
def iniciar_captura_webcam():
    print(f"[📸 HARDWARE] Inicializando cámara en /dev/video{DEVICE_INDEX} con backend V4L2...")
    cap = cv2.VideoCapture(DEVICE_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    time.sleep(1.0)

    if not cap.isOpened():
        print(f"[❌ HARDWARE] No se pudo abrir /dev/video{DEVICE_INDEX}")
        return

    print("[ORQUESTADOR] 🎯 Sistema de monitoreo activo. Coloque un código QR...\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            codigos = decode(frame)
            for codigo in codigos:
                datos = codigo.data.decode('utf-8').strip()
                if datos:
                    enviar_qr_a_servidor(datos)

            time.sleep(0.03)

    except KeyboardInterrupt:
        print("\n[🛑] Deteniendo orquestador de hardware...")
    finally:
        cap.release()
        relay.all_off()

if __name__ == "__main__":
    iniciar_captura_webcam()

