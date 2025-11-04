import threading
import time
import q4s_lite
import logging,sys, os
from datetime import datetime
import socket, struct
import configparser


#Parametros q4s
event = threading.Event()

#Parametros del actuador
actuator_alive = False
#actuator_host,actuator_port = "127.0.0.1",8889
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

actuator_host= actuator.get('actuator_address')
actuator_port= actuator.getint('actuator_port')
insignificant_loses = actuator.getfloat('insignificant_loses')
FUENTES = actuator.getint('FUENTES')
TAM_POR_FUENTE = actuator.getint('TAM_POR_FUENTE')
PROXY_USE = actuator.getboolean('PROXY_USE')

#server_address, server_port = q4s_lite.server_address, q4s_lite.server_port#"127.0.0.1",20001
#client_address, client_port = q4s_lite.client_address, q4s_lite.client_port#"127.0.0.1",20002
server_address= network.get('server_address')
server_port= network.getint('server_port')
client_address= network.get('client_address')
client_port= network.getint('client_port')
VEHICLE_ID= general.get('VEHICLE_ID')

print('\nActuator Config params')
print("======================")
print(f"actuator_address,actuator_port = {actuator_host},{actuator_port}")
print(f"server_address,server_port = {server_address},{server_port}")
print(f"client_address,client_port = {client_address}")
print(f"insignificant_losses = {insignificant_loses}")
print(f"fuentes = {FUENTES}")
print(f"tam por fuente = {TAM_POR_FUENTE}")
print(f"Proxy = {PROXY_USE}")
print(f"Vehicle id = {VEHICLE_ID}")
print()



#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_client.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

#mejor usar q4s_lite.LATENCY_ALERT
#LATENCY_ALERT = q4s_lite.LATENCY_ALERT#360 #milisegundos
#PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT#0.1#0.02 #2%
LATENCY_ALERT= general.getint('LATENCY_ALERT')
PACKET_LOSS_ALERT= general.getfloat('PACKET_LOSS_ALERT')

#FUENTES = 1
slot = FUENTES*TAM_POR_FUENTE#250000 #TODO en mayusculas
#ORIG_BANDWIDTH = FUENTES * 6000000
MAX_ALERTS_CONSECUTIVES = 3

