import smbus2

class RelayHAT:
    def __init__(self, bus_num: int = 1, address: int = 0x10):
        self.bus_num = bus_num
        self.address = address
        # En el PCF8574: 0xFF = todos los bits en 1 (todos los relés apagados)
        self.state = 0xFF
        self.bus = smbus2.SMBus(self.bus_num)
        self.apagar_todos()

    def _escribir_estado(self):
        try:
            self.bus.write_byte(self.address, self.state)
        except Exception as e:
            print(f"[❌ I2C ERROR] No se pudo comunicar con el HAT en {hex(self.address)}: {e}")

    def encender_rele(self, canal: int):
        """Activa el relé (canal 1 a 4). Lógica activa en LOW (bit en 0)."""
        if 1 <= canal <= 4:
            self.state &= ~(1 << (canal - 1))
            self._escribir_estado()

    def apagar_rele(self, canal: int):
        """Desactiva el relé (canal 1 a 4). Bit en 1."""
        if 1 <= canal <= 4:
            self.state |= (1 << (canal - 1))
            self._escribir_estado()

    def apagar_todos(self):
        """Apaga los 4 relés."""
        self.state = 0xFF
        self._escribir_estado()
