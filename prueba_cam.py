from picamera2 import Picamera2, Preview
import time

# 1. Inicializar la cámara
picam2 = Picamera2()
camera_config = picam2.create_preview_configuration()
picam2.configure(camera_config)

# 2. Iniciar la ventana de visualización en la pantalla
picam2.start_preview(Preview.QT)
picam2.start()

print("Cámara iniciada correctamente.")
print("Para salir del programa, presiona Ctrl + C en la terminal.")

# 3. Bucle infinito para mantener la cámara abierta
try:
    while True:
        # Aquí se queda el programa corriendo y mostrando el video
        time.sleep(1) 
except KeyboardInterrupt:
    # Cuando presionas Ctrl + C, el programa viene aquí y se cierra limpiamente
    print("\nCerrando la cámara...")
    picam2.stop_preview()
    picam2.stop()
