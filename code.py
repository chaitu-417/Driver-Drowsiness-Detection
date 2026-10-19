import threading
from scipy.spatial import distance
from imutils import face_utils
import imutils
import dlib
import cv2
import numpy as np
import time
import serial
import pygame
import RPi.GPIO as GPIO
from mcp3208 import MCP3208
import gps_module
import pyttsx3 
# ================= GPIO SETUP (ONLY ONCE) =================
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
DROWSY_FRAMES = 20      # ~0.8 sec at 25 FPS
FRAME_COUNT = 0
RELAY_PIN = 15
TRIG = 11
ECHO = 13

GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

GPIO.output(RELAY_PIN, GPIO.HIGH)
GPIO.output(TRIG, GPIO.LOW)
tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 160)
tts_engine.setProperty('volume', 1.0)

def speak_alert():
    tts_engine.say("Warning! Drowsiness detected. Please stay alert.")
    tts_engine.runAndWait()

# ================= PYGAME =================
pygame.mixer.init()
pygame.mixer.music.load("alert.wav")


# ================= SERIAL (GSM) =================
ser = serial.Serial("/dev/ttyS0", 9600, timeout=1)
phone_number = "+916300369899"

# ================= CAMERA & DLIB =================
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("❌ Camera not detected")
    exit()

predictor_path = "shape_predictor_68_face_landmarks.dat"
detect = dlib.get_frontal_face_detector()
predict = dlib.shape_predictor(predictor_path)

(lStart, lEnd) = face_utils.FACIAL_LANDMARKS_68_IDXS["left_eye"]
(rStart, rEnd) = face_utils.FACIAL_LANDMARKS_68_IDXS["right_eye"]

# ================= THRESHOLDS =================
EAR_THRESH = 0.28
YAWN_THRESH = 30

# ================= SHARED DATA =================
sensor_data = {
    "x": 0,
    "y": 0,
    "distance": 1000,
    "lat": 0.0,
    "lng": 0.0
}
lock = threading.Lock()

# ================= ALERT CONTROL (ADDED) =================
drowsy_active = False
last_alert_time = 0
ALERT_COOLDOWN = 5  # seconds

# ================= ULTRASONIC =================
def measure_distance():
    GPIO.output(TRIG, GPIO.LOW)
    time.sleep(0.002)
    GPIO.output(TRIG, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG, GPIO.LOW)

    start = time.time()
    while GPIO.input(ECHO) == 0:
        if time.time() - start > 0.05:
            return 1000

    start = time.time()
    while GPIO.input(ECHO) == 1:
        if time.time() - start > 0.05:
            return 1000

    duration = time.time() - start
    return round(duration * 17150, 2)

# ================= SMS =================
def send_text_message(msg, lat, lng):
    link = f"https://www.google.com/maps?q={lat},{lng}"
    full_msg = f"{msg}\nLocation:\n{link}"
    try:
        ser.write(b"AT\r\n")
        time.sleep(1)
        ser.write(b"AT+CMGF=1\r")
        time.sleep(1)
        ser.write(f'AT+CMGS="{phone_number}"\r'.encode())
        time.sleep(1)
        ser.write((full_msg + chr(26)).encode())
        print("✅ SMS Sent")
    except Exception as e:
        print("❌ SMS Error:", e)

# ================= SENSOR THREAD =================
def monitor_sensors():
    adc = MCP3208()
    while True:
        try:
            x = adc.read(1)
            y = adc.read(2)
            dist = measure_distance()
            lat, lng = gps_module.get_coordinates()

            with lock:
                sensor_data.update({
                    "x": x,
                    "y": y,
                    "distance": dist,
                    "lat": lat,
                    "lng": lng
                })
            print(f"📍 GPS: {lat:.6f}, {lng:.6f}")
            print(f"📊 MEMS: X={x} Y={y} | Distance={dist}cm")

            if dist < 10:
                print("Obstcale detected")
                send_text_message(f"Obstacle at {dist}cm", lat, lng)
                GPIO.output(RELAY_PIN, GPIO.LOW)
                time.sleep(2)
            else:
                GPIO.output(RELAY_PIN, GPIO.HIGH)

            if x < 1200 or x > 1500:
                print("Mems/Tilt detected")
                send_text_message("MEMS Tilt Detected!", lat, lng)
                GPIO.output(RELAY_PIN, GPIO.LOW)
                time.sleep(2)
            else:
                GPIO.output(RELAY_PIN, GPIO.HIGH)

        except Exception as e:
            print("❌ Sensor Thread Error:", e)
            time.sleep(2)

# ================= DROWSINESS FUNCTIONS =================
def euclidean_dist(a, b):
    return np.linalg.norm(a - b)

def eye_aspect_ratio(eye):
    A = euclidean_dist(eye[1], eye[5])
    B = euclidean_dist(eye[2], eye[4])
    C = euclidean_dist(eye[0], eye[3])
    return (A + B) / (2.0 * C)

def lip_distance(shape):
    top = np.concatenate((shape[50:53], shape[61:64]))
    low = np.concatenate((shape[56:59], shape[65:68]))
    return abs(np.mean(top, axis=0)[1] - np.mean(low, axis=0)[1])

# ================= MAIN =================
try:
    print("🚀 System Started")
    threading.Thread(target=monitor_sensors, daemon=True).start()

    while True:
        ret, frame = cap.read()
        frame = imutils.resize(frame, width=500)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        subjects = detect(gray, 0)

        current_time = time.time()

        for subject in subjects:
            shape = face_utils.shape_to_np(predict(gray, subject))
            leftEye = shape[lStart:lEnd]
            rightEye = shape[rStart:rEnd]

            ear = (eye_aspect_ratio(leftEye) + eye_aspect_ratio(rightEye)) / 2.0
            yawn = lip_distance(shape)

            if ear < EAR_THRESH or yawn > YAWN_THRESH:
                FRAME_COUNT += 1
            else:
                FRAME_COUNT = 0

            if FRAME_COUNT >= DROWSY_FRAMES:
                print("Drowsiness detected")
                cv2.putText(frame, "ALERT: DROWSINESS DETECTED!", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                if not drowsy_active:
                    pygame.mixer.music.play(-1)
                    GPIO.output(RELAY_PIN, GPIO.LOW)
                    time.sleep(4)
                    '''speak_alert()'''

                    with lock:
                        lat, lng = sensor_data["lat"], sensor_data["lng"]
                        send_text_message("🚨 Drowsiness Detected!", lat, lng)

                    drowsy_active = True
                    last_alert_time = current_time


            else:
                if drowsy_active and (current_time - last_alert_time > ALERT_COOLDOWN):
                    pygame.mixer.music.stop()
                    GPIO.output(RELAY_PIN, GPIO.HIGH)
                    drowsy_active = False

            cv2.drawContours(frame, [cv2.convexHull(leftEye)], -1, (0,255,0), 1)
            cv2.drawContours(frame, [cv2.convexHull(rightEye)], -1, (0,255,0), 1)
            cv2.drawContours(frame, [shape[48:60]], -1, (0,255,0), 1)

        cv2.imshow("Driver Monitor", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

except KeyboardInterrupt:
    print("🔌 Interrupted")

finally:
    pygame.mixer.music.stop()
    cap.release()
    cv2.destroyAllWindows()
    GPIO.cleanup()
    print("✅ System Cleaned Up")
