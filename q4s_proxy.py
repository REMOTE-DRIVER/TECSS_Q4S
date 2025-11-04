''' 
Proxy:  
Tiene un fichero de asignaciones: id_coche:puerto (en el que le escucha) que mira al iniciar, si tiene entradas escritas, levanta tantos hilos como sea necesario. Al cerrar el proceso “ordenadamente” se vacía el fichero.
Funcionamiento:
1.  Recibe Hola      
a)  comprueba en el fichero si ese coche ya está siendo escuchado en un puerto
b)   si no lo está:  levanta hilo con el publicador en un puerto y responde con ese puerto, luego lo apunta en el fichero de asignaciones. 
c)  Si está: contesta con ese puerto
2.  Si pierde conexión el coche y el hilo sigue activo: No pasa nada, cuando la recupera funciona igual
3.  Si se cierra el actuador en el coche y el hilo sigue activo: Coche dice hola al proceso proxy, este comprueba la tabla, ve su id, y le responde con el puerto.
4.  Si se cae el proceso proxy, se mueren los hilos, en el coche no pasa nada pero no puede medir
a)  Al reiniciar mira el fichero de asignaciones y levanta todos los procesos que tiene apuntados. TODO: Error, no arranca mqtt

¿Si se cae el proceso proxy, lo relanzo automáticamente (lo gestionaría desde un .bat)? Yo creo que sí.

'''

import socket
import struct
import threading
import sys
import os
import logging, configparser
import publicator_mqtt, publicator_simple
import ast

config = configparser.ConfigParser()
config_file = "q4s_lite_config.ini"
config.read(config_file)
# Acceder y convertir tipos
proxy = config['PROXY']
default_listening_port = proxy.getint('DEFAULT_LISTENING_PORT')
available_ports = ast.literal_eval(proxy.get("AVAILABLE_PORTS"))
publicator_mode = proxy.get("PUBLICATOR")

print("Puerto principal:", default_listening_port)
print("Puertos disponibles:", available_ports)
print("Modo publicador:", publicator_mode)

#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_proxy.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)


PACKET_FORMAT = ">4s4s"      # 4 bytes tipo + 4 bytes car_id
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)
MSG_ENCODING = "utf-8"

PUERTOS_DISPONIBLES = available_ports
ASSIGN_FILE = "q4s_assignations.txt"

#Cerrojos para modificar el fichero o arrancar hilo en puerto
pub_lock = threading.Lock()
file_lock = threading.Lock()


#Gestion de ficheros
def file_get_port_from_car_id(car_id):
    with file_lock:
        with open(ASSIGN_FILE, "r") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or ":" not in linea:
                    continue
                file_car_id, port = linea.split(":", 1)
                if file_car_id == car_id:
                    return int(port)
    return None

def file_write_assignation(car_id, port):
    with file_lock:
        with open(ASSIGN_FILE, "a") as f:
            f.write(f"{car_id}:{port}\n")

def get_unused_port(puertos_disponibles):
    asignados = set()
    with file_lock:
        with open(ASSIGN_FILE, "r") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or ":" not in linea:
                    continue
                _, port = linea.split(":", 1)
                asignados.add(int(port))
                
    libres = [p for p in puertos_disponibles if p not in asignados]
    return libres

def file_check_cars_running():
    ports_to_launch=[]
    with file_lock:
        with open(ASSIGN_FILE, "r") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or ":" not in linea:
                    continue
                file_car_id, port = linea.split(":")
                ports_to_launch.append(int(port))
    return ports_to_launch

#Check publicador
def start_publicator(port):
    with pub_lock:
        if publicator_mode.upper() == "MQTT":
            t = threading.Thread(target=publicator_mqtt.main,kwargs={"server_port": port},daemon=True,name=f"publicator-{port}")
        else:
            t = threading.Thread(target=publicator_simple.main,kwargs={"server_port": port},daemon=True,name=f"publicator-{port}")
        t.start()
        print(f"Arrancado publicator en puerto {port}")



#Gestion de cliente TCP, recepcion "hola"
def handle_client_tcp(conn, addr):
    try:
        data = conn.recv(PACKET_SIZE)
        if not data:
            print("No data received")
            return

        unpacked = struct.unpack(PACKET_FORMAT, data)
        message_type = unpacked[0].decode(MSG_ENCODING).strip('\x00').strip()
        car_id = unpacked[1].decode(MSG_ENCODING).strip('\x00').strip()

        if message_type == "HOLA":
            print(f"Recibido HOLA de {car_id} ({addr})")
            puerto_destino = file_get_port_from_car_id(car_id)
            if puerto_destino is None: #El car_id no esta en el fichero
                libres = get_unused_port(PUERTOS_DISPONIBLES)
                if not libres:
                    print("ERROR: No hay puertos disponibles")
                    return
                puerto_destino = libres[0]
                file_write_assignation(car_id, puerto_destino)
                start_publicator(puerto_destino)
            # enviar puerto al cliente
            packet_data = str(puerto_destino).ljust(5).encode(MSG_ENCODING)
            conn.send(packet_data)

    except Exception as e:
        print(f"Error procesando cliente {addr}: {e}")
    finally:
        conn.close()


def main():
    # TCP socket
    p_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    p_socket.bind(("0.0.0.0", default_listening_port))
    p_socket.listen()
    print(f"Proxy TCP escuchando en puerto {default_listening_port}")

    def accept_clients():
        while True:
            conn, addr = p_socket.accept()
            threading.Thread(target=handle_client_tcp, args=(conn, addr), daemon=True).start()

    proxy_thread = threading.Thread(target=accept_clients, daemon=True)
    proxy_thread.start()


    #Mirar si tiene algo escrito en el fichero para lanzarlo
    ports_to_launch = file_check_cars_running()
    for port in ports_to_launch:
        start_publicator(port)

    # entrada por consola para terminar
    print("Pulsa 0 + Enter para terminar y vaciar fichero.")
    try:
        while True:
            linea = input().strip()
            if linea == "0":
                print("Terminando...")
                p_socket.close()
                with file_lock:
                    open(ASSIGN_FILE, "w").close()
                    print(f"{ASSIGN_FILE} vaciado.")
                sys.exit(0)
            else:
                print("Pulsa 0 para salir.")
    except (KeyboardInterrupt, EOFError):
        print("Terminando por teclado...")
        p_socket.close()
        with file_lock:
            open(ASSIGN_FILE, "w").close()
            print(f"{ASSIGN_FILE} vaciado.")
        sys.exit(0)

if __name__ == "__main__":
    main()