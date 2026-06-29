from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["API Torniquete"])

# --- 1. MODELO PURO Y LIMPIO ---
class QRPayload(BaseModel):
    data: str
    source_camera: str

# --- 2. VARIABLE GLOBAL CONTROLADA (Alineada 100% a la izquierda) ---
ws_manager_global = None  

def set_websocket_manager(manager):
    """Esta función conecta el manager del servidor con este router"""
    global ws_manager_global
    ws_manager_global = manager
    print("[API] ✅ Administrador de WebSockets enlazado al router de rutas.")

# --- 3. ENDPOINT DE PROCESAMIENTO ---
@router.post("/qr")
async def recibir_qr(payload: QRPayload):
    print(f"[API] 🎯 QR recibido en la ruta: '{payload.data}' desde cámara '{payload.source_camera}'")
    
    global ws_manager_global
    
    # Validamos de manera segura si la pantalla está lista y escuchando
    if ws_manager_global is None:
        print("[API] ⚠️ Alerta: Intentando procesar un QR pero la pantalla no está conectada por WS.")

    # --- CASO A: DETECTAR INTENTOS DE ERROR O RECHAZO ---
    if "RECHAZO" in payload.data.upper() or "ERROR" in payload.data.upper():
        if ws_manager_global:
            await ws_manager_global.send_json({
                "status": "denied",
                "nombre": "Boleto Inválido o Ya Usado"
            })
        return {
            "status": "denied",
            "action": "lock", 
            "message": "Acceso denegado: Código inválido o duplicado"
        }
    
    # --- CASO B: DETECTAR EVENTO EXITOSO (Luis David Gonzalez o Pasajero) ---
    if "DAVID" in payload.data.upper():
        nombre_invitado = "Luis David Gonzalez"
    else:
        nombre_invitado = "Pasajero Local"
    
    # Notificamos de forma asíncrona a la pantalla para que se pinte de verde
    if ws_manager_global:
        await ws_manager_global.send_json({
            "status": "success",
            "nombre": nombre_invitado
        })
        
    # Le respondemos al hardware_orchestrator para que proceda con los relés de apertura
    return {
        "status": "success", 
        "action": "unlock", 
        "message": f"Bienvenido {nombre_invitado}"
    }  