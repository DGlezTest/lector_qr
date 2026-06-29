from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["API Torniquete"])

class QRPayload(BaseModel):
    data: str
    source_camera: str
    
    ws_manager = None  
    
def websocket_manager(manager):
    global es_manager
    ws_manager = manager
    
    
@router.post("/qr")
async def recibir_qr(payload: QRPayload):
    print(f"[API] QR recibido: {payload.data} desde {payload.source_camera}")
    
    if not ws_manager:
        raise HTTPException(status_code=500, detail="WebSocket manager no inicializado")
    
    if "RECHAZO" in qr.data.upper() or "ERROR" in qr.data.upper():
        if ws_manager:
            await ws_manager.send_json({
                "status": "denied",
                "nombre": "QR Invalido o Ya Utilizado"
                })
        return {"status": "denied","action":"Lock", "message": "QR Invalido o Ya Utilizado"}
    
    if ws_manager:
        await ws_manager.send_json({
            "status": "success",
            "nombre": nombre_invitado
        })
        
    return {"status": "success", "action":"Unlock", "message": f"Bienvenido {nombre_invitado}"}
        