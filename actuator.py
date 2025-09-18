import threading
import time
import q4s_lite
import logging,sys, os
from datetime import datetime
import socket
import configparser

#Parametros q4s
event = threading.Event()
#Parametros del actuador
actuator_alive = False
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

#server_address, server_port = q4s_lite.server_address, q4s_lite.server_port#"127.0.0.1",20001
#client_address, client_port = q4s_lite.client_address, q4s_lite.client_port#"127.0.0.1",20002
server_address= network.get('server_address')
server_port= network.getint('server_port')
client_address= network.get('client_address')
client_port= network.getint('client_port')


print('\nActuator Config params')
print("======================")
print(f"actuator_address,actuator_port = {actuator_host},{actuator_port}")
print(f"server_address,server_port = {server_address},{server_port}")
print(f"client_address,client_port = {client_address},{client_port}")
print(f"insignificant_losses = {insignificant_loses}")
print(f"fuentes = {FUENTES}")
print(f"tam por fuente = {TAM_POR_FUENTE}")
print()

#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_client.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

LATENCY_ALERT= general.getint('LATENCY_ALERT')
PACKET_LOSS_ALERT= general.getfloat('PACKET_LOSS_ALERT')

#FUENTES = 1
slot = FUENTES*TAM_POR_FUENTE #TODO en mayusculas
#ORIG_BANDWIDTH = FUENTES * 6000000
MAX_ALERTS_CONSECUTIVES = 6
DEMO = False
#Test
valores = None

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
    tiempo_espera = q4s_lite.KEEP_ALERT_TIME+1 #TODO: Consensuar este tiempo con JJ, Sergio y Alberto

    #Peticion inicial de ancho de banda
    ORIG_BANDWIDTH = 0
    orig_bandwith_from_coder = False
    try_number = 0
    while not orig_bandwith_from_coder:
        try_number+=1
        try:
            ORIG_BANDWIDTH = get_target_bw_orig().split(";")[2] #TODO coger el tercero (2) que es el de configuracion.
            ORIG_BANDWIDTH = int(ORIG_BANDWIDTH)
            print(f"ORIG_BANDWIDTH {ORIG_BANDWIDTH}")
            orig_bandwith_from_coder = True
        except Exception as e:
            print(f"\n[ACTUATOR] Cant get target bandwidth from coder try number {try_number}\n")
            time.sleep(1)
            continue
    coder_orig_bandwidth = ORIG_BANDWIDTH #el segundo parametro de get_bandwith, originalmente es por configuración
    actuator_bandwidth = coder_orig_bandwidth #El bandwith con el que trabaja el actuador, sobre este restamos slots, etc..
    while actuator_alive:
        if state == 0:
            print(f"\n[ACTUATOR (0)]\n")
            #if actuator_latency_alert == False:#Ignorar alertas de latencia
            #Paso 0: pido ancho de banda y intento subir al original
            try:
                coder_actual_and_orig_bandwidth = get_target_bw_orig().split(";")
            except:
                state=0
                continue
            coder_actual_bandwidth,coder_orig_bandwidth = int(coder_actual_and_orig_bandwidth[0]), int(coder_actual_and_orig_bandwidth[1]) 
            #Subir ancho de banda hasta que llegue al original(ORIG_BANDWIDTH), si es el original no hace nada
            print(f"\n    [ACTUATOR (0)] Actual bw:{coder_actual_bandwidth} Orig bw:{coder_orig_bandwidth}\n")
            if actuator_bandwidth <= ORIG_BANDWIDTH-(slot/FUENTES): #TODO: checkear ese margen
                print("\n    [ACTUATOR (0)]: Estoy por debajo del ancho de banda, lo subo un slot\n")
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
                    
            #else:
            #    actuator_latency_alert = False

            #Paso 1: Si esta en modo ruido lo quitamos
            if actuator_noise_mode == True: #Si esta en modo ruido, lo quito
                print("\n    [ACTUATOR (0)]: Quito el modo ruido\n")
                if set_noise_resist(False) != "OK":
                    state = 0                    
                    continue
                else:
                    actuator_noise_mode = False
            
            #Paso 2: Esperamos:si llega alerta, vamos a estado 1, si no llega nos quedamos en el estado 0
            alert_received_during_sleep = q4s_node.event_actuator.wait(timeout = tiempo_espera)
            if alert_received_during_sleep == False:
                print("\n    [ACTUATOR (0)]: Sin alertas un tramo de paquetes todo bien\n")
                state=0
                continue
            else:
                q4s_node.event_actuator.clear()
                print("\n    [ACTUATOR (0)]: He recibido alerta, paso a estado 1\n")
                #if check_alert_valid(q4s_node) == True:
                print(f"\n[ACTUATOR]{datetime.now().strftime("%H:%M:%S.%f")[:-3]} Me ha llegado una alerta por packet loss\n\tcliente: {q4s_node.packet_loss_up}\n\tserver: {q4s_node.packet_loss_down}\n\tcombinado: {q4s_node.packet_loss_combined}")
                state = 1
                continue
                #else: #La alerta era de latencia
                #    state = 0
                #    actuator_latency_alert = True
                #    continue

        elif state == 1:
            print("\n[ACTUATOR (1)]\n")
            state1_packet_loss = q4s_node.packet_loss_combined
            #if actuator_latency_alert == False:#Ignorar alertas de latencia
            #Paso 0: Bajar un slot 
            try:
                coder_actual_and_orig_bandwidth = get_target_bw_orig().split(";")
            except:
                state=0
                continue
            coder_actual_bandwidth,coder_orig_bandwidth = int(coder_actual_and_orig_bandwidth[0]), int(coder_actual_and_orig_bandwidth[1]) 
            
            if coder_actual_bandwidth == coder_orig_bandwidth: #no hay congestion
                print("\n    [ACTUATOR (1)]: Voy a bajar un slot\n")
                actuator_bandwidth -= slot
                actuator_bandwidth = max(actuator_bandwidth, 1000000)
                if set_target_bw_orig(actuator_bandwidth) != "OK":
                    state = 0
                    actuator_bandwidth += slot
                    #se puede resetear actuator orig bandwith a coder_orig_bandwidth
                    continue
            else: #hay congestion coder_actual_bandwidth es mas pequeño que el orig
                bandwidth_parameter =  coder_actual_bandwidth - slot
                bandwidth_parameter = max(bandwidth_parameter,1000000)             
                if set_target_bw_orig(bandwidth_parameter) != "OK":
                    state = 0
                    continue
                else:
                    #actuator_bandwidth = coder_actual_bandwidth - slot
                    actuator_bandwidth = bandwidth_parameter
            if DEMO:
                if q4s_node.packet_loss_decoration>=0.1:
                    q4s_node.packet_loss_decoration-=0.05
                    print(f"[ACTUATOR] New packet loss decoration {q4s_node.packet_loss_decoration}")
            #else:
            #    actuator_latency_alert = False  
            
            #Paso 1: te duermes esperando una alerta 
            alert_received_during_sleep = q4s_node.event_actuator.wait(timeout = tiempo_espera)
            if alert_received_during_sleep == False:
                print("\n    [ACTUATOR (1)]: Sin alertas durante un tramo, vuelvo a estado 0\n")
                consecutive_alerts = 0 
                state = 0 
                continue
            else:
                q4s_node.event_actuator.clear()
                #if check_alert_valid(q4s_node) == True:
                after_alert_packet_loss = q4s_node.packet_loss_combined
                print("\n    [ACTUATOR (1)]: Alerta durante el sueño, la trato\n")
                print(f"\n[ACTUATOR]{datetime.now().strftime("%H:%M:%S.%f")[:-3]} Me ha llegado una alerta por packet loss\n\tcliente: {q4s_node.packet_loss_up}\n\tserver: {q4s_node.packet_loss_down}\n\tcombinado: {q4s_node.packet_loss_combined}")
                margen = slot/actuator_bandwidth 
                print(f"\nMargen {margen} = {slot}/{actuator_bandwidth} y se va a comparar con {abs(after_alert_packet_loss-state1_packet_loss)}\n")
                if after_alert_packet_loss >= state1_packet_loss: #Empeoras
                    consecutive_alerts+=1 
                elif abs(after_alert_packet_loss-state1_packet_loss) > margen: #Se resetea si mejoras bastante
                    consecutive_alerts = 0
                #Si no mejoras bastante, sigues con el contador de alertas consecutivas iguales
                #TODO: Repetir esto en el estado 2 al perder paquetes
                #Paso 3: Si llegan 3 alertas, te vas al estado 2
                print(f"\nAlertas consecutivas sin mejora: {consecutive_alerts}")
                if consecutive_alerts < MAX_ALERTS_CONSECUTIVES:
                    state = 1
                    continue
                elif consecutive_alerts==MAX_ALERTS_CONSECUTIVES: #consecutive alerts = 3 que es 0 
                    consecutive_alerts = 0
                    state = 2
                    print("\n    [ACTUATOR (1)]: Muchas alertas consecutivas sin mejora, paso al estado 2\n")
                    continue
                #else: #latency alert 
                #    state = 1
                #    actuator_latency_alert = True
                #    continue
            
        elif state==2:
            print("\n[ACTUATOR (2)]\n")
            
            #Paso 0: Guardamos la perdida de paquetes con la que llegamos aqui
            state2_packet_loss = q4s_node.packet_loss_combined
            #Paso 1: Ponemos modo ruido
            if actuator_noise_mode == False:
                print("\n    [ACTUATOR (2)]: Pongo el modo ruido\n")
                if set_noise_resist(True) != "OK":
                    state = 0
                    continue
                else:
                    actuator_noise_mode = True
            #esperamos
            time.sleep(tiempo_espera)
            #Paso 2: Comprobamos perdida paquetes
            new_packet_loss = q4s_node.packet_loss_combined

            #Paso 4: Si es mejor vamos a estado 0
            if new_packet_loss <= insignificant_loses: #Si es menor de un 2 por ciento se pasa a estado 0 TODO: Consensuar valor
                print("\n    [ACTUATOR (2)]: La perdida es insignificante, vuelvo a estado 0\n")
                state = 0
                continue


            #Paso 3: Si es peor bajamos un slot de ancho de banda y volvemos a estado 2
            margen = slot/actuator_bandwidth 
            print(f"\nMargen {margen} = {slot}/{actuator_bandwidth} y se {abs(new_packet_loss- state2_packet_loss )}\n")
            if abs(new_packet_loss-state2_packet_loss) > margen: #TODO: Consensuar con Nokia el valor 
                #Se consulta ancho de banda
                print("\n    [ACTUATOR (2)]: He esperado y ha crecido la perdida, intento bajar ancho de banda\n") 
                try:
                    coder_actual_and_orig_bandwidth = get_target_bw_orig().split(";")
                except:
                    state=0
                    continue
                coder_actual_bandwidth,coder_orig_bandwidth = int(coder_actual_and_orig_bandwidth[0]), int(coder_actual_and_orig_bandwidth[1]) 
                #y se pide que baje un slot
                if coder_actual_bandwidth == coder_orig_bandwidth: #no hay congestion
                    print("\n    [ACTUATOR (2)]: Voy a bajar un slot\n")
                    actuator_bandwidth -= slot
                    actuator_bandwidth = max(actuator_bandwidth, 1000000)
                    if set_target_bw_orig(actuator_bandwidth) != "OK":
                        state = 0
                        actuator_bandwidth += slot
                        #se puede resetear actuator orig bandwith a coder_orig_bandwidth
                        continue
                else: #hay congestion coder_actual_bandwidth es mas pequeño que el orig
                    bandwidth_parameter =  coder_actual_bandwidth - slot
                    bandwidth_parameter = max(bandwidth_parameter,1000000)             
                    if set_target_bw_orig(bandwidth_parameter) != "OK":
                        state = 0
                        continue
                    else:
                        #actuator_bandwidth = coder_actual_bandwidth - slot
                        actuator_bandwidth = bandwidth_parameter                
                
                #seguir en estado 2
                state = 2
                continue
            else:#las perdidas se mantienen o bajan
                #Nuevo resolver bug, no actualizaba coder_actual_bandwidth
                try:
                    coder_actual_and_orig_bandwidth = get_target_bw_orig().split(";")
                except:
                    state=0
                    continue
                coder_actual_bandwidth,coder_orig_bandwidth = int(coder_actual_and_orig_bandwidth[0]), int(coder_actual_and_orig_bandwidth[1]) 
                #################
                if actuator_bandwidth <= ORIG_BANDWIDTH-(slot/FUENTES):
                    print("\n    [ACTUATOR (2)]: He esperado y las perdidas se mantienen o bajan, subo el ancho de banda\n")
                    #print(f"coder_actual_bandwidth = {coder_actual_bandwidth} \ncoder_orig_bandwidth = {coder_orig_bandwidth} \nactuator_bandwidth = {actuator_bandwidth}")
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

            


