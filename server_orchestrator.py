import os
import sys
from app.routers.api_v1 import router as api_router, set_websocket_manager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Orquestador de Interfaz Local")

# Localizar la ruta absoluta
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

#servir archivos locales staticos (Tailwind CSS, JS, etc.)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

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
set_websocket_manager(manager)
app.include_router(api_router)

# --- ENDPOINTS HTTP ---
@app.get("/")
async def get_index():
    html_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>❌ Error: templates/index.html no encontrado</h1>", status_code=404)

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
