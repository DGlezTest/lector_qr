import os
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Orquestador de Interfaz Local")

# Localizar la ruta absoluta
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# --- MODELOS DE DATOS ---
class QRPayload(BaseModel):
    data: str
    source_camera: str

class EventoLocal(BaseModel):
    status: str
    nombre: str = ""

# --- GESTOR DE CONEXIONES WEBSOCKET ---
class ConnectionManager:
    def __init__(self):
        self.active_connections = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WEBSOCKET] Kiosco conectado. Activas: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WEBSOCKET] Kiosco desconectado. Activas: {len(self.active_connections)}")
        
    async def send_json(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# --- ENDPOINTS HTTP ---
@app.get("/")
async def get_index():
    html_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>❌ Error: templates/index.html no encontrado</h1>", status_code=404)

@app.post("/api/qr")
async def recibir_evento_qr(qr: QRPayload):
    print(f"[SERVER] 🎯 QR Recibido desde el Hardware: '{qr.data}'")
    
    # Mandamos el JSON directo al index.html mediante el WebSocket activo
    await manager.send_json({
        "status": "success",
        "data": qr.data,
        "source": qr.source_camera,
        "nombre": "Acceso Autorizado"
    })
    return {"status": "processed", "target": "kiosk_display"}

@app.post("/api/evento-local")
async def recibir_evento_hardware(evento: EventoLocal):
    await manager.send_json({
        "status": evento.status,
        "nombre": evento.nombre
    })
    return {"status": "notificado_a_pantalla"}

# --- WEBSOCKET ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
