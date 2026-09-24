import os
import re
import json
import sqlite3
import httpx
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api")

API_BASE_URL = os.getenv("API_BASE_URL", "https://eventos.grupoteleurban.com").rstrip("/")
TURNSTILE_API_TOKEN = os.getenv(
    "TURNSTILE_API_TOKEN", 
    "0269ca762d1415c7db4b879ea9aef6dda0559bed3f7541ddee25996d7c72c2d6"
)
DEFAULT_EVENT_ID = os.getenv(
    "DEFAULT_EVENT_ID", 
    "48688d656de57df20054ded3047aae5b64c6151c"
)
DB_PATH = os.getenv("DB_PATH", "/home/pi/lector_qr/setup/accesos.db")

ws_manager_global = None

def set_websocket_manager(manager):
    global ws_manager_global
    ws_manager_global = manager

class QRPayload(BaseModel):
    data: str
    source_camera: str = "main_cam"

ERROR_TRANSLATIONS = {
    "invalid_credentials": "Error de autenticación de terminal",
    "invalid_action": "Acción no permitida",
    "ticket_not_found": "Boleto no registrado",
    "invitation_not_accepted": "Invitación no confirmada",
    "already_checked_in": "El boleto ya ingresó previamente",
    "not_checked_in": "Sin registro de entrada",
    "capacity_reached": "Aforo máximo alcanzado"
}

def parsear_contenido_qr(qr_raw: str):
    raw = qr_raw.strip()
    url_match = re.search(r'/events/([a-fA-F0-9]+)/tickets/([a-fA-F0-9]+)', raw)
    if url_match:
        return url_match.group(1), url_match.group(2)

    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            ev = payload.get("event_id") or payload.get("uri_event") or DEFAULT_EVENT_ID
            tk = payload.get("ticket_id") or payload.get("uri_guest") or payload.get("id")
            if tk:
                return str(ev), str(tk)
    except Exception:
        pass

    return DEFAULT_EVENT_ID, raw


def registrar_en_db(uri_guest: str, guest_name: str, status: str, tipo_movimiento: str, metadata: dict):
    try:
        zona = metadata.get("zona", "")
        area = metadata.get("area", "")
        mesa = metadata.get("mesa", "")
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS accesos_historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT,
                    nombre TEXT,
                    movimiento TEXT,
                    estado TEXT,
                    zona TEXT,
                    area TEXT,
                    mesa TEXT,
                    fecha_hora TEXT
                )
            """)
            cur.execute("""
                INSERT INTO accesos_historial 
                (ticket_id, nombre, movimiento, estado, zona, area, mesa, fecha_hora)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (uri_guest, guest_name, tipo_movimiento, status, zona, area, mesa, ahora))
            conn.commit()
    except Exception as e:
        print(f"[SQLite ⚠️] Error al guardar en base local: {e}", flush=True)


@router.post("/qr")
async def recibir_qr(payload: QRPayload):
    global ws_manager_global

    print("\n================ [QR DETECTADO] ================", flush=True)
    print(f">> RAW DATA: '{payload.data}'", flush=True)

    uri_event, uri_guest = parsear_contenido_qr(payload.data)
    print(f">> PARSED: Evento='{uri_event}' | Ticket='{uri_guest}'", flush=True)

    if not uri_guest:
        msg_error = "Lectura de código QR inválida"
        print(f">> ERROR: No se pudo extraer uri_guest de: {payload.data}", flush=True)

        if ws_manager_global:
            try:
                await ws_manager_global.broadcast({
                    "status": "denied",
                    "nombre": "Acceso Denegado",
                    "message": msg_error
                })
            except Exception as e:
                print(f"[WebSocket ⚠️] {e}", flush=True)
        return {"status": "denied", "action": "lock", "message": msg_error}

    url = f"{API_BASE_URL}/api/access/events/{uri_event}/tickets/{uri_guest}"
    print(f">> LLAMANDO API: {url}", flush=True)
    headers = {
        "Authorization": f"Bearer {TURNSTILE_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    body = {"action": "check_in"}

    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
            response = await client.post(url, headers=headers, json=body)
            data_resp = response.json()
            print(f">> HTTP STATUS: {response.status_code}", flush=True)
            print(f">> RESPUESTA API: {data_resp}", flush=True)
            print("================================================\n", flush=True)
    except httpx.RequestError as exc:
        print(f"[API ⚠️] Error de red con servidor central: {exc}", flush=True)
        msg_red = "Error de conexión con el servidor"
        if ws_manager_global:
            try:
                await ws_manager_global.broadcast({
                    "status": "denied",
                    "nombre": "Fallo de Red",
                    "message": msg_red
                })
            except Exception as e:
                print(f"[WebSocket ⚠️] {e}", flush=True)
        return {"status": "denied", "action": "lock", "message": msg_red}
    except Exception as e:
        print(f"[API ⚠️] Error procesando JSON de respuesta: {e}", flush=True)
        return {"status": "denied", "action": "lock", "message": "Error interno de validación"}

    allowed = data_resp.get("allowed", False)
    code = data_resp.get("code", "unknown")
    info_invitado = data_resp.get("data") or {}
    meta = info_invitado.get("metadata") or {}

    if not allowed:
        motivo_error = ERROR_TRANSLATIONS.get(code, data_resp.get("message", "Acceso denegado"))
        registrar_en_db(uri_guest, "Desconocido", code, "RECHAZO", meta)

        if ws_manager_global:
            try:
                await ws_manager_global.broadcast({
                    "status": "denied",
                    "nombre": "Acceso Denegado",
                    "name": "Acceso Denegado",
                    "message": motivo_error,
                    "mensaje": motivo_error
                })
            except Exception as e:
                print(f"[WebSocket ⚠️] {e}", flush=True)

        return {
            "status": "denied",
            "action": "lock",
            "code": code,
            "message": motivo_error
        }

    # Acceso Aprobado: Extraer datos del invitado incluyendo el COLOR de la mesa
    guest_name = info_invitado.get("guest_name") or meta.get("name") or "Invitado"
    zona = meta.get("zona", "")
    mesa = meta.get("mesa", "")
    color = meta.get("color", "") # <- Extrae "NEGRO", "AZUL", "ROJO", etc.
    
    if code == "checked_out":
        tipo_movimiento = "SALIDA"
        mensaje_pantalla = "¡Hasta pronto! Gracias por acompañarnos"
    else:
        tipo_movimiento = "ENTRADA"
        ubicacion = f"Mesa {mesa}" if mesa else (f"Zona {zona}" if zona else "26 Aniversario")
        mensaje_pantalla = f"{ubicacion} · Por favor pase adelante"

    registrar_en_db(uri_guest, guest_name, code, tipo_movimiento, meta)

    if ws_manager_global:
        try:
            payload_ws = {
                "status": "success",
                "nombre": guest_name,
                "name": guest_name,
                "invitado": guest_name,
                "zona": zona,
                "mesa": mesa,
                "color": color, # <- Se envía al HTML
                "tipo_movimiento": tipo_movimiento,
                "message": mensaje_pantalla,
                "mensaje": mensaje_pantalla
            }
            if hasattr(ws_manager_global, "broadcast"):
                await ws_manager_global.broadcast(payload_ws)
            elif hasattr(ws_manager_global, "send_json"):
                await ws_manager_global.send_json(payload_ws)
        except Exception as e:
            print(f"[WebSocket ⚠️] Error al enviar WebSocket: {e}", flush=True)

    return {
        "status": "success",
        "action": "unlock",
        "name": guest_name,
        "mesa": mesa,
        "color": color,
        "message": mensaje_pantalla
    }