def main():
    global actuator_alive
    logger.addHandler(client_handler)
    #El actuador es el cliente por defecto, ya que va en el coche
    q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event_actuator=event, config_file=config_file)
    q4s_node.run()
    actuator_alive = True
    actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
    actuator_thread.start()
    
    while True:
        print("\n1: Menu Pérdidas")
        print("2: Menu Peticiones")
        print("9: Repetir menu")
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
                print("\n1: Pierde un 10 por ciento de paquetes")
                print("2: No pierdas paquetes")
                print("3: BER de 50000")
                print("4: BER de 0")
                print("9: Repetir menu")
                print("0: Atrás")
                sub_option = input("Elige una opción: ")

                if sub_option == '0':
                    break
                elif sub_option == '1':
                    q4s_node.packet_loss_decoration += 0.1
                    send_command(f"SET_LOSS:10")
                elif sub_option == '2':
                    q4s_node.packet_loss_decoration = 0
                    send_command(f"SET_LOSS:0")
                elif sub_option == '3':
                    send_command(f"SET_BER:50000")
                elif sub_option == '4':
                    send_command(f"SET_BER:0")
                elif sub_option == "9":
                    continue


        elif option == '2':  # Submenú de peticiones al coder
            while True:
                print("\n1: Petición GET_TARGET_BW_ORIG")
                print("2: Petición SET_TARGET_BW_ORIG")
                print("3: Petición SET_NOISE_RESIST ON")
                print("4: Petición SET_NOISE_RESIST OFF")
                print("5: Petición BER 50000")
                print("6: Petición BER 0")
                print("7: Petición SET_LOSS 10")
                print("8: Petición SET_LOSS 0")
                print("9: Repetir menu")
                print("0: Atrás")
                sub_option = input("Introduce una opción: ")
                
                if sub_option == "1":
                    print(send_command("GET_TARGET_BW_ORIG"))
                elif sub_option == "2":
                    value = int(input("Dime valor de ancho de banda objetivo: "))
                    print(send_command(f"SET_TARGET_BW_ORIG:{value}"))
                elif sub_option == "3":
                    print(send_command(f"SET_NOISE_RESIST:1"))
                elif sub_option == "4":
                    print(send_command(f"SET_NOISE_RESIST:0"))
                elif sub_option == "5":
                    print(send_command(f"SET_BER:50000"))
                elif sub_option == "6":
                    print(send_command(f"SET_BER:0"))
                elif sub_option == "7":
                    print(send_command(f"SET_LOSS:10"))
                elif sub_option == "8":
                    print(send_command(f"SET_LOSS:0"))
                elif sub_option == "9":
                    continue
                elif sub_option == "0":
                    break
        elif option == "9":
            continue


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
    