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

    # Configuración I2C
    i2c_cfg = config.get("i2c", config.get("I2C", {}))
    I2C_BUS_NUM = int(i2c_cfg.get("bus", i2c_cfg.get("BUS", 1)))
    raw_addr = i2c_cfg.get("device_address", i2c_cfg.get("DEVICE_ADDRESS", "0x13"))
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

except Exception as e:
    print(f"[❌ CONFIG ERROR] Error al parsear JSON: {e}")
    I2C_BUS_NUM, I2C_ADDR = 1, 0x13
    CANAL_ABRIR, CANAL_CERRAR = 1, 2
    TIEMPO_APERTURA, TIEMPO_ESPERA, TIEMPO_CIERRE = 2.5, 5.0, 2.5
    TIPO_CAMARA, DEVICE_INDEX, CAM_WIDTH, CAM_HEIGHT = "webcam", 0, 640, 480

# --- 2. CONTROLADOR FÍSICO I2C CON AUTO-DESCUBRIMIENTO ---
class RelayController:
    def __init__(self, bus_num=1, address=0x13):
        self.bus_num = bus_num
        self.address = address
        self.bus = None

        try:
            self.bus = SMBus(self.bus_num)
            
            # Si la dirección configurada es 0x0 o falla el ping, auto-escanear
            if not self.address or self.address == 0 or not self.probar_conexion(self.address):
                print("[🔍 AUTO-I2C] Buscando HAT en el bus...")
                auto_addr = self.auto_detectar_direccion()
                if auto_addr:
                    self.address = auto_addr
                    print(f"[✅ AUTO-I2C] Dirección encontrada dinámicamente: {hex(self.address)}")
                else:
                    self.address = 0x13

            self.all_off()
            print(f"[🔌 I2C] Conexión establecida con HAT en {hex(self.address)}")
        except Exception as e:
            print(f"[❌ I2C ERROR] No se pudo inicializar bus I2C: {e}")

    def probar_conexion(self, addr):
        try:
            self.bus.read_byte(addr)
            return True
        except Exception:
            return False

    def auto_detectar_direccion(self):
        # Escaneo de direcciones estándar (0x03 a 0x77)
        for addr in range(0x03, 0x78):
            try:
                self.bus.read_byte(addr)
                return addr
            except Exception:
                continue
        return None

    def on(self, channel: int):
        if self.bus and self.address:
            try:
                self.bus.write_byte_data(self.address, channel, 0xFF)
            except Exception as e:
                print(f"[❌ I2C ERROR] Fallo al activar canal {channel} en {hex(self.address)}: {e}")

    def off(self, channel: int):
        if self.bus and self.address:
            try:
                self.bus.write_byte_data(self.address, channel, 0x00)
            except Exception as e:
                print(f"[❌ I2C ERROR] Fallo al apagar canal {channel} en {hex(self.address)}: {e}")

    def all_off(self):
        if self.bus and self.address:
            for ch in range(1, 5):
                try:
                    self.bus.write_byte_data(self.address, ch, 0x00)
                except Exception:
                    pass

relay = RelayController(I2C_BUS_NUM, I2C_ADDR)

# Variables de control
bloqueo_motor = False
ultimo_qr_leido = ""
tiempo_ultimo_qr = 0

def secuencia_apertura_motor(nombre: str):
    global bloqueo_motor
    bloqueo_motor = True
    print(f"\n[🤖 AUTOMATIZACIÓN] 🔓 Secuencia de ENTRADA: {nombre}")
    try:
        print(f"[🤖 AUTOMATIZACIÓN] ⚡ Activando Relé {CANAL_ABRIR} ({TIEMPO_APERTURA}s)...")
        relay.on(CANAL_ABRIR)
        time.sleep(TIEMPO_APERTURA)
        relay.off(CANAL_ABRIR)
        print(f"[🤖 AUTOMATIZACIÓN] 🕒 Tiempo de cruce ({TIEMPO_ESPERA}s)...")
        time.sleep(TIEMPO_ESPERA)
    except Exception as e:
        print(f"[❌ ERROR MOTOR] Error en ciclo de apertura: {e}")
    finally:
        relay.all_off()
        bloqueo_motor = False
        print("[🤖 AUTOMATIZACIÓN] 🔒 Ciclo finalizado. Relés en reposo.\n")

def secuencia_cierre_motor(nombre: str):
    global bloqueo_motor
    bloqueo_motor = True
    print(f"\n[🤖 AUTOMATIZACIÓN] 🚪 Secuencia de SALIDA: {nombre}")
    try:
        print(f"[🤖 AUTOMATIZACIÓN] ⚡ Activando Relé {CANAL_CERRAR} ({TIEMPO_CIERRE}s)...")
        relay.on(CANAL_CERRAR)
        time.sleep(TIEMPO_CIERRE)
        relay.off(CANAL_CERRAR)
        print(f"[🤖 AUTOMATIZACIÓN] 🕒 Tiempo de cruce ({TIEMPO_ESPERA}s)...")
        time.sleep(TIEMPO_ESPERA)
    except Exception as e:
        print(f"[❌ ERROR MOTOR] Error en ciclo de cierre: {e}")
    finally:
        relay.all_off()
        bloqueo_motor = False
        print("[🤖 AUTOMATIZACIÓN] 🔒 Ciclo finalizado. Relés en reposo.\n")

# --- 3. RED / API FASTAPI ---
SERVER_API_URL = "http://localhost:8000/api/qr"

def enviar_qr_a_servidor(qr_data: str):
    global ultimo_qr_leido, tiempo_ultimo_qr
    ahora = time.time()

    if qr_data == ultimo_qr_leido and (ahora - tiempo_ultimo_qr) < 4.0:
        return

    if bloqueo_motor:
        print(f"[⚠️ HARDWARE] Mecanismo en movimiento. Ignorando lectura.")
        return

    ultimo_qr_leido = qr_data
    tiempo_ultimo_qr = ahora

    print(f"\n[🎯 HARDWARE] QR Detectado: {qr_data}")

    try:
        res = requests.post(SERVER_API_URL, json={"data": qr_data, "source_camera": TIPO_CAMARA}, timeout=2.5)
        if res.status_code == 200:
            data = res.json()
            accion = data.get("action", "").lower()
            nombre = data.get("name", "Invitado")
            movimiento = data.get("movimiento", "ENTRADA").upper()

            print(f"[📤 RED] Servidor: {accion.upper()} | Tipo: {movimiento} ({data.get('message', '')})")

            if accion == "unlock":
                target = secuencia_apertura_motor if movimiento == "ENTRADA" else secuencia_cierre_motor
                threading.Thread(target=target, args=(nombre,), daemon=True).start()
    except Exception as e:
        print(f"[❌ RED] Error al conectar con servidor: {e}")

# --- 4. BUCLE DE CAPTURA ---
def iniciar_captura_webcam():
    cap = cv2.VideoCapture(DEVICE_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    time.sleep(1.0)
    if not cap.isOpened():
        print(f"[❌ HARDWARE] No se pudo abrir /dev/video{DEVICE_INDEX}")
        return

    print("[ORQUESTADOR] 🎯 Monitoreo de QR activo...\n")
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            for codigo in decode(frame):
                datos = codigo.data.decode('utf-8').strip()
                if datos:
                    enviar_qr_a_servidor(datos)

            time.sleep(0.03)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        relay.all_off()

if __name__ == "__main__":
    iniciar_captura_webcam()
