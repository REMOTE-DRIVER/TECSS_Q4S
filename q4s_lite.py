''' 
NOKIA TECSS
Implementacion de q4s bla bla

Autores:
Juan Ramos Diaz
Juan Jose Guerrero Lopez
'''
import socket
import struct
import threading
import time
import sys,os
import logging
import functools
import random
import configparser
import math

restas = 0
recibidos_global = 0
recibidos_global_resp = 0
# Valores por defecto
DEFAULTS = {
    'GENERAL': {
        'VEHICLE_ID': "0001",
        'PACKETS_PER_SECOND': 30,
        'GLOBAL_SEQ_SIZE': 100,
        'WINDOW_SIZE':100,
        'LATENCY_ALERT': 150,
        'PACKET_LOSS_ALERT': 0.02,
        'NO_INIT': False,
        'OFFSET':0,
        'MEASURES_COMBINATION_STRATEGY':0,
        'REAL_SCENARIO': False,
        'COTTON_TEST': False,
        'MAX_LATENCY_MS': 500
    },
    'NETWORK': {
        'server_address': '127.0.0.1',
        'server_port': 20001,
        'client_address': '127.0.0.1',
        'client_port': 20002,
        'bind_all': True,
        'bind_ip': '0.0.0.0',
        'bind_port': 20004
    }
}

config = configparser.ConfigParser()

# Leer el archivo
config.read_dict(DEFAULTS)  # cargar valores por defecto primero
#config.read(config_file)      # luego sobrescribir con lo del fichero si existe

# Acceder y convertir tipos
general = config['GENERAL']
network = config['NETWORK']

VEHICLE_ID= general.get('VEHICLE_ID')#.strip('"')
PACKETS_PER_SECOND= general.getint('PACKETS_PER_SECOND')
GLOBAL_SEQ_SIZE= general.getint('GLOBAL_SEQ_SIZE')
LATENCY_ALERT= general.getint('LATENCY_ALERT')
PACKET_LOSS_ALERT= general.getfloat('PACKET_LOSS_ALERT')
server_address= network.get('server_address')
server_port= network.getint('server_port')
client_address= network.get('client_address')
client_port= network.getint('client_port')
NO_INIT = general.getboolean('NO_INIT')
OFFSET = general.getint('OFFSET')
MEASURES_COMBINATION_STRATEGY = general.getint('MEASURES_COMBINATION_STRATEGY')
REAL_SCENARIO = general.getboolean('REAL_SCENARIO')
WINDOW_SIZE = general.getint('WINDOW_SIZE')
COTTON_TEST = general.getboolean('COTTON_TEST')
MAX_LATENCY_MS = general.getint('MAX_LATENCY_MS')
BIND_ALL = network.getboolean('bind_all')
BIND_IP = network.get('bind_ip')
BIND_PORT = network.getint('bind_port')

PACKET_FORMAT = f">4sidffffffi{OFFSET}s"  # Formato de los datos
PACKET_SIZE = 52 + OFFSET #bytes

MSG_FORMAT = 'utf-8'
ack_message = "ACK".ljust(4).encode(MSG_FORMAT)
syn_message = "SYN".ljust(4).encode(MSG_FORMAT)
ping_message ="PING".encode(MSG_FORMAT)
resp_message = "RESP".encode(MSG_FORMAT)
disc_message = "DISC".encode(MSG_FORMAT)
reset_message = "RST".ljust(4).encode(MSG_FORMAT)

INIT_CONNECTION_TRIES = 10
MODO_STANDALONE = False  #Para indicar que se ejecuta como libreria, solo se pone a true si se ejecuta desde este modulo

KEEP_ALERT_TIME = max(1,(WINDOW_SIZE / PACKETS_PER_SECOND)) #segundos que estas en estado de alerta a partir del cual vuelve a avisar al actuador, para no avisarle en todos los paquetes
KEEP_ALERT_TIME_PUBLICATOR = 1

#Nueva latencia
LATENCY_CHECKPOINT = [3,5,7,9]# definen crecimiento y diferencia de latencia, jj recomienda de 3,4,5,6
UP_INDEX = 0
DOWN_INDEX = 0
TIME_BETWEEN_PINGS = 1/PACKETS_PER_SECOND 

#Estrategias de combinacion de medidas, la media, la mayor, la menor,no hacer nada, etc...
#x e y son las latencias de cada lado, z es el rol de quien invoca
MEASURE_COMBINATIONS = [lambda x,y,z: (x+y)/2,
                        lambda x,y,z:max(x,y),
                        lambda x,y,z:min(x,y),
                        lambda x,y,z: x if z=="client" else y]

COMBINED_FUNC = MEASURE_COMBINATIONS[MEASURES_COMBINATION_STRATEGY]

#Tiempo en segundos para medir los errores de conexion
CONNECTION_ERROR_TIME_MARGIN = 1

#Configuracion de logging: logger.info (en adelante) en consola y fichero, logger.debug solo en fichero
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)

