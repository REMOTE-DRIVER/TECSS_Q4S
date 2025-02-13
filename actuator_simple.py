import threading
import time
import q4s_lite
import logging,sys
from datetime import datetime
#Parametros q4s
event = threading.Event()
server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 2000

#Parametros del actuador
actuator_alive = False
actuator_host,actuator_port = "127.0.0.1",8889

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


def state_machine(q4s_node):
    global actuator_alive
    slot = 250000 #bits por segundo
    state = 0
    consecutive_events = 0
    prev_packet_loss = None
    tiempo_espera = q4s_lite.KEEP_ALERT_TIME
    while True:
        if state == 0:
            #Subir ancho de banda hasta que llegue al original, si es el original no hace nada
            #Si esta en modo ruido lo quitamos
            #Si llega alerta, vamos a estado 1
            #Si falla cualquier peticion al coder, volvemos a estado 0
            break
        elif state == 1:
            #Se consulta ancho de banda y se pide que baje un slot
            #te duermes esperando una alerta event_received = q4s_node.event.wait(timeout=TIME_X) se pone a True si llega evento
            #si no llega la alerta, la cosa ha mejorado y te vas al estado 0
            #Si llega alerta, vuelves al estado 1 (para bajar otro slot)
            #Si llegan 3 alertas, te vas al estado 2
            #Si falla cualquier peticion al coder, volvemos a estado 0
            continue
        elif state==2:
            #Guardamos la perdida de paquetes con la que llegamos aqui
            #Ponemos modo ruido
            #esperamos
            #Comprobamos perdida paquetes
            #Si es peor bajamos un slot de ancho de banda y volvemos a estado 2
            #si es mejor vamos a estado 0
            continue



def actuator_old(q4s_node):
    global actuator_alive
    
    while actuator_alive:
        q4s_node.event.wait()
        q4s_node.event.clear()
        print(f"[ACTUATOR] Me despiertan con packet loss: {q4s_node.packet_loss_combined}")
        #Alerta de perdida de conexion o de latencia/packet loss
        if q4s_node.running==False:
            print("Alerta por perdida de conexion")
            actuator_alive = False
            #Si esta implementado el reset haces continue del bucle
            #Ahora lo que haces es emitir un mensaje de que terminas
        else:
            if q4s_node.packet_loss_combined >= PACKET_LOSS_ALERT:
                print(f"\n[ACTUATOR]{datetime.now().strftime("%H:%M:%S.%f")[:-3]} Me ha llegado una alerta por packet loss\n\tcliente: {q4s_node.packet_loss_up}\n\tserver: {q4s_node.packet_loss_down}\n\tcombinado: {q4s_node.packet_loss_combined}")
                #state_machine(q4s_node)
                
        #peticion a lhe
    print("\nFinished actuation you must relaunch the program\nPress 0 to exit\n")
                
def actuator(q4s_node):
    global actuator_alive
    global state
    slot = 250000 #bits por segundo
    state = 0
    consecutive_events = 0
    prev_packet_loss = None
    tiempo_espera = q4s_lite.KEEP_ALERT_TIME
    while actuator_alive:
        if state == 0:
            q4s_node.event.wait()
            q4s_node.event.clear()
            print(f"\n[ACTUATOR]{datetime.now().strftime("%H:%M:%S.%f")[:-3]} Me ha llegado una alerta por packet loss\n\tcliente: {q4s_node.packet_loss_up}\n\tserver: {q4s_node.packet_loss_down}\n\tcombinado: {q4s_node.packet_loss_combined}")
            #Subir ancho de banda hasta que llegue al original, si es el original no hace nada
            #Si esta en modo ruido lo quitamos
            #Si llega alerta, vamos a estado 1
            #Si falla cualquier peticion al coder, volvemos a estado 0
            continue
        elif state == 1:
            #Se consulta ancho de banda y se pide que baje un slot
            #te duermes esperando una alerta event_received = q4s_node.event.wait(timeout=TIME_X) se pone a True si llega evento
            #si no llega la alerta, la cosa ha mejorado y te vas al estado 0
            #Si llega alerta, vuelves al estado 1 (para bajar otro slot)
            #Si llegan 3 alertas, te vas al estado 2
            #Si falla cualquier peticion al coder, volvemos a estado 0
            continue
        elif state==2:
            #Guardamos la perdida de paquetes con la que llegamos aqui
            #Ponemos modo ruido
            #esperamos
            #Comprobamos perdida paquetes
            #Si es peor bajamos un slot de ancho de banda y volvemos a estado 2
            #si es mejor vamos a estado 0
            continue


def main():
    global actuator_alive
    logger.addHandler(client_handler)
    #El actuador es el cliente por defecto, ya que va en el coche
    q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event)
    q4s_node.run()
    actuator_alive = True
    actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
    actuator_thread.start()

    #main_thread_alive = True
    
    while True:
            #time.sleep(0.1)
            print("")
            print("1: empeora latencia")
            print("2: mejora latencia")
            print("3: pierde un 10 por ciento de paquetes")
            print("4: No pierdas paquetes")
            #print("5: restart actuator")
            print("0: Salir")
            option = input("\nElige una opcion\n")
            if option == '0':#Mata el actuador y los hilos del cliente q4s
                actuator_alive=False
                #actuator_thread.join()
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
                q4s_node.packet_loss_decoration+=0.1
            elif option == '4':
                q4s_node.packet_loss_decoration=0
            '''elif option == '5':#Opcion desactivada
                actuator_alive=False
                #actuator_thread.join()
                q4s_node.running=False
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()
                actuator_thread.join()
                main()'''
                

    print("EXIT")

if __name__=="__main__":
    main()
    '''logger.addHandler(client_handler)
    #El actuador es el cliente por defecto, ya que va en el coche
    q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event)
    q4s_node.run()
    actuator_alive = True
    actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
    actuator_thread.start()

    #main_thread_alive = True
    
    while True:
            #time.sleep(0.1)
            print("")
            print("1: empeora latencia")
            print("2: mejora latencia")
            print("3: pierde un 10 por ciento de paquetes")
            print("4: pierde un 10 por ciento de paquetes")
            print("5: restart actuator")
            print("0: Salir")
            option = input("\nElige una opcion\n")
            if option == '0':#Mata el actuador y los hilos del cliente q4s
                actuator_alive=False
                #actuator_thread.join()
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
                q4s_node.packet_loss_decoration+=0.1

    print("EXIT")'''
    