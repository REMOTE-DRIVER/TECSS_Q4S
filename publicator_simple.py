import threading
import time
import q4s_lite
import logging

#Parametros q4s
event = threading.Event()
server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 2000

PUBLICATION_TIME = 3 #segundos
PUBLICATION_ALERT_TIME = 1 #segundo

#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_server.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

LATENCY_ALERT = q4s_lite.LATENCY_ALERT#360 #milisegundos
PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT#0.1#0.02 #2%

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
        print(f"\n[PUBLICATOR ALERTS] Alerta con codigo {alert_code}:{q4s_node.latency_combined} {q4s_node.packet_loss_combined} {q4s_node.connection_errors}")
    print("\nFinished alert publication you must relaunch the program\nPress 0 to exit\n")

def measures_publicator(q4s_node):
    global publicator_alive
    while publicator_alive:
        print(f"[PUBLICATOR] Vehicle id = {decode_identifier(q4s_node.flow_id)} Measures Latency:{q4s_node.latency_combined:.10f} Packet_loss: {q4s_node.packet_loss_combined:.3f}")
        time.sleep(PUBLICATION_TIME)


def main():
    global publicator_alive
    logger.addHandler(client_handler)
    #El actuador es el server por defecto, ya que va en el proxy de video
    q4s_node = q4s_lite.q4s_lite_node("server", server_address, server_port,client_address, client_port,event_publicator=event)
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
            print("1: empeora latencia")
            print("2: mejora latencia")
            print("3: pierde un 10 por ciento de paquetes")
            print("4: deja de perder paquetes")
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
                q4s_node.latency_decoration+=0.1
            elif option == '2':
                q4s_node.latency_decoration=0
            elif option == '3':
                q4s_node.packet_loss_decoration=0.8
                print(f"Packet_loss_decoration =  {q4s_node.packet_loss_decoration}")
            elif option == '4':
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