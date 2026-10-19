import serial
import pynmea2  # You can install this library using: pip install pynmea2

def parse_gps_data(data):
    try:
        msg = pynmea2.parse(data)
        if isinstance(msg, pynmea2.types.talker.GGA):
            #print("Latitude: {0}, Longitude: {1}".format(msg.latitude, msg.longitude))
            return msg.latitude, msg.longitude
    except pynmea2.ParseError as e:
        print("Parse error: {}".format(e))
        return None

def get_coordinates():
    while True:
        serial_port = serial.Serial("/dev/ttyS0", baudrate=9600, timeout=1) 
        data = serial_port.readline().decode('utf-8',errors='replace')
        if data.startswith('$GPGGA'):
            latitude,longitude = parse_gps_data(data)
            lat = round(latitude,6)
            lng = round(longitude,6)
            return lat,lng

if __name__ == "__main__":
    
    try:
        while True:  
            lat,lng=get_coordinates()
            print(lat)
            print(lng)
    except KeyboardInterrupt:
        print("Exiting GPS module interface.")
    finally:
        serial_port.close()