def send_command(command: str) -> str:
    """Envía un comando al dispositivo y recibe la respuesta mediante TCP."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((actuator_host,actuator_port))
        #No se envia con send, para asegurar que se envia el mensaje entero
        s.sendall(command.encode() + b"\0")  # Añadir byte cero al final
        response = s.recv(1024)  # Recibir respuesta
    return response.decode().strip("\0")  # Quitar byte cero al final


def get_target_bw_orig() -> str:
    '''target_BW_orig puede ser superior a target_BW en casos de congestión de acceso o modo panic
    sample response: "4000000;5000000\0"'''
    return send_command("GET_TARGET_BW_ORIG")


def set_target_bw_orig(value: int) -> str:
    '''Distribuye el nuevo target entre todas las fuentes activas
    sample response: "OK\0"'''
    return send_command(f"SET_TARGET_BW_ORIG:{value}")


def set_noise_resist(enable: bool) -> str:
    ''' 0 para desactivar, 1 para activar
    sample response: "OK\0"'''
    return send_command(f"SET_NOISE_RESIST:{int(enable)}")

def actuator(q4s_node):
    global actuator_alive    
    while actuator_alive:
        q4s_node.event_actuator.wait()
        q4s_node.event_actuator.clear()
        #rint(f"[ACTUATOR] Me despiertan con packet loss: {q4s_node.packet_loss_combined}")       
        print(f"\n[ACTUATOR]{datetime.now().strftime("%H:%M:%S.%f")[:-3]} Me ha llegado una alerta por packet loss\n\tcliente: {q4s_node.packet_loss_up}\n\tserver: {q4s_node.packet_loss_down}\n\tcombinado: {q4s_node.packet_loss_combined}")
    print("\nFinished actuation you must relaunch the program\nPress 0 to exit\n")

def get_server_port_from_proxy(VEHICLE_ID):
    PACKET_FORMAT = ">4s4s"      # 4 bytes tipo + 16 bytes car_id
    MSG_ENCODING = "utf-8"
    while True:
        try:
            print(f"Conectando con el server en {server_address}:{server_port}...")
            p_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            p_socket.connect((server_address, server_port))
            break
        except(ConnectionRefusedError, OSError):
            print("El proxy no está disponible, reintentando en 1 segundo...")
            time.sleep(1)

    while True:
        # Empaquetar mensaje HOLA + car_id
        tipo_bytes = "HOLA".ljust(4).encode(MSG_ENCODING)
        car_bytes = VEHICLE_ID.ljust(4).encode(MSG_ENCODING)
        packet = struct.pack(PACKET_FORMAT, tipo_bytes, car_bytes)

        # Enviar al servidor
        p_socket.send(packet) 
        print(f"Enviado HOLA a {server_address}:{server_port}")

        try:
            data = p_socket.recv(5)  # Recibir respuesta
            # Suponiendo que el servidor envía el puerto como cadena de 5 bytes
            puerto_recibido = int(data.decode(MSG_ENCODING).strip())
            print(f"Recibido puerto: {puerto_recibido}")
            break  # Terminar cuando se recibe puerto
        except socket.timeout:
            print("No hay respuesta del proxy, reintentando en 1 segundo...")
            time.sleep(1)

    p_socket.close()
    print("Puerto adquirido.")
    return puerto_recibido

def main():
    global actuator_alive, server_port
    logger.addHandler(client_handler)
    #El actuador es el cliente por defecto, ya que va en el coche
    #Aqui se deberian leer las variables globales del fichero
    #config_file="q4s_lite_config.ini"
    if PROXY_USE:
        server_port = get_server_port_from_proxy(VEHICLE_ID)
    #server_port = get_server_port_from_proxy(VEHICLE_ID)
    q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event_actuator=event, config_file=config_file)
    q4s_node.run()
    actuator_alive = True
    actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
    actuator_thread.start()
    
    while True:
        print("\n1: Menu Pérdidas")
        print("2: Menu Peticiones")
        print("0: Salir")
        print("\nElige una opción: \n")
        option = input() 

        if option == '0':  # Mata el actuador y los hilos del cliente q4s
            actuator_alive = False
            q4s_node.running = False
            q4s_node.measuring = False
            q4s_node.hilo_snd.join()
            q4s_node.hilo_rcv.join()
            break

        elif option == '1':  # Submenú de pérdidas
            while True:
                print("\n1: Empeora latencia")
                print("2: Mejora latencia")
                print("3: Pierde un 10 por ciento de paquetes")
                print("4: No pierdas paquetes")
                print("0: Atrás")
                print("\nElige una opción: \n")
                sub_option = input()

                if sub_option == '0':
                    break
                elif sub_option == '1':
                    q4s_node.latency_decoration += 0.1
                elif sub_option == '2':
                    q4s_node.latency_decoration = 0
                elif sub_option == '3':
                    q4s_node.packet_loss_decoration += 0.1
                elif sub_option == '4':
                    q4s_node.packet_loss_decoration = 0

        elif option == '2':  # Submenú de peticiones al coder
            while True:
                print("\n1: Petición GET_TARGET_BW_ORIG")
                print("2: Petición SET_TARGET_BW_ORIG")
                print("3: Petición SET_NOISE_RESIST")
                print("0: Atrás")
                sub_option = input("Introduce una opción: ")
                
                if sub_option == "1":
                    print(send_command("GET_TARGET_BW_ORIG"))
                elif sub_option == "2":
                    value = int(input("Dime valor de ancho de banda objetivo: "))
                    print(send_command(f"SET_TARGET_BW_ORIG:{value}"))
                elif sub_option == "3":
                    enable = int(input("Activar (1)/Desactivar (0) modo noise resist: "))
                    print(send_command(f"SET_NOISE_RESIST:{enable}"))
                elif sub_option == "0":
                    break

    print("EXIT")


if __name__=="__main__":
    main()
 