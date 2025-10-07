from __future__ import annotations

import logging
import signal
import sys, os
import threading
import time
from typing import Final
from pathlib import Path
import configparser

import q4s_lite
from paho.mqtt import client as mqtt
from paho.mqtt.enums import CallbackAPIVersion


DEFAULTS = {
    'GENERAL': {
        'VEHICLE_ID': "0001",
        'PACKETS_PER_SECOND': 30,
        'PACKET_LOSS_PRECISSION': 100,
        'LATENCY_ALERT': 150,
        'PACKET_LOSS_ALERT': 0.02,
        'NO_INIT': False,
        'OFFSET':0,
        'MEASURES_COMBINATION_STRATEGY':0
    },
    'NETWORK': {
        'server_address': '127.0.0.1',
        'server_port': 20001,
        'client_address': '127.0.0.1',
        'client_port': 20002,
    },
    'ACTUATOR':{
        'actuator_address':'127.0.0.1',
        'actuator_port':'8889',
        'insignificant_loses': 0.01,
        'fuentes': 1,
        'TAM_POR_FUENTE':250000
    },
    'PUBLICATOR':{
        'PUBLICATION_TIME': 3,
        'PUBLICATION_ALERT_TIME': 1
    }
}
if len(sys.argv)==2:
    config_file = sys.argv[1]
else:
    config_file = "q4s_lite_config.ini"

if not (os.path.exists(config_file)):
    print("\n[Q4S Lite CONFIG] Config file not found using default configuration values\n")

config = configparser.ConfigParser()

config.read_dict(DEFAULTS)  # cargar valores por defecto primero
config.read(config_file)
# Acceder y convertir tipos
general = config['GENERAL']
network = config['NETWORK']
actuator = config['ACTUATOR']
publicator = config['PUBLICATOR']

#server_address, server_port = q4s_lite.server_address, q4s_lite.server_port
#client_address, client_port = q4s_lite.client_address, q4s_lite.client_port
#PUBLICATION_TIME = 3 #segundos
#PUBLICATION_ALERT_TIME = 1 #segundo
server_address= network.get('server_address')
server_port= network.getint('server_port')
client_address= network.get('client_address')
client_port= network.getint('client_port')
PUBLICATION_TIME = publicator.getint('PUBLICATION_TIME')
#PUBLICATION_ALERT_TIME = publicator.getint('PUBLICATION_ALERT_TIME')


def load_password(file_name: str = "password.txt") -> str:
    path = Path(__file__).with_name(file_name)   # mismo directorio que el .py
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logging.error("No encuentro %s; saliendo", path)
        sys.exit(1)

#LATENCY_ALERT: Final[int] = q4s_lite.LATENCY_ALERT
#PACKET_LOSS_ALERT: Final[float] = q4s_lite.PACKET_LOSS_ALERT
LATENCY_ALERT= general.getint('LATENCY_ALERT')
PACKET_LOSS_ALERT= general.getfloat('PACKET_LOSS_ALERT')

BROKER_HOST: Final[str] = "remotedriver.dit.upm.es"
BROKER_PORT: Final[int] = 41883
USERNAME: Final[str] = "nokiatecss"
PASSWORD: Final[str] = load_password()  

#PUBLICATION_TIME: Final[int] = 3  # segundos

print() # Para separar la salida del logger de la salida estándar
logger = logging.getLogger("q4s_publicator")
logger.setLevel(logging.INFO)
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_console_hdl = logging.StreamHandler(sys.stderr)  # stderr para separar de stdout
_console_hdl.setFormatter(_formatter)
logger.addHandler(_console_hdl)
logger.addHandler(logging.FileHandler("publicador_mqtt.log", mode="w", encoding="utf-8"))


def encode_identifier(identifier: str) -> int:
    if len(identifier) != 4:
        raise ValueError("El identificador debe tener exactamente 4 caracteres")
    return int.from_bytes(identifier.encode(), byteorder="big")


def decode_identifier(number: int) -> str:
    return number.to_bytes(4, byteorder="big").decode()


