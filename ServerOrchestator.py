from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Orquestador de Interfaz Local")

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
            await connection.send_json(message)

manager = ConnectionManager()

@app.get("/")
async def get_index():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Mantiene la conexión abierta
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Endpoint crítico: Aquí es donde el script de hardware le habla al servidor
@app.post("/api/evento-local")
async def recibir_evento_hardware(evento: EventoLocal):
    await manager.send_json({
        "status": evento.status,
        "nombre": evento.nombre
    })
    return {"status": "notificado_a_pantalla"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)