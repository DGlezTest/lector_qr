import qrcode

qr=qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
)

# Datos
qr.add_data('5567685453')
qr.make(fit=True)


img=qr.make_image(fill_color="black", back_color="white")  
img.save('qr.png')

