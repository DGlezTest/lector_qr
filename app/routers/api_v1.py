import json
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api")

ws_manager_global = None

def set_websocket_manager(manager):
    """Conecta el ConnectionManager de server_orchestrator con este router"""
    global ws_manager_global
    ws_manager_global = manager
    print("[API] ✅ Administrador de WebSockets enlazado al router de rutas.")

class QRPayload(BaseModel):
    data: str
    source_camera: str = "webcam"

@router.post("/qr")
async def recibir_qr(payload: QRPayload):
    contenido = payload.data.strip()
    print(f"[API] 🎯 QR recibido: '{contenido}' desde '{payload.source_camera}'")

    global ws_manager_global

    # 1. CASO RECHAZO / ERROR
    if "RECHAZO" in contenido.upper() or "ERROR" in contenido.upper():
        if ws_manager_global:
            await ws_manager_global.broadcast({
                "status": "denied",
                "nombre": "Boleto Inválido o Duplicado",
                "message": "Acceso Denegado"
            })
        return {
            "status": "denied",
            "action": "lock",
            "message": "Acceso denegado: Código inválido o duplicado"
        }

    # 2. CASO ACCESO EXITOSO
    nombre_invitado = "Pasajero Local"
    try:
        datos_json = json.loads(contenido)
        if isinstance(datos_json, dict) and "nombre" in datos_json:
            nombre_invitado = str(datos_json["nombre"]).strip()
    except Exception:
        if "DAVID" in contenido.upper():
            nombre_invitado = "Luis David Gonzalez"
        elif len(contenido) > 0:
            nombre_invitado = contenido

    # Notificar a la pantalla mediante broadcast
    if ws_manager_global:
        await ws_manager_global.broadcast({
            "status": "success",
            "nombre": nombre_invitado,
            "message": "Disfruta el 26 Aniversario · Por favor pase adelante"
        })

    # Responder al hardware_orchestrator para accionar los relés I2C
    return {
        "status": "success",
        "action": "unlock",
        "name": nombre_invitado,
        "message": f"Bienvenido {nombre_invitado}"
    }
