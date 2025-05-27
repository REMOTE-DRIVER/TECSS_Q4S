import threading
from pathlib import Path
import os
import time
import q4s_lite
import logging
import signal
import sys

from paho.mqtt.enums import CallbackAPIVersion
import paho.mqtt.client as mqtt

#Parametros q4s
event = threading.Event()
server_address, server_port = "127.0.0.1", 20001
client_address, client_port = "127.0.0.1", 20002

#Parametros mqtt
publicator_alive = False
mqtt_host, mqtt_port = "remotedriver.dit.upm.es", 41883
username = "nokiatecss"
password = "qSASgLxTZjzdFjvI8nC29A"

PUBLICATION_TIME = 3 #segundos
PUBLICATION_ALERT_TIME = 1 #segundo

#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_server.log',mode='w')
client_handler.setFormatter(formatter)
logger.addHandler(client_handler)

LATENCY_ALERT = q4s_lite.LATENCY_ALERT
PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT

# Variable global para controlar el estado de conexión
mqtt_connected = threading.Event()

def encode_identifier(identifier: str) -> int:
    if len(identifier) != 4:
        raise ValueError("El identificador debe tener exactamente 4 caracteres")
    return int.from_bytes(identifier.encode('utf-8'), byteorder='big')

def decode_identifier(number: int) -> str:
    return number.to_bytes(4, byteorder='big').decode('utf-8')

def check_alert(q4s_node):
    '''Esta funcion comprueba el origen de la alerta y lo devuelve
    perdida conexion, latencia, perdida paquetes, Resultado funcion
    0                   0           0                0
    0                   0           1                1
    0                   1           0                2
    0                   1           1                3
    1                   0           0                4
    1                   0           1                5
    1                   1           0                6
    1                   1           1                7'''
    connection_alert = int(q4s_node.connection_errors > 0)
    latency_alert = int(q4s_node.latency_combined > LATENCY_ALERT)
    packet_loss_alert = int(q4s_node.packet_loss_combined > PACKET_LOSS_ALERT)
    
    alert_code = (connection_alert << 2) | (latency_alert << 1) | packet_loss_alert
    
    return alert_code

def wait_for_mqtt_connection(timeout=30):
    """Espera hasta que MQTT esté conectado o se agote el timeout"""
    return mqtt_connected.wait(timeout=timeout)

def alert_publicator(q4s_node, client_mqtt):
    """Publica alertas en cuanto `q4s_node.event_publicator` se dispara."""
    global publicator_alive
    
    logger.info("Hilo alert_publicator iniciado")
    
    while publicator_alive:
        try:
            # Wait con timeout para poder verificar publicator_alive
            event_triggered = q4s_node.event_publicator.wait(timeout=1.0)
            
            # Verificar si debemos salir
            if not publicator_alive:
                break
                
            # Solo procesar si el evento se disparó realmente
            if event_triggered:
                q4s_node.event_publicator.clear()
                
                # Esperar conexión MQTT con timeout
                if not mqtt_connected.is_set():
                    logger.warning("Esperando conexión MQTT para alerta...")
                    if not wait_for_mqtt_connection(timeout=5):
                        logger.warning("Timeout esperando conexión MQTT, saltando alerta")
                        continue
                
                alert_code = check_alert(q4s_node)
                print(f"\n[PUBLICATOR ALERTS] Alerta con codigo {alert_code}\n")
                
                topic = f"RD/{decode_identifier(q4s_node.flow_id)}/QoS_alert"
                payload = (
                    f"{alert_code};lat={q4s_node.latency_combined:.10f};"
                    f"pl={q4s_node.packet_loss_combined:.3f};"
                    f"jitter={q4s_node.jitter_combined:.3f};"
                    f"pc={q4s_node.connection_errors}"
                )
                
                # Publicar con QoS 1 para mayor fiabilidad
                result = client_mqtt.publish(topic, payload, qos=1)
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info("-> ALERTA %s -> %s", topic, payload)
                else:
                    logger.error("Error publicando alerta: %s", result.rc)
                    
        except Exception as e:
            logger.error(f"Error en alert_publicator: {e}")
            if not publicator_alive:
                break
    
    logger.info("Hilo alert_publicator terminado")

