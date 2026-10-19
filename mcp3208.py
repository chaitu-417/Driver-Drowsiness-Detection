# First install spidev if not installed:
# Enable SPI (sudo raspi-config)
# $ sudo apt-get update 
# $ sudo apt-get upgrade
# $ sudo apt-get install python3-dev python3-pip
# $ sudo pip3 install spidev

from spidev import SpiDev
import time

class MCP3208:
    def __init__(self, bus=0, device=0):
        self.bus, self.device = bus, device
        self.spi = SpiDev()
        self.open()
        self.spi.max_speed_hz = 1000000  # 1MHz

    def open(self):
        self.spi.open(self.bus, self.device)
        self.spi.max_speed_hz = 1000000  # 1MHz
    
    def read(self, channel=0):
        """
        Reads data from the specified ADC channel (0–7).
        MCP3208 is 12-bit → values 0–4095.
        """
        if channel < 0 or channel > 7:
            raise ValueError("MCP3208 channel must be 0-7")

        # Build command byte sequence
        # 1st byte: Start bit (0b00000110 for single-ended)
        # 2nd byte: (channel << 6)
        # 3rd byte: don't care, just 0
        cmd = [6 | (channel >> 2), (channel & 3) << 6, 0]
        
        # Perform SPI transaction
        adc = self.spi.xfer2(cmd)
        
        # Combine data (12-bit result)
        result = ((adc[1] & 0x0F) << 8) | adc[2]
        return result

    def close(self):
        self.spi.close()


if __name__ == "__main__":
    adc = MCP3208()
    try:
        while True:
            x = adc.read(1)  # Read channel 0
            y = adc.read(2)  # Read channel 1
            
            print("x:", x)
            time.sleep(1)
            print("y:", y)
            time.sleep(1)
    except KeyboardInterrupt:
        adc.close()
        print("MCP3208 closed.")
