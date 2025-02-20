import threading
import time
import q4s_lite
import logging,sys
from datetime import datetime
import socket
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

FUENTES = 3
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

def check_alert_valid(q4s_node):
    '''Esta funcion es para validar que una alerta recibida es por packet loss y no por latencia o perdida conex'''
    if q4s_node.running==False:
        print("Alerta por perdida de conexion")
        actuator_alive = False
        #Si esta implementado el reset haces continue del bucle
        #Ahora lo que haces es emitir un mensaje de que terminas
        return False
    else:
        if q4s_node.packet_loss_combined >= PACKET_LOSS_ALERT:
            return True
    return False

def actuator(q4s_node):
    '''Variables de medicion:
    ORIG_BANDWIDTH: Por configuracion, el tope de bw que puede dar el coder, se usa en el estado 0, para intentar
                    llegar a este tope
    
    coder_actual_bandwidth: El primer valor que devuelve el get_bw, sirve como tope de subida de bw cuando hay congestion
                            tambien sirve como punto del que bajar bw cuando hay congestion
    
    coder_orig_bandwidth: El segundo valor que devuelve el get_bw. Cuando hago set_bw_orig, modifico este valor
    
    actuator_bandwidth: Con este valor trabaja el actuador, debe ser igual que el coder_orig_bandwidth si todo va bien
    
    actuator_noise_mode: Booleano para ver si hay que hacer la peticion de poner modo ruido

    actuator_latency_alert: Booleano para ignorar alertas por latencia
    '''
    global actuator_alive

    actuator_noise_mode = False
    actuator_latency_alert = False
    state = 0
    consecutive_alerts = 0
    prev_packet_loss = None
    tiempo_espera = 2*q4s_lite.KEEP_ALERT_TIME #TODO: Consensuar este tiempo con JJ, Sergio y Alberto

    #Peticion inicial de ancho de banda
    ORIG_BANDWIDTH = 0
    orig_bandwith_from_coder = False
    try_number = 0
    while not orig_bandwith_from_coder:
        try_number+=1
        try:
            ORIG_BANDWIDTH = get_target_bw_orig().split[";"][1]
            orig_bandwith_from_coder = True
        except Exception as e:
            print(f"[ACTUATOR] Cant get target bandwidth from coder try number {try_number}")
            continue
    coder_orig_bandwidth = ORIG_BANDWIDTH #el segundo parametro de get_bandwith, originalmente es por configuración
    actuator_bandwidth = coder_orig_bandwidth #El bandwith con el que trabaja el actuador, sobre este restamos slots, etc..
    while actuator_alive:
        if state == 0:
            if actuator_latency_alert == False:#Ignorar alertas de latencia
                #Paso 0: pido ancho de banda y intento subir al original
                try:
                    coder_actual_and_orig_bandwidth = get_target_bw_orig().split[";"]
                except:
                    state=0
                    continue
                coder_actual_bandwidth,coder_orig_bandwidth = int(coder_actual_and_orig_bandwidth[0]), int(coder_actual_and_orig_bandwidth[1]) 
                #Subir ancho de banda hasta que llegue al original(ORIG_BANDWIDTH), si es el original no hace nada
                if actuator_bandwidth < ORIG_BANDWIDTH-(slot/FUENTES):
                    #subirlo hasta llegar a orig_bandwidth                
                    if coder_actual_bandwidth == coder_orig_bandwidth:
                        bandwith_parameter = actuator_bandwidth+slot
                        if set_target_bw_orig(bandwith_parameter) != "OK":
                            state = 0
                            continue
                        else:
                            actuator_bandwidth = bandwith_parameter
                            coder_orig_bandwidth = actuator_bandwidth 
                    else: #Hay congestion en el coder y no podemos subir a tope, subimos a lo que puede el coder
                        if actuator_bandwidth < coder_actual_bandwidth-(slot/FUENTES):
                            bandwith_parameter = coder_actual_bandwidth+slot
                            if set_target_bw_orig(bandwith_parameter) != "OK":
                                state = 0
                                continue
                            else:
                                actuator_bandwidth = bandwith_parameter
                                coder_orig_bandwidth = actuator_bandwidth                   
                    
            else:
                actuator_latency_alert = False

            #Paso 1: Si esta en modo ruido lo quitamos
            if actuator_noise_mode == True: #Si esta en modo ruido, lo quito
                if set_noise_resist(False) != "OK":
                    state = 0                    
                    continue
                else:
                    actuator_noise_mode = False
            
            #Paso 2: Esperamos:si llega alerta, vamos a estado 1, si no llega nos quedamos en el estado 0
            alert_received_during_sleep = q4s_node.event.wait(timeout = tiempo_espera)
            if alert_received_during_sleep == False:
                state=0
                continue
            else:
                q4s_node.event.clear()
                if check_alert_valid(q4s_node) == True:
                    print(f"\n[ACTUATOR]{datetime.now().strftime("%H:%M:%S.%f")[:-3]} Me ha llegado una alerta por packet loss\n\tcliente: {q4s_node.packet_loss_up}\n\tserver: {q4s_node.packet_loss_down}\n\tcombinado: {q4s_node.packet_loss_combined}")
                    state = 1
                    continue
                else: #La alerta era de latencia
                    state = 0
                    actuator_latency_alert = True
                    continue

        elif state == 1:
            if actuator_latency_alert == False:#Ignorar alertas de latencia
                #Paso 0: Bajar un slot 
                try:
                    coder_actual_and_orig_bandwidth = get_target_bw_orig().split[";"]
                except:
                    state=0
                    continue
                coder_actual_bandwidth,coder_orig_bandwidth = int(coder_actual_and_orig_bandwidth[0]), int(coder_actual_and_orig_bandwidth[1]) 
                
                if coder_actual_bandwidth == coder_orig_bandwidth: #no hay congestion
                    actuator_bandwidth -= slot
                    if set_target_bw_orig(actuator_bandwidth) != "OK":
                        state = 0
                        actuator_bandwidth += slot
                        #se puede resetear actuator orig bandwith a coder_orig_bandwidth
                        continue
                else: #hay congestion coder_actual_bandwidth es mas pequeño que el orig                
                    if set_target_bw_orig(coder_actual_bandwidth - slot) != "OK":
                        state = 0
                        continue
                    else:
                        actuator_bandwidth = coder_actual_bandwidth - slot
            else:
                actuator_latency_alert = False  
            
            #Paso 1: te duermes esperando una alerta 
            alert_received_during_sleep = q4s_node.event.wait(timeout = tiempo_espera)
            if alert_received_during_sleep == False:
                consecutive_alerts = 0 
                state = 0 
                continue
            else:
                if check_alert_valid(q4s_node) == True:
                    print(f"\n[ACTUATOR]{datetime.now().strftime("%H:%M:%S.%f")[:-3]} Me ha llegado una alerta por packet loss\n\tcliente: {q4s_node.packet_loss_up}\n\tserver: {q4s_node.packet_loss_down}\n\tcombinado: {q4s_node.packet_loss_combined}")
                    consecutive_alerts+=1%(MAX_ALERTS_CONSECUTIVES)
                    #Paso 3: Si llegan 3 alertas, te vas al estado 2
                    if consecutive_alerts > 0:
                        state = 1
                        continue
                    else: #consecutive alerts = 3 que es 0 
                        consecutive_alerts = 0
                        state = 2
                        continue
                else: #latency alert 
                    state = 1
                    actuator_latency_alert = True
                    continue
            
        elif state==2:
            #Paso 0: Guardamos la perdida de paquetes con la que llegamos aqui
            state2_packet_loss = q4s_node.packet_loss_combined
            #Paso 1: Ponemos modo ruido
            if actuator_noise_mode == False:
                if set_noise_resist(True) != "OK":
                    state = 0
                    continue
                else:
                    actuator_noise_mode = True
            #esperamos
            time.sleep(tiempo_espera)
            #Paso 2: Comprobamos perdida paquetes
            new_packet_loss = q4s_node.packet_loss_combined

            #Paso 3: Si es peor bajamos un slot de ancho de banda y volvemos a estado 2
            if new_packet_loss > state2_packet_loss and (new_packet_loss-state2_packet_los) > 0.01: #TODO: Consensuar con Nokia el valor 
            #if new_packet_loss > state2_packet_loss and new_packet_loss > state2_packet_loss * (1 + 0.01): #diferencia relativa
                #Se consulta ancho de banda 
                try:
                    coder_actual_and_orig_bandwidth = get_target_bw_orig().split[";"]
                except:
                    state=0
                    continue
                coder_actual_bandwidth,coder_orig_bandwidth = int(coder_actual_and_orig_bandwidth[0]), int(coder_actual_and_orig_bandwidth[1]) 
                #y se pide que baje un slot
                if coder_actual_bandwidth == coder_orig_bandwidth: #no hay congestion
                    actuator_bandwidth -= slot
                    if set_target_bw_orig(actuator_bandwidth) != "OK":
                        state = 0
                        actuator_bandwidth += slot
                        #se puede resetear actuator orig bandwith a coder_orig_bandwidth
                        continue
                else: #hay congestion coder_actual_bandwidth es mas pequeño que el orig                
                    if set_target_bw_orig(coder_actual_bandwidth - slot) != "OK":
                        state = 0
                        continue
                    else:
                        actuator_bandwidth = coder_actual_bandwidth - slot                

                #seguir en estado 2
                state = 2
                continue
            else:#las perdidas se mantienen o bajan
                if actuator_bandwidth < ORIG_BANDWIDTH-(slot/FUENTES):
                    #subirlo hasta llegar a orig_bandwidth                
                    if coder_actual_bandwidth == coder_orig_bandwidth:
                        bandwith_parameter = actuator_bandwidth+slot
                        if set_target_bw_orig(bandwith_parameter) != "OK":
                            state = 0
                            continue
                        else:
                            actuator_bandwidth = bandwith_parameter
                            coder_orig_bandwidth = actuator_bandwidth 
                    else: #Hay congestion en el coder y no podemos subir a tope, subimos a lo que puede el coder
                        if actuator_bandwidth < coder_actual_bandwidth-(slot/FUENTES):
                            bandwith_parameter = coder_actual_bandwidth+slot
                            if set_target_bw_orig(bandwith_parameter) != "OK":
                                state = 0
                                continue
                            else:
                                actuator_bandwidth = bandwith_parameter
                                coder_orig_bandwidth = actuator_bandwidth
                state = 2
                continue

            #Paso 4: Si es mejor vamos a estado 0
            if new_packet_loss <= 0.01: #Si es menor de un 2 por ciento se pasa a estado 0 TODO: Consensuar valor
                state = 0
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
    
    while True:
        print("\n1: Menu Pérdidas")
        print("2: Menu Peticiones")
        print("0: Salir")
        option = input("\nElige una opción: ")

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
                sub_option = input("Elige una opción: ")

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
    