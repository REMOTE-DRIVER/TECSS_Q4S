import threading, time, sys, logging
from paho.mqtt import client as mqtt
from pathlib import Path

def load_password(file_name: str = "password.txt") -> str:
    path = Path(__file__).with_name(file_name)   # mismo directorio que el .py
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logging.error("No encuentro %s; saliendo", path)
        sys.exit(1)

password = load_password()  # Cargar la contraseña desde el archivo

STOP = threading.Event()

def on_connect(cli, _u, _f, rc):
    if rc == 0:
        #cli.subscribe("RD/#")
        cli.subscribe("RD/7777/#")
    else:
        print("CONNACK rc", rc)

def on_message(_cli, _u, msg):
    print(msg.topic, msg.payload.decode())

cli = mqtt.Client(protocol=mqtt.MQTTv311)
cli.username_pw_set("nokiatecss", password)
cli.on_connect = on_connect
cli.on_message = on_message
cli.connect("remotedriver.dit.upm.es", 41883, keepalive=60)
cli.loop_start()

try:
    while not STOP.is_set():
        time.sleep(1)
except KeyboardInterrupt:
    STOP.set()
    cli.loop_stop()
    cli.disconnect()
    sys.exit(0)
