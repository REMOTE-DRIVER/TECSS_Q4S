import threading
import time
import q4s_lite
import logging,sys
from datetime import datetime
import socket
import configparser


#Parametros q4s
event = threading.Event()

#Parametros del actuador
actuator_alive = False
#actuator_host,actuator_port = "127.0.0.1",8889
DEFAULTS = {'ACTUATOR':{
                'actuator_address':'127.0.0.1',
                'actuator_port':'8889'    
            }}

config = configparser.ConfigParser()

config.read_dict(DEFAULTS)  # cargar valores por defecto primero
config.read("q4s_lite_config.ini")
# Acceder y convertir tipos
general = config['GENERAL']
network = config['NETWORK']
actuator = config['ACTUATOR']

actuator_host= actuator.get('actuator_address')
actuator_port= actuator.getint('actuator_port')
#falta obtener los de q4s para crear el q4s_node
server_address, server_port = q4s_lite.server_address, q4s_lite.server_port#"127.0.0.1",20001
client_address, client_port = q4s_lite.client_address, q4s_lite.client_port#"127.0.0.1",20002

print('\nActuator Config params')
print("======================")
print(f"actuator_address,actuator_port = {actuator_host},{actuator_port}")
print(f"server_address,server_port = {server_address},{server_port}")
print(f"client_address,client_port = {client_address},{client_port}")
print()



#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_client.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

#mejor usar q4s_lite.LATENCY_ALERT
LATENCY_ALERT = q4s_lite.LATENCY_ALERT#360 #milisegundos
PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT#0.1#0.02 #2%

FUENTES = 1
slot = FUENTES*250000 #TODO en mayusculas
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

def main():
    global actuator_alive
    logger.addHandler(client_handler)
    #El actuador es el cliente por defecto, ya que va en el coche
    q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event_actuator=event)
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
 