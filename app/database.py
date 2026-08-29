import sqlite3
import os
from datetime import datetime

DB_PATH = "/home/pi/lector_qr/setup/accesos.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabla de estado actual de cada usuario/QR
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios_estado (
        qr_id TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        estado_actual TEXT DEFAULT 'AFUERA', -- 'AFUERA' o 'ADENTRO'
        ultimo_movimiento DATETIME
    )
    """)
    
    # Tabla de bitácora histórica
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registro_accesos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id TEXT NOT NULL,
        nombre TEXT NOT NULL,
        tipo_movimiento TEXT NOT NULL, -- 'ENTRADA' o 'SALIDA'
        timestamp DATETIME NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def procesar_acceso_db(qr_id: str, nombre: str):
    """
    Alterna el estado del usuario:
    - Si estaba AFUERA -> Pasa a ADENTRO (Registra ENTRADA)
    - Si estaba ADENTRO -> Pasa a AFUERA (Registra SALIDA)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Obtener estado actual
    cursor.execute("SELECT estado_actual FROM usuarios_estado WHERE qr_id = ?", (qr_id,))
    row = cursor.fetchone()

    if row is None:
        nuevo_estado = "ADENTRO"
        tipo_movimiento = "ENTRADA"
        cursor.execute("""
            INSERT INTO usuarios_estado (qr_id, nombre, estado_actual, ultimo_movimiento)
            VALUES (?, ?, ?, ?)
        """, (qr_id, nombre, nuevo_estado, ahora))
    else:
        estado_previo = row[0]
        if estado_previo == "ADENTRO":
            nuevo_estado = "AFUERA"
            tipo_movimiento = "SALIDA"
        else:
            nuevo_estado = "ADENTRO"
            tipo_movimiento = "ENTRADA"

        cursor.execute("""
            UPDATE usuarios_estado 
            SET estado_actual = ?, ultimo_movimiento = ?, nombre = ?
            WHERE qr_id = ?
        """, (nuevo_estado, ahora, nombre, qr_id))

    # 2. Guardar en el historial
    cursor.execute("""
        INSERT INTO registro_accesos (qr_id, nombre, tipo_movimiento, timestamp)
        VALUES (?, ?, ?, ?)
    """, (qr_id, nombre, tipo_movimiento, ahora))

    conn.commit()
    conn.close()

    return tipo_movimiento, nuevo_estado