def measures_publicator(q4s_node, client_mqtt):
    """Publica métricas de QoS cada `PUBLICATION_TIME` segundos."""
    global publicator_alive
    
    logger.info("Hilo measures_publicator iniciado")
    
    while publicator_alive:
        try:
            # Esperar conexión MQTT con timeout
            if not mqtt_connected.is_set():
                logger.warning("Esperando conexión MQTT para medida...")
                if not wait_for_mqtt_connection(timeout=5):
                    logger.warning("Timeout esperando conexión MQTT, saltando medida")
                    time.sleep(1)
                    continue
            
            print()
            print(f"[PUBLICATOR] Vehicle id = {decode_identifier(q4s_node.flow_id)} "
                  f"Measures Latency:{q4s_node.latency_combined:.10f} "
                  f"Packet_loss: {q4s_node.packet_loss_combined:.3f} "
                  f"Jitter: {q4s_node.jitter_combined:.3f} "
                  f"Connection errors: {q4s_node.connection_errors}")
            
            topic = f"RD/{decode_identifier(q4s_node.flow_id)}/QoS_status"
            payload = (
                f"lat={q4s_node.latency_combined:.10f};"
                f"pl={q4s_node.packet_loss_combined:.3f};"
                f"jitter={q4s_node.jitter_combined:.3f};"
                f"pc={q4s_node.connection_errors}"
            )
            
            # Publicar con QoS 1 para mayor fiabilidad
            result = client_mqtt.publish(topic, payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug("-> MEDIDA %s -> %s", topic, payload)
            else:
                logger.error("Error publicando medida: %s", result.rc)
            
            # Sleep fraccionado para responder más rápido a publicator_alive
            sleep_remaining = PUBLICATION_TIME
            while sleep_remaining > 0 and publicator_alive:
                sleep_chunk = min(0.5, sleep_remaining)  # Sleep en chunks de 0.5s máximo
                time.sleep(sleep_chunk)
                sleep_remaining -= sleep_chunk
                
        except Exception as e:
            logger.error(f"Error en measures_publicator: {e}")
            if not publicator_alive:
                break
            time.sleep(1)  # Evitar loop infinito en caso de error persistente
    
    logger.info("Hilo measures_publicator terminado")

def on_connect(client, userdata, flags, reason_code, properties):
    global mqtt_connected
    
    if flags.session_present:
        print("Session Present")
        
    if reason_code == 0:
        # Conexión exitosa
        logger.info("Conectado a %s:%s", mqtt_host, mqtt_port)
        print("Conexión exitosa")
        mqtt_connected.set()  # Señalar que estamos conectados
        
        # Publicar estado online al conectarse
        client_id = client._client_id.decode() if isinstance(client._client_id, bytes) else client._client_id
        client.publish(f"RD/{client_id}/status", "online", qos=1, retain=True)
        
    else:
        # Error en la conexión
        logger.error("Fallo de conexión (reason_code=%s)", reason_code)
        print(f"Error en la conexión con el código: {reason_code}")
        mqtt_connected.clear()

def on_disconnect(client, userdata, flags, reason_code, properties):
    global mqtt_connected
    
    mqtt_connected.clear()  # Señalar que estamos desconectados
    
    if reason_code == 0:
        # Desconexión exitosa
        logger.info("Desconectado")
        print("Desconexión exitosa")
    else:
        # Error en la desconexión
        logger.warning("Desconectado (reason_code=%s)", reason_code)
        print(f"Error en la desconexión con el código: {reason_code}")

def main() -> None:
    global publicator_alive, mqtt_connected
    logger.addHandler(client_handler)

    # El actuador es el server por defecto, ya que va en el proxy de video
    q4s_node = q4s_lite.q4s_lite_node(
        "server",
        server_address, server_port,
        client_address, client_port,
        event,
    )
    q4s_node.run()

    print(f"client_id = q4s_{decode_identifier(q4s_node.flow_id)}")
    client_id = f"q4s_{decode_identifier(q4s_node.flow_id)}"
    
    # Crear cliente MQTT
    client_mqtt = mqtt.Client(
        client_id=client_id,
        protocol=mqtt.MQTTv5,
        callback_api_version=CallbackAPIVersion.VERSION2,
    )
    
    # Configurar clean session después de crear el cliente
    client_mqtt._clean_start = mqtt.MQTT_CLEAN_START_FIRST_ONLY  # Para MQTT v5
    client_mqtt.username_pw_set(username, password)
    
    # Configurar callbacks
    client_mqtt.on_connect = on_connect
    client_mqtt.on_disconnect = on_disconnect
    
    # Configurar reconexión automática
    client_mqtt.reconnect_delay_set(min_delay=1, max_delay=60)
    
    # Configurar Last Will (opcional pero recomendado)
    client_mqtt.will_set(
        topic=f"RD/{client_id}/status",
        payload="offline",
        qos=1,
        retain=True
    )
    
    # Variable para controlar threads
    publicator_alive = False
    alert_publicator_thread = None
    measures_publicator_thread = None
    
    def _graceful_exit(*_):
        global publicator_alive
        
        logger.info("Cerrando publicador...")
        
        # 1. Detener threads daemon (se señaliza pero no esperamos)
        publicator_alive = False
        if hasattr(q4s_node, 'event_publicator'):
            q4s_node.event_publicator.set()  # Desbloquear alert_publicator
        
        # 2. Detener Q4S
        q4s_node.running = False
        q4s_node.measuring = False
        
        # 3. Desconectar MQTT limpiamente
        try:
            # Publicar mensaje de desconexión si estamos conectados
            if mqtt_connected.is_set():
                client_mqtt.publish(f"RD/{client_id}/status", "offline", qos=1, retain=True)
                time.sleep(0.2)  # Dar tiempo a que se envíe el mensaje
            
            client_mqtt.loop_stop()
            client_mqtt.disconnect()
            time.sleep(0.1)  # Dar tiempo a la desconexión
        except Exception as e:
            logger.error(f"Error al desconectar MQTT: {e}")
        
        logger.info("Publicator finalizado correctamente")
        sys.exit(0)
    
    # Configurar manejadores de señal
    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)
    
    try:
        # Conectar al broker MQTT con reconexión automática
        logger.info("Conectando al broker MQTT...")
        
        # Usar connect_async para evitar bloqueo en la conexión inicial
        client_mqtt.connect_async(mqtt_host, mqtt_port, keepalive=60)
        client_mqtt.loop_start()  # Iniciar loop MQTT
        
        # Esperar confirmación de conexión inicial
        logger.info("Esperando conexión inicial...")
        if wait_for_mqtt_connection(timeout=10):
            logger.info("Conexión MQTT establecida")
        else:
            logger.warning("Timeout en conexión inicial, continuando (reconexión automática activa)")
        
        # Iniciar threads de publicación
        publicator_alive = True
        alert_publicator_thread = threading.Thread(
            target=alert_publicator, 
            args=(q4s_node, client_mqtt,), 
            daemon=True
        )
        measures_publicator_thread = threading.Thread(
            target=measures_publicator, 
            args=(q4s_node, client_mqtt,), 
            daemon=True
        )
        
        alert_publicator_thread.start()
        measures_publicator_thread.start()
        
        logger.info("Publicador iniciado correctamente. Presiona 0 para salir.")
        
        # Loop principal
        while True:
            try:
                cmd = input("Presiona 0 para salir » ")
                if cmd.strip() == "0":
                    break
            except EOFError:
                # Si no hay entrada disponible (ej: ejecutado en background)
                time.sleep(1)
                continue
            except KeyboardInterrupt:
                # Manejar Ctrl+C aquí también
                break
                
    except Exception as e:
        logger.error(f"Error durante la ejecución: {e}")
    finally:
        _graceful_exit()

if __name__=="__main__":
    main()