#Manejador para imprimir por consola
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  
console_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(console_handler)

#Manejador y formato para imprimir en ficheros
formatter = logging.Formatter('%(asctime)s - %(message)s')

server_handler = logging.FileHandler('q4s_server.log',mode='w')
server_handler.setLevel(logging.DEBUG)
server_handler.setFormatter(formatter)

client_handler = logging.FileHandler('q4s_client.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

class q4s_lite_node():

    def __init__(self, role, address, port, target_address, target_port, event_publicator=None,event_actuator=None, config_file=None):
        if not MODO_STANDALONE:
            load_config(config_file)
        #El rol importa para iniciar conex o medir up/down
        self.role = role
        #id del flujo a medir
        if role=="server":
            self.flow_id = 0 
        else:
            self.flow_id = encode_identifier(VEHICLE_ID)
        #udp socket params
        self.address = address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if role=="server": #El cliente no hace bind para reutilizar el socket
            if BIND_ALL:
                self.socket.bind(('0.0.0.0', port)) #Escucha en todas las interfaces porque con ip publica puede no saber a que interfaz escuchar
            else:
                if BIND_PORT == self.port:
                    self.socket.bind((BIND_IP,BIND_PORT))
                else: #En este caso te ha abierto un publicador con un puerto especifico que le dio el proxy
                    self.socket.bind((BIND_IP,self.port))
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 0)
            #self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 0)
            print("Tamaño del búfer de envío establecido a 0.")
        except socket.error as e:
            print(f"Error al establecer el tamaño del búfer: {e}")
        self.target_address = (target_address, target_port)
        #execution check
        self.running=False
        #negotiation stage params
        self.negotiation_rcv=None
        self.negotiation_snd=None
        self.negotiating=False
        self.negotiation_latency_alert = 0
        self.negotiation_packet_loss_alert = 0
        #measurement stage params
        self.hilo_rcv=None
        self.hilo_snd=None
        self.measuring=False
        #measurement params
        self.seq_number = 0
        self.latency_up=0.0
        self.latency_down=0.0
        self.jitter_up=0.0
        self.jitter_down=0.0
        self.packet_loss_up=0.0
        self.packet_loss_down=0.0
        #connection errors
        self.connection_errors = 0
        self.first_connection_error_time = 0
        #average_measures
        self.latency_combined = 0.0
        self.jitter_combined = 0.0
        self.packet_loss_combined = 0.0
        #packet_loss control
        #self.first_packet = False
        self.packets_received = [0] * GLOBAL_SEQ_SIZE #[0] * GLOBAL_SEQ_SIZE
        self.total_received = WINDOW_SIZE #GLOBAL_SEQ_SIZE
        #state
        self.state=[None,None,None] #Es una tupla de nombre estado, timestamp cuando se puso en actuador y timestamp cuando se puso en publicador, ver si la alerta es larga
        #lock para acceso critico
        self.lock = threading.Lock()
        #evento para mandar la señal al modulo de actuacion o publicacion
        self.event_actuator = event_actuator if event_actuator is not None else threading.Event()
        self.event_publicator = event_publicator if event_publicator is not None else threading.Event()
        #Deterioro de latencias y descarte de paquetes
        self.latency_decoration = 0
        self.packet_loss_decoration = 0
        #Offset del paquete para pruebas
        self.offset = b"A" * OFFSET
        #Nueva loss
        self.n_seq_ini = GLOBAL_SEQ_SIZE-WINDOW_SIZE#(0-WINDOW_SIZE)%GLOBAL_SEQ_SIZE
        self.n_seq_fin = 0


        #Se printan los parametros de la pila
        print('Q4s_lite Config params')
        print("======================")
        print(f"VEHICLE_ID = {VEHICLE_ID}")
        print(f"PACKETS_PER_SECOND = {PACKETS_PER_SECOND}")
        print(f"GLOBAL_SEQ_SIZE = {GLOBAL_SEQ_SIZE}")
        print(f"LATENCY_ALERT = {LATENCY_ALERT}")
        print(f"PACKET_LOSS_ALERT = {PACKET_LOSS_ALERT}")
        print(f"server_address,server_port = {server_address},{server_port}")
        print(f"client_address = {client_address}")
        print(f"MEASURES_COMBINATION_STRATEGY = {MEASURES_COMBINATION_STRATEGY}")
        print(f"OFFSET = {OFFSET}" )
        print(f"KEEP_ALERT_TIME={KEEP_ALERT_TIME}")
        print(f"REAL_SCENARIO = {REAL_SCENARIO}")

        print("\nQ4s_lite Execution")
        print("======================")


    def init_connection_server(self):
        logger.info("[INIT CONNECTION] SERVER: Waiting for connection")
        self.socket.settimeout(30)
        while True:
            try:
                data, addr = self.socket.recvfrom(PACKET_SIZE)
                self.target_address = addr
                data_rcvd = struct.unpack(PACKET_FORMAT,data)
                message_type = data_rcvd[0].decode(MSG_FORMAT).strip()
                if "SYN" in message_type:
                    self.socket.settimeout(3)
                    for i in range(INIT_CONNECTION_TRIES): #while True para que siempre espere
                        logger.info(f"[INIT CONNECTION] SERVER: Received connexion attempt")
                        self.flow_id = data_rcvd[9]
                        decoded_identifier = decode_identifier(self.flow_id)
                        logger.info(f"[INIT CONNECTION] SERVER: Vehicle id: {decoded_identifier}")
                        #Responde al syn con ack
                        packet_data=(ack_message,0,time.time(),0.0,0.0,0.0,0.0,0.0,0.0,self.flow_id,self.offset)
                        datos = struct.pack(PACKET_FORMAT,*packet_data)
                        self.socket.sendto(datos,self.target_address)
                        #Ahora espero el ack de vuelta
                        data,_ = self.socket.recvfrom(PACKET_SIZE)
                        data_rcvd = struct.unpack(PACKET_FORMAT,data)
                        message_type = data_rcvd[0].decode(MSG_FORMAT).strip()
                        if "ACK" in message_type:
                            logger.info("[INIT CONNECTION] SERVER: Start")
                            return 0
                        elif "SYN" in message_type:
                            continue
                        else:
                            logger.info("[INIT CONNECTION] SERVER: Error, invalid confirmation")
                            return -1
                else:#Reset te llegan ping o resp del otro extremo, pasas directamente a la fase de medicion
                    self.flow_id = data_rcvd[9]
                    logger.info(f"[RESET CONNECTION] SERVER: Received PING or RESP message, going directly into Measurement stage")
                    return 0
            except socket.timeout:
                logger.info("[INIT CONNECTION] SERVER:Timeout")
                return -1

    def init_connection_client(self):
        logger.info("[INIT CONNECTION] CLIENT: Starting connection")
        #self.flow_id = encode_identifier(VEHICLE_ID) #Lo coge de un fichero
        decoded_identifier = decode_identifier(self.flow_id)
        logger.info(f"[INIT CONNECTION] CLIENT: Vehicle id: {decoded_identifier}")
        retries = 0
        self.socket.settimeout(3)
        timestamp=time.time()
        while retries < INIT_CONNECTION_TRIES: #while True para que lo intente hasta que pueda
        #while True:
            try:
                packet_data=(syn_message,0,time.time(),0.0,0.0,0.0,0.0,0.0,0.0,self.flow_id,self.offset)
                datos = struct.pack(PACKET_FORMAT,*packet_data)
                self.socket.sendto(datos,self.target_address)

                data, _ = self.socket.recvfrom(PACKET_SIZE)
                timestamp_recepcion = time.time()
                data_rcvd = struct.unpack(PACKET_FORMAT,data)
                message_type = data_rcvd[0].decode(MSG_FORMAT).strip()
                if "ACK" in message_type:
                    #Responde ack, se le envia otro ack
                    packet_data=(ack_message,0,time.time(),0.0,0.0,0.0,0.0,0.0,0.0,self.flow_id,self.offset)
                    datos = struct.pack(PACKET_FORMAT,*packet_data)
                    self.socket.sendto(datos,self.target_address)
                    logger.info(f"[INIT CONNECTION] CLIENT {self.socket.getsockname()}: Conexion establecida ha tardado {timestamp_recepcion-timestamp} segundos")
                    return 0
                else:#RESET
                    logger.info("[RESET CONNECTION] CLIENT: Received PING or RESP while initializating connection")
                    return 0
            except socket.timeout:
                retries+=1
                logger.info(f"[INIT CONNECTION] CLIENT: Timeout, reintentando {retries}/{INIT_CONNECTION_TRIES}")
            except ConnectionResetError:
                #Cuando levantas el cliente antes que el server: [WinError 10054] Se ha forzado la interrupción de una conexión existente por el host remoto
                continue
        else:
            logger.info("[INIT CONNECTION] CLIENT: Error, no se puede conectar al servidor")
            return -1

    @staticmethod
    def get_metrics(reception_time,sent_time,last_latency,total_received):
        global UP_INDEX,DOWN_INDEX
        new_latency = ((reception_time-sent_time)*1000)/2 #rtt/2
        #jitter = abs(new_latency-last_latency) #El valor absoluto TODO restar la original, no la smoothed
        try:
            jitter = abs(new_latency-jitter_last_latency) 
        except:
            jitter = abs(new_latency-last_latency)
        jitter_last_latency = new_latency
        #amortiguacion 
        #New latency OJO a los resets de indices
        if new_latency > last_latency + LATENCY_CHECKPOINT[UP_INDEX]:
            smoothed_latency = last_latency + LATENCY_CHECKPOINT[UP_INDEX]
            if UP_INDEX == len(LATENCY_CHECKPOINT)-1:
                pass
            else:
                UP_INDEX +=1
            DOWN_INDEX = 0
        elif new_latency < last_latency - LATENCY_CHECKPOINT[DOWN_INDEX]:
            smoothed_latency = last_latency - LATENCY_CHECKPOINT[DOWN_INDEX]
            if DOWN_INDEX == len(LATENCY_CHECKPOINT)-1:
                pass
            else:
                DOWN_INDEX +=1
            UP_INDEX = 0
        else:
            smoothed_latency = new_latency
            UP_INDEX = 0
            DOWN_INDEX = 0
        #smoothed_latency= new_latency #Comentar esta linea si hago amortiguacion
        #loss
        loss = 1-(total_received/WINDOW_SIZE)
        #print(f"        loss = 1 - ({total_received}/{WINDOW_SIZE})= {loss}")
        if loss < 0:
            loss = 0
        if loss>=1:
            loss = 1
        elif REAL_SCENARIO == False: 
            '''Esta formula solo es valida cuando las perdidas son aleatorias, simetricas e independientes, como las perdidas
            simuladas con clumsy'''
            #loss = 1.0 - math.sqrt(1.0 - loss)
            #p + (1-p)p
            loss = (-2 +math.sqrt(4-4*loss))/-2
        return smoothed_latency,jitter,loss

    def measurement_send_ping(self):
        while self.measuring:
            #Se prepara el paquete
            packet_data=(
                ping_message,
                self.seq_number,
                #time.time(),
                time.perf_counter(),
                self.latency_up,
                self.latency_down,
                self.jitter_up,
                self.jitter_down,
                self.packet_loss_up,
                self.packet_loss_down,
                self.flow_id,
                self.offset
                )
            packet = struct.pack(PACKET_FORMAT, *packet_data)
            
            try:
                with self.lock:#Antes de enviar miro la posicion k
                    
                    self.packets_received[self.seq_number] = 1 #damos por perdido de momento
                    
                    #perdida de paquetes simulada
                    if self.packet_loss_decoration==0:
                        self.socket.sendto(packet, self.target_address)
                        #self.array_lost_marked[k] = (time.perf_counter())
                    elif self.packet_loss_decoration > 0:
                        #self.packet_loss_decoration+=0.02 #Margen de seguridad
                        # Parámetros del algoritmo determinista
                        M = 10000                          # granularidad (más grande = más precisión)
                        A = 2654435761                     # constante de dispersión (Knuth)
                        loss = self.packet_loss_decoration # ej. 0.3 para 30%

                        # Umbral de pérdida (número de valores que serán drop)
                        threshold = int(round(loss * M))   # ej. 0.3 → 3000

                        # Genera un valor pseudo-aleatorio pero determinista basado en seq_number
                        v = (self.seq_number * A) % M

                        # Si v >= threshold → enviamos (perdemos "threshold" valores de cada M)
                        if v >= threshold:
                            self.socket.sendto(packet, self.target_address)

                    #if self.seq_number == GLOBAL_SEQ_SIZE-1:
                    #    print(f"\nSEQ_NUMBER: {self.seq_number}")
                    self.seq_number = (self.seq_number+1)%GLOBAL_SEQ_SIZE
                    #Prueba del algodon, solo manda 10k paquetes, faltaria un sys.exit()
                    #Para probarlo se podria desde aqui acceder al recibidos_global y calcular el porcentaje para que quede mas limpio
                    if COTTON_TEST:
                        if self.seq_number == 0: #Has mandado global seq_size
                            #time.sleep(1)
                            self.measuring=False
                            #self.hilo_snd.join()
                            #self.hilo_rcv.join()
                            print(f"\nPings recibidos:{recibidos_global}, Resps recibidos:{recibidos_global_resp}\n"
                            f"Pings perdidos: {(1-(recibidos_global/GLOBAL_SEQ_SIZE))*100}% "
                            f"Resps perdidos:{(1-(recibidos_global_resp/GLOBAL_SEQ_SIZE))*100}%\n")
                            sys.exit()


                    #Para medir los paquetes que envio en un segundo
                    '''if self.seq_number % PACKETS_PER_SECOND == 0:
                        time_aux = time.perf_counter()
                        print(f"\n[Hilo send]{self.seq_number}:{time_aux}\n")'''
                
                sleep_time = TIME_BETWEEN_PINGS#random.uniform(0, 2*TIME_BETWEEN_PINGS)
                time.sleep(sleep_time)
            except KeyboardInterrupt:
                self.measuring=False
            except ConnectionResetError as e:
                continue
            except Exception as e:
                #Si el so cierra la conexion porque no esta levantado el otro extremo
                #Tambien si se cae el otro extremo
                print(f"[MEASUREMENT SEND PING]: ERROR in sending message {e}")
                continue
        return

    def update_measures(self,data_from_packet):
        #actualizo medidas
        #segun el rol update de unos u otros, porque te pueden llegar ceros de antes de empezar y q los actualices solo para mostrarlo en pantalla y lo pierdas justo depues reescribiendo con cero.
        if self.role == "server":
            self.latency_up = data_from_packet[3]
            self.jitter_up = data_from_packet[5]
            self.packet_loss_up = data_from_packet[7]
            
        else:
            self.latency_down = data_from_packet[4]
            self.jitter_down = data_from_packet[6]
            self.packet_loss_down = data_from_packet[8]

    #def check_alert(self,latency,packet_loss,data): #Quito el data porque ya no envio mensaje, lanzo alerta al actuador
    def check_alert(self,alert_latency,alert_packet_loss, flow_id):
        #Se invoca con booleanos si hay alerta, para comprobar si la alerta es nueva o lleva un rato en alerta
        #logger.debug(f"ESTADO: {self.state}")
        if self.state[0]=="normal":
            if alert_latency or alert_packet_loss:
                self.state[0]="alert"
                if alert_packet_loss:
                    if time.perf_counter()-self.state[1]>=KEEP_ALERT_TIME:
                        self.state[1]=time.perf_counter()
                        self.event_actuator.set()
                        self.event_publicator.set() #Al publicador le interesan todas las alertas, al actuador solo packet loss
                        logger.debug(f"[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                        printalert(f"\n[ALERT]: Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                if alert_latency:
                    if time.perf_counter()-self.state[1]>=KEEP_ALERT_TIME_PUBLICATOR:
                        self.state[2]=time.perf_counter()
                        self.event_publicator.set() #Al publicador le interesan todas las alertas, al actuador solo packet loss
                        logger.debug(f"[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                        printalert(f"\n[ALERT]: Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
        elif self.state[0]=="alert":
            if alert_packet_loss:
                if time.perf_counter()-self.state[1]>=KEEP_ALERT_TIME:
                    self.state[0]="alert"
                    self.state[1] = time.perf_counter()
                    self.state[2] = time.perf_counter()
                    self.event_actuator.set()
                    self.event_publicator.set()
                    logger.debug(f"[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                    printalert(f"\n[ALERT]:   Vehicle_id: {flow_id}Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
            elif alert_latency:
                if time.perf_counter()-self.state[2]>=KEEP_ALERT_TIME_PUBLICATOR:
                    #self.state="alert",time.perf_counter()
                    self.state[0]="alert"
                    self.state[2] = time.perf_counter()
                    self.event_publicator.set()
                    logger.debug(f"[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                    printalert(f"\n[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
            elif self.connection_errors>0:
                if time.perf_counter()-self.state[2]>=KEEP_ALERT_TIME_PUBLICATOR:
                    #Se ha terminado una alerta pero quedan connection errors
                    self.state[0]="alert"
                    self.state[2] = time.perf_counter()
                    self.event_publicator.set()
                    logger.debug(f"[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                    printalert(f"\n[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss} Connection Error: {self.connection_errors}")
                    #print(f"\n[ALERT]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss} Connection Error: {self.connection_errors}\n")
            else:
                self.state[0]="normal"
                self.state[1]=time.perf_counter()
                self.state[2]=time.perf_counter()
                self.event_publicator.set()
                logger.debug(f"[RECOVERY]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                printalert(f"\n[RECOVERY]:  Vehicle_id: {flow_id} Latency:{alert_latency} Packet_loss: {alert_packet_loss}")


    def measurement_receive_message(self):
        global last_print, restas, recibidos_global, recibidos_global_resp
        sent_packets = 0
        paquetes_l_r = 0
        while self.measuring:
            #recibe mensaje bloqueante
            try:
                data,addr = self.socket.recvfrom(PACKET_SIZE)
                timestamp_recepcion = time.perf_counter()
                #Reseteo de connection error
                if self.connection_errors>0:
                    if timestamp_recepcion-self.first_connection_error_time >= CONNECTION_ERROR_TIME_MARGIN:
                        self.connection_errors = 0

                if self.role=="server":
                    self.target_address = addr
                unpacked_data = struct.unpack(PACKET_FORMAT, data)
                message_type = unpacked_data[0].decode(MSG_FORMAT).strip()  # El tipo de mensaje es el primer campo
                if self.role=="server":
                    self.flow_id = unpacked_data[9]
                if message_type == "PING": #PING
                    #Prueba del algodon
                    if COTTON_TEST:
                        recibidos_global+=1
                    #print(f"Recibidos_global={recibidos_global}")
                    self.update_measures(unpacked_data)
                    #logger.debug(f"[MEASURING RECEIVE PING] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]} vehicle_id:{unpacked_data[9]}")
                    packet_data = (resp_message,*unpacked_data[1:])
                    packet = struct.pack(PACKET_FORMAT, *packet_data)
                    self.socket.sendto(packet,self.target_address)
                    
                elif message_type == "RESP": #RESP  
                    #Prueba del algodon
                    if COTTON_TEST:
                        recibidos_global_resp+=1
                    #print(f"Recibidos_global_resp={recibidos_global_resp}")
                    n_seq_actual = unpacked_data[1]              
                    with self.lock:

                        self.packets_received[n_seq_actual] = 0
                        self.total_received += 1
                        self.total_received = min(self.total_received,WINDOW_SIZE+1)
                        #print(f"Llega el paquete {n_seq_actual} total_received={self.total_received}")
                        #la ventana termina en el n_seq_actual, ahora mismo
                        #La ventana empieza en el n_seq_actual - 300, ahora mismo - 1 segundo
                        #si el paquete en n_seq_ini (inico de la ventana) 

                        #Cuando se pierde un paquete se "equivocan" los indices, se ha movido la ventana y detecta
                        #la perdida instantanea
                        self.n_seq_fin = n_seq_actual
                        new_n_seq_ini = (self.n_seq_fin - WINDOW_SIZE+GLOBAL_SEQ_SIZE)%GLOBAL_SEQ_SIZE
                        #tengo q quitar los paquetes recibidos entre n_seq_ini y new_n_seq_ini
                        inicio = self.n_seq_ini
                        fin = new_n_seq_ini
                        #print(f"    Inicio:{inicio} Fin: {fin}", end="")
                        if inicio > fin:
                            #Hemos ciclado
                            if (inicio-fin)>WINDOW_SIZE//2:
                                fin += GLOBAL_SEQ_SIZE
                            else: #Desorden
                                inicio = fin-1 #De esta manera revisas exhaustivamente el desorden_protection
                                if inicio<0:
                                    inicio = 0

                        #fin = (inicio+10)%GLOBAL_SEQ_SIZE
                        #print(f"\ni,f y diferencia: {inicio},{fin} y {fin-inicio}")
                        #print(f"====> Inicio:{inicio} Fin: {fin}")
                        restas = 0
                        for i in range(inicio,fin):
                            j = i%GLOBAL_SEQ_SIZE
                            if self.packets_received[j] == 0:
                                self.total_received -= 1
                                restas+=1
                                self.packets_received[j] = 2 #Proteccion frente al desorden_protection de llegada de paquetes, solo se cuenta una vez

                        self.n_seq_ini = new_n_seq_ini
                        #print(f"    Restas: {restas}")
                        
                        #logger.debug(f"[MEASURING RECEIVE RESP] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]} vehicle_id:{unpacked_data[9]}")
                        
                        if self.role=="server":
                            self.latency_down,self.jitter_down,self.packet_loss_down = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_down,self.total_received)
                            #logger.debug(f"[MEASURING (down)] Latency:{self.latency_down:.10f} Jitter: {self.jitter_down:.10f} Packet_loss: {self.packet_loss_down:.3f}")
                        elif self.role=="client":
                            self.latency_up,self.jitter_up,self.packet_loss_up = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_up,self.total_received)
                            #logger.debug(f"[MEASURING (up)] Latency:{self.latency_up:.10f} Jitter: {self.jitter_up:.10f} Packet_loss: {self.packet_loss_up:.3f}")    
                        
                        #Combinacion de medidas
                        self.latency_combined = COMBINED_FUNC(self.latency_up,self.latency_down,self.role)
                        self.packet_loss_combined = COMBINED_FUNC(self.packet_loss_up,self.packet_loss_down,self.role)
                        self.jitter_combined = COMBINED_FUNC(self.jitter_up,self.jitter_down,self.role)
                        
                        decoded_identifier = decode_identifier(unpacked_data[9])

                        #Comprobar que funciona bien
                        if self.latency_combined>=MAX_LATENCY_MS: #Si la latencia es en un sentido, solo mido la mitad
                            if self.connection_errors == 0:
                                self.first_connection_error_time = time.perf_counter()
                            self.connection_errors+=1
                            #if time.perf_counter()-self.first_connection_error_time >= CONNECTION_ERROR_TIME_MARGIN:
                            #    self.connection_errors = 0
                                
                        print(f"[MEASURING:{decoded_identifier}] Lat:{self.latency_combined:.6f} Loss: {self.packet_loss_combined:.3f} Jitter: {self.jitter_combined:.3f} Conn: {self.connection_errors:3d}", end="\r")
                        #print(
                        #f"[MEASURING:{decoded_identifier}]"
                        #f" Lat:{self.latency_combined:.6f} Loss: {self.packet_loss_combined:.3f} Jitter: {self.jitter_combined:.3f}"
                        ###f" outstanding: {outstanding}"
                        ###f" tail: {self.tail_alpha}"
                        ##f" Transit:{self.max_transit_packets:3d} "
                        #f" Recv:{self.total_received:4d}"
                        #f" ini,fin:{self.n_seq_ini:4d},{self.n_seq_fin:4d}"
                        ##f" pps:{PACKETS_PER_SECOND:3d}"
                        #f" restas: {restas:4d}"
                        ####f"falso_positivo:{self.falsos_positivos:3d} "
                        ####f"tiempo recuperacion:{self.lost_to_recover[n_seq_actual]}"
                        ###f" l-r:{self.lost_to_recover[n_seq_actual]:.6f} "
                        ##f" l-r n:{paquetes_l_r:4d} "
                        ####f" Recibido/Mirando:{n_seq_actual:4d}({self.packets_received[n_seq_actual]})/{self.looking_packet:4d}({self.packets_received[self.looking_packet]}),"
                        ####f" Reco_ratio:{self.lost_recovered}/{self.lost_marked}={recovery_ratio}"
                        ##, end="\r")
                        #)
                        self.check_alert(self.latency_combined>=LATENCY_ALERT,self.packet_loss_combined>=PACKET_LOSS_ALERT, decoded_identifier)
                        
                        recv_end=time.perf_counter()
                        self.process_time = recv_end - timestamp_recepcion

            except KeyboardInterrupt:
                self.measuring=False
            except (ConnectionResetError,socket.timeout):
                #No esta levantado el otro extremo
                if self.connection_errors == 0:
                    self.first_connection_error_time = time.perf_counter()                    
                    #print("\n")
                self.connection_errors+=1
                if time.perf_counter()-self.state[2]>=KEEP_ALERT_TIME_PUBLICATOR:
                    self.state[0] = "alert"
                    self.state[2] = time.perf_counter()
                    self.event_publicator.set()#El primer error de conexion emite una alerta
                    #print()
                    decoded_identifier = decode_identifier(self.flow_id)
                    #printalert(f"[ALERT] CONNECTION ERROR Vehicle_id: {decoded_identifier} Conn: {self.connection_errors}")
                    #print(f"\n[ALERT] CONNECTION ERROR Vehicle_id: {decoded_identifier} Conn: {self.connection_errors}\n")
                '''if self.connection_errors == 0:
                    self.first_connection_error_time = time.perf_counter()                    
                    #print("\n")
                self.connection_errors+=1'''
                try:
                    printalert(f"[ALERT] CONNECTION ERROR Vehicle_id: {decoded_identifier}  in last {CONNECTION_ERROR_TIME_MARGIN} second: {self.connection_errors}\t\t", end="\r") 
                    #print(f"\n[ALERT2] CONNECTION ERROR Vehicle_id: {decoded_identifier}  in last {CONNECTION_ERROR_TIME_MARGIN} second: {self.connection_errors}\t\t", end="\n") 
                except:
                    continue
                if time.perf_counter()-self.first_connection_error_time >= CONNECTION_ERROR_TIME_MARGIN:
                    self.connection_errors = 0
                continue
            except Exception as error:
                print(f"Error recibiendo mensajes {error}")
                continue
        self.socket.close()
        print("\n[MEASURING] END")
        return

        

    def run(self):
        #try:
        #inicio conexion
        self.running = True
        if NO_INIT == False:
            if self.role=="server":
                init = self.init_connection_server()
            elif self.role=="client":
                init = self.init_connection_client()
            else:
                init = -1
        else:
            init = 0
        if init == 0:                
            socket_timeout = (MAX_LATENCY_MS/1000)*2#0.300 # Acordado en Valencia, ctag frena el coche con 250 milis sin mensajes
            self.socket.settimeout(socket_timeout)
            
            self.hilo_rcv = threading.Thread(target=self.measurement_receive_message, daemon=True, name="hilo_rcv")
            self.hilo_snd = threading.Thread(target=self.measurement_send_ping, daemon=True, name="hilo_snd")
            
            actual_time = time.perf_counter()
            self.state=["normal",actual_time,actual_time]
            self.first_connection_error_time = actual_time
            self.measuring = True
            if self.role=="server":
                self.hilo_rcv.start()
                self.hilo_snd.start()
            else:
                self.hilo_snd.start()
                self.hilo_rcv.start()
            print("[MEASUREMENT PHASE] Press ctrl+c to stop")


        else:
            self.running=False
            print("Conexion fallida")

def encode_identifier(identifier: str) -> int:
    if len(identifier) != 4:
        raise ValueError(f"El identificador debe tener exactamente 4 caracteresy tiene {len(identifier)}")
    return int.from_bytes(identifier.encode('utf-8'), byteorder='big')

def decode_identifier(number: int) -> str:
    return number.to_bytes(4, byteorder='big').decode('utf-8')

def printalert(*args, **kwargs):
    if MODO_STANDALONE:
        print(*args, **kwargs)

def load_config(config_file):
    global VEHICLE_ID,PACKETS_PER_SECOND,GLOBAL_SEQ_SIZE,LATENCY_ALERT,PACKET_LOSS_ALERT, \
    server_address, server_port, client_address, client_port, NO_INIT, \
    KEEP_ALERT_TIME, KEEP_ALERT_TIME_PUBLICATOR, TIME_BETWEEN_PINGS,MEASURES_COMBINATION_STRATEGY,COMBINED_FUNC, \
    PACKET_FORMAT, PACKET_SIZE, OFFSET, REAL_SCENARIO, WINDOW_SIZE, COTTON_TEST, BIND_ALL, BIND_IP, BIND_PORT, \
    MAX_LATENCY_MS

    config = configparser.ConfigParser()

    # Leer el archivo
    #config.read_dict(DEFAULTS)  # cargar valores por defecto primero
    config.read(config_file)      # luego sobrescribir con lo del fichero si existe

    # Acceder y convertir tipos
    general = config['GENERAL']
    network = config['NETWORK']

    VEHICLE_ID= general.get('VEHICLE_ID')#.strip('"')
    PACKETS_PER_SECOND= general.getint('PACKETS_PER_SECOND')
    GLOBAL_SEQ_SIZE= general.getint('GLOBAL_SEQ_SIZE')
    LATENCY_ALERT= general.getint('LATENCY_ALERT')
    PACKET_LOSS_ALERT= general.getfloat('PACKET_LOSS_ALERT')
    server_address= network.get('server_address')
    server_port= network.getint('server_port')
    client_address= network.get('client_address')
    client_port= network.getint('client_port')
    NO_INIT = general.getboolean('NO_INIT')
    MEASURES_COMBINATION_STRATEGY = general.getint('MEASURES_COMBINATION_STRATEGY')
    OFFSET = general.getint('OFFSET')
    REAL_SCENARIO = general.getboolean('REAL_SCENARIO')
    WINDOW_SIZE = general.getint('WINDOW_SIZE')
    COTTON_TEST = general.getboolean('COTTON_TEST')
    MAX_LATENCY_MS = general.getint('MAX_LATENCY_MS')
    BIND_ALL = network.getboolean('bind_all')
    BIND_IP = network.get('bind_ip')
    BIND_PORT = network.getint('bind_port')

    

    KEEP_ALERT_TIME = max(1,(WINDOW_SIZE / PACKETS_PER_SECOND)) #segundos que estas en estado de alerta a partir del cual vuelve a avisar al actuador, para no avisarle en todos los paquetes
    KEEP_ALERT_TIME_PUBLICATOR = 1
    

    TIME_BETWEEN_PINGS = 1/PACKETS_PER_SECOND 

    COMBINED_FUNC = MEASURE_COMBINATIONS[MEASURES_COMBINATION_STRATEGY]

    PACKET_FORMAT = f">4sidffffffi{OFFSET}s"  # Formato de los datos
    PACKET_SIZE = 52 + OFFSET #bytes

if __name__=="__main__":
    main_run = True
    #os.system('cls' if os.name == 'nt' else 'clear')
    MODO_STANDALONE = True

    if len(sys.argv)<2:
        print("Usage")

    elif len(sys.argv)==2 or len(sys.argv)==3:
        if len(sys.argv)==3:
            config_file = sys.argv[2]
        else:
            config_file = "q4s_lite_config.ini"

        if not (os.path.exists(config_file)):
            print("\n[Q4S Lite CONFIG] Config file not found using default configuration values\n")

        load_config(config_file)
        if sys.argv[1] == "-s":            
            logger.addHandler(server_handler)
            q4s_node = q4s_lite_node("server",server_address, server_port, client_address, client_port)
            q4s_node.run()
            try:
                while q4s_node.running:#Aqui se puede poner menu de control con simulacion de perdidas etc...
                    #time.sleep(0.1)
                    #print("\n1: Empeora latencia")
                    #print("2: Mejora latencia")
                    print("\n1: Pierde un 10 por ciento mas de paquetes")
                    print("2: No pierdas paquetes")
                    print("0: Atrás\n")
                    print("\nElige una opción: \n")
                    sub_option = input()                   

                    if sub_option == '0':
                        break
                    elif sub_option == '1':
                        #q4s_node.latency_decoration += 0.1
                        q4s_node.packet_loss_decoration += 0.1
                    elif sub_option == '2':
                        #q4s_node.latency_decoration = 0
                        q4s_node.packet_loss_decoration = 0
                    elif sub_option == '3':
                        q4s_node.packet_loss_decoration += 0.1
                    elif sub_option == '4':
                        q4s_node.packet_loss_decoration = 0
            except KeyboardInterrupt:
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()
            print("\nYou can see q4s_server.log for viewing execution")
        elif sys.argv[1] == "-c":
            logger.addHandler(client_handler)
            q4s_node = q4s_lite_node("client",client_address, client_port, server_address, server_port)
            q4s_node.run()
            try:
                while q4s_node.running:#Aqui se puede poner menu de control con simulacion de perdidas etc...
                    print("\n1: Pierde un 10 por ciento mas de paquetes")
                    print("2: No pierdas paquetes")
                    print("0: Atrás\n")
                    print("\nElige una opción: \n")
                    sub_option = input() 

                    if sub_option == '0':
                        break
                    elif sub_option == '1':
                        #q4s_node.latency_decoration += 0.1
                        q4s_node.packet_loss_decoration += 0.1
                    elif sub_option == '2':
                        #q4s_node.latency_decoration = 0
                        q4s_node.packet_loss_decoration = 0
            except KeyboardInterrupt:
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()
            print("\nYou can see q4s_client.log for viewing execution")
        else:
            print("Opcion no reconocida\nUsage:  ")
    else:
        print("Too much arguments\nUsage:  ")


