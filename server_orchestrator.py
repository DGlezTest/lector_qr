import os
import cv2
import asyncio
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from pyzbar.pyzbar import decode
import uvicorn

app = FastAPI(title="Orquestador de Interfaz Local")

# Localizar la ruta absoluta
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Inicializar cámara globalmente con backend V4L2 para Linux (Raspberry Pi)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

class EventoLocal(BaseModel):
    status: str
    nombre: str = ""

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def send_json(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# --- LÓGICA DE DETECCION Y STREAMING ---
ultimo_qr = None

def generar_frames():
    global ultimo_qr
    while True:
        success, frame = camera.read()
        if not success:
            time.sleep(0.1)
            continue
        
        # 1. Procesar QR en escala de grises (Previene congelamientos en Trixie)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        qr_codes = decode(gray_frame)
        
        for qr in qr_codes:
            contenido_qr = qr.data.decode("utf-8")
            if contenido_qr != ultimo_qr:
                ultimo_qr = contenido_qr
                print(f"[SERVER] 🎯 QR Detectado en Stream: {contenido_qr}")
                
                # 💡 DISPARO MÁGICO: Enviamos de inmediato el JSON al Frontend por WebSocket
                # Como no estamos en un entorno async nativo aquí, usamos asyncio
                asyncio.run(manager.send_json({
                    "status": "success",  # O evaluar contra tu backend si es válido/denegado
                    "nombre": "Usuario QR" 
                }))
                
                # Pequeña pausa para no leer el mismo QR consecutivamente en el mismo segundo
                time.sleep(1.0) 
                ultimo_qr = None

        # 2. Convertir el frame a formato JPEG para la web
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
            
        frame_bytes = buffer.tobytes()
        
        # Generar el flujo multipart estándar para streaming de video en navegadores
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# --- ENDPOINTS ---

@app.get("/")
async def get_index():
    html_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>❌ Error: templates/index.html no encontrado</h1>", status_code=404)

# Nuevo Endpoint para alimentar la etiqueta <img> del HTML
@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generar_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/evento-local")
async def recibir_evento_hardware(evento: EventoLocal):
    await manager.send_json({
        "status": evento.status,
        "nombre": evento.nombre
    })
    return {"status": "notificado_a_pantalla"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)