import json
from fastapi import APIRouter
from pydantic import BaseModel
from app.database import init_db, procesar_acceso_db

router = APIRouter(prefix="/api")

# Inicializar BD al cargar el router
init_db()

ws_manager_global = None

def set_websocket_manager(manager):
    global ws_manager_global
    ws_manager_global = manager

class QRPayload(BaseModel):
    data: str
    source_camera: str = "webcam"

@router.post("/qr")
async def recibir_qr(payload: QRPayload):
    contenido = payload.data.strip()
    global ws_manager_global

    # 1. Caso Acceso Denegado
    if "RECHAZO" in contenido.upper() or "ERROR" in contenido.upper():
        if ws_manager_global:
            try:
                await ws_manager_global.broadcast({
                    "status": "denied",
                    "nombre": "Acceso Denegado",
                    "name": "Acceso Denegado",
                    "message": "Boleto Inválido o Duplicado",
                    "mensaje": "Boleto Inválido o Duplicado"
                })
            except Exception as e:
                print(f"[API ⚠️] Error en broadcast WebSocket: {e}")

        return {"status": "denied", "action": "lock", "message": "Acceso Denegado"}

    # 2. Extracción de Identificador y Nombre
    qr_id = contenido
    nombre_invitado = "Invitado"

    try:
        datos_json = json.loads(contenido)
        if isinstance(datos_json, dict):
            nombre_invitado = str(datos_json.get("nombre", datos_json.get("n", datos_json.get("name", "Invitado")))).strip()
            qr_id = str(datos_json.get("id", nombre_invitado))
    except Exception:
        if contenido.startswith("NOM:"):
            nombre_invitado = contenido.replace("NOM:", "").strip()
            qr_id = nombre_invitado
        elif "DAVID" in contenido.upper():
            nombre_invitado = "Luis David Gonzalez"
            qr_id = "DAVID"
        elif len(contenido) > 0:
            nombre_invitado = contenido
            qr_id = contenido

    # 3. Procesar estado en SQLite
    try:
        tipo_movimiento, nuevo_estado = procesar_acceso_db(qr_id, nombre_invitado)
    except Exception as e:
        print(f"[API ⚠️] Error en base de datos SQLite: {e}")
        tipo_movimiento = "ENTRADA"
        nuevo_estado = "ADENTRO"

    # 4. Definir mensaje_pantalla ANTES de armar el payload
    if tipo_movimiento == "ENTRADA":
        mensaje_pantalla = "Disfruta el 26 Aniversario · Por favor pase adelante"
    else:
        mensaje_pantalla = "Gracias por acompañarnos en el 26 Aniversario · ¡Hasta pronto!"

    # 5. Notificación por WebSocket a la pantalla
    if ws_manager_global:
        try:
            payload_ws = {
                "status": "success",
                "nombre": nombre_invitado,
                "name": nombre_invitado,
                "invitado": nombre_invitado,
                "user": nombre_invitado,
                "guest": nombre_invitado,
                "persona": nombre_invitado,
                "tipo_movimiento": tipo_movimiento,
                "estado": nuevo_estado,
                "message": mensaje_pantalla,
                "mensaje": mensaje_pantalla
            }
            if hasattr(ws_manager_global, "broadcast"):
                await ws_manager_global.broadcast(payload_ws)
            elif hasattr(ws_manager_global, "send_json"):
                await ws_manager_global.send_json(payload_ws)
        except Exception as e:
            print(f"[API ⚠️] Error al enviar WebSocket: {e}")

    # 6. Respuesta HTTP 200 al orquestador de hardware
    return {
        "status": "success",
        "action": "unlock",
        "name": nombre_invitado,
        "movimiento": tipo_movimiento,
        "estado": nuevo_estado,
        "message": mensaje_pantalla
    }
