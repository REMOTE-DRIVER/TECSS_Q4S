import threading
import time
import q4s_lite
import logging, sys, os
import configparser

#Parametros q4s
event = threading.Event()

DEFAULTS = {
    'GENERAL': {
        'VEHICLE_ID': "0001",
        'PACKETS_PER_SECOND': 30,
        'PACKET_LOSS_PRECISSION': 100,
        'LATENCY_ALERT': 150,
        'PACKET_LOSS_ALERT': 0.02,
        'NO_INIT': False
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


#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_server.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

#LATENCY_ALERT = q4s_lite.LATENCY_ALERT#360 #milisegundos
#PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT#0.1#0.02 #2%
LATENCY_ALERT= general.getint('LATENCY_ALERT')
PACKET_LOSS_ALERT= general.getfloat('PACKET_LOSS_ALERT')

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

    #print(f"Debug - connection: {connection_alert}, latency: {latency_alert}, packet_loss: {packet_loss_alert}, alert_code: {alert_code}")
    
    return alert_code


def alert_publicator(q4s_node):
    global publicator_alive
    while publicator_alive:
        q4s_node.event_publicator.wait()
        q4s_node.event_publicator.clear()
        alert_code = check_alert(q4s_node)
        #Si te han despertado y el estado no es normal, es alert
        if q4s_node.state[0]=="alert": #Si es una alerta
            print(f"\n[PUBLICATOR ALERTS] Alerta con codigo {alert_code}:{q4s_node.latency_combined} {q4s_node.packet_loss_combined} {q4s_node.connection_errors} Vehicle id = {decode_identifier(q4s_node.flow_id)}")
        elif q4s_node.state[0]=="normal": #Si te despiertan y el estado es normal, es un recovery
            print(f"\n[PUBLICATOR ALERTS] Recovery {alert_code}:{q4s_node.latency_combined} {q4s_node.packet_loss_combined} {q4s_node.connection_errors} Vehicle id = {decode_identifier(q4s_node.flow_id)}")

    print("\nFinished alert publication you must relaunch the program\nPress 0 to exit\n")

def measures_publicator(q4s_node):
    global publicator_alive
    while publicator_alive:
        print(f"\n[PUBLICATOR] Vehicle id = {decode_identifier(q4s_node.flow_id)} Measures Latency:{q4s_node.latency_combined:.10f} Packet_loss: {q4s_node.packet_loss_combined:.3f}")
        time.sleep(PUBLICATION_TIME)


def main():
    global publicator_alive
    logger.addHandler(client_handler)
    #El actuador es el server por defecto, ya que va en el proxy de video
    q4s_node = q4s_lite.q4s_lite_node("server", server_address, server_port,client_address, client_port,event_publicator=event,config_file=config_file)
    q4s_node.run()
    publicator_alive = True
    alert_publicator_thread = threading.Thread(target=alert_publicator,args=(q4s_node,),daemon=True)
    alert_publicator_thread.start()
    measures_publicator_thread = threading.Thread(target=measures_publicator,args=(q4s_node,),daemon=True)
    measures_publicator_thread.start()

    #main_thread_alive = True
    
    while True:
            #time.sleep(0.1)
            print("")
            print("1: pierde un 10 por ciento de paquetes")
            print("2: deja de perder paquetes")
            #print("5: restart publicator")
            print("0: Salir")
            print("\nElige una opción: \n")
            option = input() 
            if option == '0':#Mata el actuador y los hilos del cliente q4s
                publicator_alive=False
                #publicator_thread.join()
                q4s_node.running=False
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()
                break
            elif option == '1':
                q4s_node.packet_loss_decoration=0.1
                #print(f"Packet_loss_decoration =  {q4s_node.packet_loss_decoration}")
            elif option == '2':
                q4s_node.packet_loss_decoration=0
            '''elif option == '5':#Opcion desactivada
                publicator_alive=False
                #publicator_thread.join()
                q4s_node.running=False
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()
                publicator_thread.join()
                main()'''
                

    print("Saliendo...")

if __name__=="__main__":
    main()