def compute_alert_code(q4s_node: "q4s_lite.q4s_lite_node") -> int:
    # Calcula el código de alerta basado en los estados de conexión, latencia y pérdida de paquetes.
    # Los bits se asignan de la siguiente manera:
    # bit0: pérdida de paquetes (1 si la pérdida de paquetes combinada supera el umbral)
    # bit1: latencia (1 si la latencia combinada supera el umbral)
    # bit2: conexión (1 si hay errores de conexión)
    # Resultado:
    # 0: sin alertas
    # 1: alerta de pérdida de paquetes
    # 2: alerta de latencia
    # 3: alerta de latencia y pérdida de paquetes
    # 4: alerta de conexión
    # 5: alerta de conexión y pérdida de paquetes
    # 6: alerta de conexión y latencia
    # 7: alerta de conexión, latencia y pérdida de paquetes
    connection_alert = int(q4s_node.connection_errors > 0)
    latency_alert = int(q4s_node.latency_combined >= LATENCY_ALERT)
    loss_alert = int(q4s_node.packet_loss_combined >= PACKET_LOSS_ALERT)
    return (connection_alert << 2) | (latency_alert << 1) | loss_alert


def compute_explanation(alert_code: int) -> str:
    if alert_code == 0:
        return "sin alertas"
    explanations = []
    if alert_code & 1:  # bit0: pérdida de paquetes
        explanations.append("pl")
    if alert_code & 2:  # bit1: latencia
        explanations.append("lat")
    if alert_code & 4:  # bit2: conexión
        explanations.append("conn")
    return ",".join(explanations)


def compute_alert_level(alert_code: int) -> int:
    # baja --> 0,1,2,3 media --> 4,5,6 alta --> 7, recovery
    # nivel (0-3): 0=baja, 1=media, 2=alta, 3=recovery
    if alert_code in (0, 1, 2, 3):
        return 0
    elif alert_code in (4, 5, 6):
        return 1
    elif alert_code == 7:
        return 2
    else:
        raise ValueError(f"Código de alerta desconocido: {alert_code}. Debe ser 0-7.")


def measures_publisher(q4s_node: "q4s_lite.q4s_lite_node", mqttc: mqtt.Client,
                       connected_evt: threading.Event, running_evt: threading.Event) -> None:
    topic = f"RD/{decode_identifier(q4s_node.flow_id)}/QoS_status"
    while running_evt.is_set():
        if not connected_evt.wait(timeout=1):
            continue
        payload = (
            f"lat={q4s_node.latency_combined:.10f};"
            f"jit={q4s_node.jitter_combined:.3f};"
            f"pl={q4s_node.packet_loss_combined:.3f};"
            f"conn={q4s_node.connection_errors}"
        )
        mqttc.publish(topic, payload, qos=1, retain=False)
        print() 
        logger.debug("[PUB] %s -> %s", topic, payload)

        sleep_left = PUBLICATION_TIME
        while running_evt.is_set() and sleep_left > 0:
            time.sleep(min(0.5, sleep_left))
            sleep_left -= 0.5
        logger.info("[PUB] %s -> %s", topic, payload)


def alerts_publisher(q4s_node: "q4s_lite.q4s_lite_node", mqttc: mqtt.Client,
                     connected_evt: threading.Event, running_evt: threading.Event) -> None:
    topic = f"RD/{decode_identifier(q4s_node.flow_id)}/QoS_alert"
    while running_evt.is_set():
        if not q4s_node.event_publicator.wait(timeout=1):
            continue
        q4s_node.event_publicator.clear()
        if not running_evt.is_set():
            break
        if not connected_evt.wait(timeout=5):
            print() 
            logger.warning("Alerta ignorada: sin conexión MQTT")
            continue
        
        alert_code = compute_alert_code(q4s_node)
        if q4s_node.state[0]=="alert":  # Si es una alerta
            alert_level = compute_alert_level(alert_code)
            explanation = compute_explanation(alert_code)  # Explicación de la alerta
        elif q4s_node.state[0]=="normal":  # Si te despiertan y el estado es normal, es un recovery
            alert_level = 3  # recovery
            explanation = "recovery"
        payload = (
            f"level={alert_level};"
            f"code={alert_code};"
            f"explicación={explanation};"
            f"lat={q4s_node.latency_combined:.10f};"
            f"jit={q4s_node.jitter_combined:.3f};"
            f"pl={q4s_node.packet_loss_combined:.3f};"
            f"conn={q4s_node.connection_errors}"
        )
        mqttc.publish(topic, payload, qos=1, retain=False)
        print() 
        logger.info("[ALERT] %s -> %s", topic, payload)


