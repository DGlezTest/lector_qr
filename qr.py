import json
import qrcode

# 1. Creamos la estructura de datos
datos_invitado = {
    "nombre": "Estrella mi amor ya no te enojes",
    "tipo": "VIP",
    "mesa": 1
}

# 2. Convertimos el diccionario a cadena JSON
contenido_qr = json.dumps(datos_invitado, ensure_ascii=False)

# 3. Generamos el código QR
qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
)

qr.add_data(contenido_qr)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")
img.save("qr_estrella.png")

print(f"QR generado con contenido: {contenido_qr}")