def on_connect(client: mqtt.Client, userdata, flags, reason_code, properties):
    # MQTT v5 ⇒ reason_code es objeto ReasonCodes.  En v3.1.1 sería un int.
    rc_val = getattr(reason_code, "value", reason_code)      # int 0-255
    rc_name = getattr(reason_code, "getName", lambda: rc_val)()

    print()  # rompe la línea viva de medidas

    if rc_val == 0:
        logger.info("Conectado a %s:%s (RC=%s)", BROKER_HOST, BROKER_PORT, rc_name)
        _CONNECTED_EVENT.set()

        # Publica 'online' sólo cuando la sesión ya está operativa
        topic = f"RD/{client._client_id.decode()}/status"
        client.publish(topic, "online", qos=1, retain=False)
    else:
        logger.error("Fallo al conectar (RC=%s)", rc_name)
        _CONNECTED_EVENT.clear()


def on_disconnect(client: mqtt.Client, _userdata, _flags, reason_code, _properties):
    print() 
    logger.warning("Desconectado (reason=%s)", reason_code)
    _CONNECTED_EVENT.clear()

def on_publish(client, userdata, mid, reason_code, properties):
    # MQTT v5 → reason_code es objeto ReasonCodes.  Si fuera v3.1.1, es int.
    code_val = getattr(reason_code, "value", reason_code)  # int 0-255

    if code_val >= 128:   # sólo errores “negativos”
        logger.error("PUB mid=%s rechazado (RC=%s – %s)",
                     mid, code_val, reason_code.getName())
    else:
        logger.debug("PUB mid=%s RC=%s – %s",
                     mid, code_val, reason_code.getName())


_RUNNING_EVENT = threading.Event()
_CONNECTED_EVENT = threading.Event()


def graceful_exit(_: int | None = None, __: object | None = None):
    print() 
    logger.info("Parando publicador…")
    _RUNNING_EVENT.clear()
    try:
        if _CONNECTED_EVENT.is_set():
            _MQTT_CLIENT.publish(f"RD/{_MQTT_CLIENT._client_id.decode()}/status", "offline", qos=1, retain=False)
            time.sleep(0.2)
        _MQTT_CLIENT.loop_stop()
        _MQTT_CLIENT.disconnect()
    finally:
        _Q4S_NODE.measuring = False
        _Q4S_NODE.running = False
        print() 
        logger.info("Publicador detenido. Bye!")
        sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)


if __name__ == "__main__":
    if len(sys.argv)==2:
        config_file = sys.argv[1]
    else:
        config_file = "q4s_lite_config.ini"

    if not (os.path.exists(config_file)):
        print("\n[Q4S Lite CONFIG] Config file not found using default configuration values\n")

    _Q4S_NODE = q4s_lite.q4s_lite_node(
        role="server",
        address=server_address,
        port=server_port,
        target_address=client_address,
        target_port=client_port,
        event_publicator=threading.Event(),
        config_file=config_file
    )
    _Q4S_NODE.run()

    client_id = f"q4s_{decode_identifier(_Q4S_NODE.flow_id)}"

    flow_txt = decode_identifier(_Q4S_NODE.flow_id)  # '7777'
    client_id = f"q4s_{flow_txt}" 

    _MQTT_CLIENT = mqtt.Client(
    client_id=client_id,
    protocol=mqtt.MQTTv5,
    callback_api_version=CallbackAPIVersion.VERSION2,
)
    _MQTT_CLIENT.username_pw_set(USERNAME, PASSWORD)
    _MQTT_CLIENT.on_connect = on_connect
    _MQTT_CLIENT.on_disconnect = on_disconnect
    _MQTT_CLIENT.on_publish = on_publish
    _MQTT_CLIENT.will_set(f"RD/{client_id}/status", "offline", qos=1, retain=False)
    _MQTT_CLIENT.reconnect_delay_set(1, 60)
    
    _MQTT_CLIENT.connect_async(
    BROKER_HOST,
    BROKER_PORT,
    keepalive=60,
    clean_start=mqtt.MQTT_CLEAN_START_FIRST_ONLY,
    )
    _MQTT_CLIENT.loop_start()

    _RUNNING_EVENT.set()
    threading.Thread(target=measures_publisher, daemon=True,
                     name="measures_publisher",
                     args=(_Q4S_NODE, _MQTT_CLIENT, _CONNECTED_EVENT, _RUNNING_EVENT)).start()
    threading.Thread(target=alerts_publisher, daemon=True,
                     name="alerts_publisher",
                     args=(_Q4S_NODE, _MQTT_CLIENT, _CONNECTED_EVENT, _RUNNING_EVENT)).start()

    print()     
    logger.info("Publicador operativo. Pulsa 0 para salir…")
    try:
        while True:
            if input().strip() == "0":
                graceful_exit()
    except (KeyboardInterrupt, EOFError):
        graceful_exit()
