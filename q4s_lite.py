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

#Paquete con tipo_mensaje,num secuencia, timestamp, latencia_up/down, jitter_up/down, packet_loss_up/down 
#Tipos de mensaje: SYN, ACK, PING, RESP, DISC
PACKET_FORMAT = ">4sidffffff"  # Formato de los datos
PACKET_SIZE = 48 #bytes

MSG_FORMAT = 'utf-8'
ack_message = "ACK".ljust(4).encode(MSG_FORMAT)
syn_message = "SYN".ljust(4).encode(MSG_FORMAT)
ping_message ="PING".encode(MSG_FORMAT)
resp_message = "RESP".encode(MSG_FORMAT)
disc_message = "DISC".encode(MSG_FORMAT)

NEGOTIATION_TIME = 5 #Dependera de lo que tarde en limpiarse una ventana de packet loss

PACKETS_PER_SECOND = 30


PACKET_LOSS_PRECISSION = 100 #Precision de los paquetes perdidos
LATENCY_ALERT = 295 #milisegundos
PACKET_LOSS_ALERT = 0.05 #tanto por 1
KEEP_ALERT_TIME = (PACKET_LOSS_PRECISSION / PACKETS_PER_SECOND) #1 #segundos que estas en estado de alerta a partir del cual vuelve a avisar al actuador, para no avisarle en todos los paquetes
#deberia ser lo que tardas en que pase la ventana de packet_loss
print(f"KEEP_ALERT_TIME={KEEP_ALERT_TIME}")
#Estrategias de combinacion de latencia_OLD
#SMOOTHING_PARAM = 20#segun la estrategia, es el parametro n o alfa (numero de paquetes hasta latencia maxima, o factor de suavizado)
#TIME_TO_GET_LATENCY = 1#Segundos hasta llegar a la latencia real
#TIME_BETWEEN_PINGS = 1/(SMOOTHING_PARAM*TIME_TO_GET_LATENCY)

#Nueva latencia
LATENCY_CHECKPOINT = [3,5,7,9]# definen crecimiento y diferencia de latencia, jj recomienda de 3,4,5,6
UP_INDEX = 0
DOWN_INDEX = 0
TIME_BETWEEN_PINGS = 1/PACKETS_PER_SECOND #30 paquetes por segundo

#Estrategias de combinacion de medidas, la media, la mayor, la menor,no hacer nada, etc...
#x e y son las latencias de cada lado, z es el rol de quien invoca
MEASURE_COMBINATIONS = [lambda x,y,z: (x+y)/2,
                        lambda x,y,z:max(x,y),
                        lambda x,y,z:min(x,y),
                        lambda x,y,z: x if z=="client" else y]
MEASURE_COMBINATION_STRATEGY = 0
COMBINED_FUNC = MEASURE_COMBINATIONS[MEASURE_COMBINATION_STRATEGY]


server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 20002

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

    def __init__(self, role, address, port, target_address, target_port, event=threading.Event()):
        #El rol importa para iniciar conex o medir up/down
        self.role = role 
        #udp socket params
        self.address = address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((address, port))
        self.target_address = (target_address, target_port)
        #execution check
        self.running=False
        #measurement stage params
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
        #average_measures
        self.latency_combined = 0.0
        self.jitter_combined = 0.0
        self.packet_loss_combined = 0.0
        #packet_loss control
        self.packets_received = [0] * PACKET_LOSS_PRECISSION
        self.total_received = PACKET_LOSS_PRECISSION
        #state
        self.state=None,None #Es una tupla de nombre estado, timestamp cuando se puso, ver si la alerta es larga
        #lock para acceso critico
        self.lock = threading.Lock()
        #evento para mandar la señal al modulo de actuacion o publicacion
        self.event = event
        #Deterioro de latencias y descarte de paquetes
        self.latency_decoration = 0
        self.packet_loss_decoration = 0

    def init_connection_server(self):
        #print("[INIT CONNECTION] SERVER: Waiting for connection")
        logger.info("[INIT CONNECTION] SERVER: Waiting for connection")
        self.socket.settimeout(15)
        try:
            data, _ = self.socket.recvfrom(PACKET_SIZE)
            data_rcvd = struct.unpack(PACKET_FORMAT,data)
            message_type = data_rcvd[0].decode(MSG_FORMAT).strip()
            if "SYN" in message_type:
                for i in range(3):
                    logger.info(f"[INIT CONNECTION] SERVER: Received connexion attempt")
                    #Responde al syn con ack
                    packet_data=(ack_message,0,time.time(),0.0,0.0,0.0,0.0,0.0,0.0)
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
        except socket.timeout:
            logger.info("[INIT CONNECTION] SERVER:Timeout")
            return -1

    def init_connection_client(self):
        logger.info("[INIT CONNECTION] CLIENT: Starting connection")
        retries = 0
        self.socket.settimeout(3)
        timestamp=time.time()
        while retries < 3:
            try:
                packet_data=(syn_message,0,time.time(),0.0,0.0,0.0,0.0,0.0,0.0)
                datos = struct.pack(PACKET_FORMAT,*packet_data)
                self.socket.sendto(datos,self.target_address)

                data, _ = self.socket.recvfrom(PACKET_SIZE)
                timestamp_recepcion = time.time()
                data_rcvd = struct.unpack(PACKET_FORMAT,data)
                message_type = data_rcvd[0].decode(MSG_FORMAT).strip()
                if "ACK" in message_type:
                    #Responde ack, se le envia otro ack
                    packet_data=(ack_message,0,time.time(),0.0,0.0,0.0,0.0,0.0,0.0)
                    datos = struct.pack(PACKET_FORMAT,*packet_data)
                    self.socket.sendto(datos,self.target_address)
                    logger.info(f"[INIT CONNECTION] CLIENT: Conexion establecida ha tardado {timestamp_recepcion-timestamp} segundos")
                    return 0
                else:
                    logger.info("[INIT CONNECTION] CLIENT: Respuesta invalida")
            except socket.timeout:
                retries+=1
                logger.info(f"[INIT CONNECTION] CLIENT: Timeout, reintentando {retries}/3")
            except ConnectionResetError:
                #Cuando levantas el cliente antes que el server: [WinError 10054] Se ha forzado la interrupción de una conexión existente por el host remoto
                continue
        else:
            logger.info("[INIT CONNECTION] CLIENT: Error, no se puede conectar al servidor")
            return -1

    def negotiation_send(self): #simplificar para la negociacion
        while self.negotiating:
            #Se prepara el paquete
            packet_data=(
                ping_message,
                self.seq_number,
                time.time(),
                self.latency_up,
                self.latency_down,
                self.jitter_up,
                self.jitter_down,
                self.packet_loss_up,
                self.packet_loss_down
                )
            packet = struct.pack(PACKET_FORMAT, *packet_data)
            try:
                self.socket.sendto(packet, self.target_address)
                #self.socket.sendto(packet, self.target_address)
                logger.debug(f"[NEGOTIATING SEND PING] n_seq:{packet_data[1]}: lat_up:{packet_data[3]} lat_down:{packet_data[4]} jit_up:{packet_data[5]} jit_down:{packet_data[6]} pl_up:{packet_data[7]} pl_down:{packet_data[8]}")
                with self.lock:
                    self.total_received-=self.packets_received[self.seq_number]
                    self.packets_received[self.seq_number] = 1
                self.seq_number = (self.seq_number+1)%PACKET_LOSS_PRECISSION
                #Packet loss strategy: Como mido por tandas, primero no mido, luego si, luego no, otra vez si... reseteo el total_received
                if self.seq_number == 0:
                    self.total_received = PACKET_LOSS_PRECISSION
                time.sleep(TIME_BETWEEN_PINGS)#Esto es la cadencia de paquetes por segundo, configurable tambien
                #responsividad es packetloss_precission/cadencia
            except KeyboardInterrupt:
                self.measuring=False
            except Exception as e:
                #Si el so cierra la conexion porque no esta levantado el otro extremo
                #Tambien si se cae el otro extremo
                print(f"[NEGOTIATING SEND PING]: ERROR in sending message {e}")
                continue
        return

    def negotiation_receive(self):
        while self.negotiating:
            #recibe mensaje bloqueante
            try:
                data,addr = self.socket.recvfrom(PACKET_SIZE)
                #timestamp_recepcion solo se usa para medir, es decir si el mensaje es tipo resp, aqui es mas preciso pero se puede mover para optimizar el proceso
                timestamp_recepcion = time.time()
                unpacked_data = struct.unpack(PACKET_FORMAT, data)
                message_type = unpacked_data[0].decode(MSG_FORMAT).strip()  # El tipo de mensaje es el primer campo
                if message_type == "PING": #PING
                    self.update_measures(unpacked_data)
                    logger.debug(f"[NEGOTIATING RECEIVE PING] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]}")
                    packet_data = (resp_message,*unpacked_data[1:])#,unpacked_data[1],unpacked_data[2],unpacked_data[3],unpacked_data[4],unpacked_data[5],unpacked_data[6],unpacked_data[7],unpacked_data[8])
                    packet = struct.pack(PACKET_FORMAT, *packet_data)
                    self.socket.sendto(packet,self.target_address)
                    logger.debug(f"[NEGOTIATING CONTEST RESP] n_seq:{packet_data[1]}: lat_up:{packet_data[3]} lat_down:{packet_data[4]} jit_up:{packet_data[5]} jit_down:{packet_data[6]} pl_up:{packet_data[7]} pl_down:{packet_data[8]}")
                elif message_type == "RESP": #RESP
                    #actualizo el packet received                    
                    with self.lock:
                        self.packets_received[unpacked_data[1]]=0
                        #lo puedo poner a 1 para medir antes y no esperar tanto entre mediciones
                        #self.total_received+=1 #self.packets_received[unpacked_data[1]]                    
                    logger.debug(f"[NEGOTIATING RECEIVE RESP] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]}")
                    
                    if self.role=="server":
                        self.latency_down,self.jitter_down,self.packet_loss_down = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_down,self.total_received)
                        logger.debug(f"[NEGOTIATING (down)] Latency:{self.latency_down:.10f} Jitter: {self.jitter_down:.10f} Packet_loss: {self.packet_loss_down:.3f}")
                    elif self.role=="client":
                        self.latency_up,self.jitter_up,self.packet_loss_up = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_up,self.total_received)
                        logger.debug(f"[NEGOTIATING (up)] Latency:{self.latency_up:.10f} Jitter: {self.jitter_up:.10f} Packet_loss: {self.packet_loss_up:.3f}")    
                    
                    #Combinacion de medidas
                    self.latency_combined = COMBINED_FUNC(self.latency_up,self.latency_down,self.role)
                    self.packet_loss_combined = COMBINED_FUNC(self.packet_loss_up,self.packet_loss_down,self.role)
                    if self.latency_combined >= LATENCY_ALERT:
                        self.negotiation_latency_alert += 1
                        print(f"[NEGOTIATING ALERT]: Latency alert {self.latency_combined}")
                    if self.packet_loss_combined >= PACKET_LOSS_ALERT:
                        self.negotiation_packet_loss_alert += 1
                        print(f"[NEGOTIATING ALERT]: Latency alert {self.packet_loss_combined}")
                    

            except KeyboardInterrupt:
                self.negotiating=False
            except socket.timeout:
                self.negotiating = False
                print("\nConection timeout during negotiation")
            except ConnectionResetError as e:
                #Si el so cierra la conexion porque no esta levantado el otro extremo
                #Tambien si se cae el otro extremo, esto ocurre cuando lo pruebo en local, en dos maquinas se podra gestionar bien TODO
                #Esto ocurre en cuanto se corta la conexion
                #TODO: Podria volver al init conection para esperar al otro extremo
                self.negotiating = False
                print("\nConection error during negotiation")
                
                #continue
            except Exception as error:
                #pass
                #print(f"Error recibiendo mensajes {error}")#suelen entrar timeouts, tratar en el futuro
                #self.measuring = False
                continue
        #self.socket.close()
        print("\n[NEGOTIATION] END")
        return



    @staticmethod
    def get_metrics(reception_time,sent_time,last_latency,total_received):
        global UP_INDEX,DOWN_INDEX
        new_latency = ((reception_time-sent_time)*1000)/2 #rtt/2
        jitter = abs(new_latency-last_latency) #El valor absoluto
        #amortiguacion 
        #smoothed_latency = SMOOTHING_PARAM * new_latency + (1 - SMOOTHING_PARAM) * last_latency
        #smothed_latency = last_latency + ((new_latency - last_latency) / SMOOTHING_PARAM)
        
        #topes = [3,5,7,9]# definen crecimiento y diferencia de latencia, jj recomienda de 3,4,5,6
        #UP_INDEX = 0
        #indice_bajada = 0
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

        #loss
        loss=((PACKET_LOSS_PRECISSION-total_received)/PACKET_LOSS_PRECISSION)
        #print(total_received, loss)
        if loss < 0:
            loss = 0
        #print(smothed_latency,jitter,loss)
        return smoothed_latency,jitter,loss

    def measurement_send_ping(self):
        while self.measuring:
            #Se prepara el paquete
            packet_data=(
                ping_message,
                self.seq_number,
                time.time(),
                self.latency_up,
                self.latency_down,
                self.jitter_up,
                self.jitter_down,
                self.packet_loss_up,
                self.packet_loss_down
                )
            packet = struct.pack(PACKET_FORMAT, *packet_data)
            try:
                #perdida de paquetes simulada
                if self.packet_loss_decoration==0:
                    self.socket.sendto(packet, self.target_address)
                elif self.packet_loss_decoration>0:
                    if random.random()>self.packet_loss_decoration:
                        self.socket.sendto(packet, self.target_address)
                #self.socket.sendto(packet, self.target_address)
                logger.debug(f"[MEASURING SEND PING] n_seq:{packet_data[1]}: lat_up:{packet_data[3]} lat_down:{packet_data[4]} jit_up:{packet_data[5]} jit_down:{packet_data[6]} pl_up:{packet_data[7]} pl_down:{packet_data[8]}")
                with self.lock:
                    self.total_received-=self.packets_received[self.seq_number]
                    self.packets_received[self.seq_number] = 1
                self.seq_number = (self.seq_number+1)%PACKET_LOSS_PRECISSION
                #Packet loss strategy: Como mido por tandas, primero no mido, luego si, luego no, otra vez si... reseteo el total_received
                if self.seq_number == 0:
                    #print(f"\nSe han enviado 100 paquetes y se resetea total received que ahora vale {self.total_received}\n")
                    self.total_received = PACKET_LOSS_PRECISSION

                time.sleep(TIME_BETWEEN_PINGS)#Esto es la cadencia de paquetes por segundo, configurable tambien
                #responsividad es packetloss_precission/cadencia
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
    def check_alert(self,alert_latency,alert_packet_loss):
        #Se invoca con booleanos si hay alerta, para comprobar si la alerta es nueva o lleva un rato en alerta
        '''if alert_latency or alert_packet_loss:
            if self.state[0]=="normal":
                self.state="alert",time.time()
                if self.event != None:
                    self.event.set()
                logger.debug(f"[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                print(f"\n[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
            elif self.state[0]=="alert":
                if time.time()-self.state[1]>=KEEP_ALERT_TIME:#Solo comprueba si ha pasado x tiempo, esto se puede comprobar antes de invocar
                    self.state="alert",time.time()
                    if self.event != None:
                        self.event.set()
                    logger.debug(f"[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                    print(f"\n[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
        elif time.time()-self.state[1]>=KEEP_ALERT_TIME:
            #Cambiar estado a normal
            pass'''
        logger.debug(f"ESTADO: {self.state}")
        if self.state[0]=="normal":
            if alert_latency or alert_packet_loss:
                self.state="alert",time.perf_counter()
                self.event.set()
                logger.debug(f"[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                print(f"\n[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
        elif self.state[0]=="alert":
            if time.perf_counter()-self.state[1]>=KEEP_ALERT_TIME:#Solo comprueba si ha pasado x tiempo, esto se puede comprobar antes de invocar
                if alert_latency or alert_packet_loss:
                    self.state="alert",time.perf_counter()
                    self.event.set()
                    logger.debug(f"[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                    print(f"\n[ALERT]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")
                else:
                    self.state="normal",time.perf_counter()
                    logger.debug(f"[RECOVERY]: Latency:{alert_latency} Packet_loss: {alert_packet_loss}")

    def measurement_receive_message(self):
        while self.measuring:
            #recibe mensaje bloqueante
            try:
                data,addr = self.socket.recvfrom(PACKET_SIZE)
                #timestamp_recepcion solo se usa para medir, es decir si el mensaje es tipo resp, aqui es mas preciso pero se puede mover para optimizar el proceso
                timestamp_recepcion = time.time()
                unpacked_data = struct.unpack(PACKET_FORMAT, data)
                message_type = unpacked_data[0].decode(MSG_FORMAT).strip()  # El tipo de mensaje es el primer campo
                if message_type == "PING": #PING
                    self.update_measures(unpacked_data)
                    logger.debug(f"[MEASURING RECEIVE PING] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]}")
                    packet_data = (resp_message,*unpacked_data[1:])#,unpacked_data[1],unpacked_data[2],unpacked_data[3],unpacked_data[4],unpacked_data[5],unpacked_data[6],unpacked_data[7],unpacked_data[8])
                    packet = struct.pack(PACKET_FORMAT, *packet_data)
                    self.socket.sendto(packet,self.target_address)
                    logger.debug(f"[MEASURING CONTEST RESP] n_seq:{packet_data[1]}: lat_up:{packet_data[3]} lat_down:{packet_data[4]} jit_up:{packet_data[5]} jit_down:{packet_data[6]} pl_up:{packet_data[7]} pl_down:{packet_data[8]}")
                elif message_type == "RESP": #RESP
                    #actualizo el packet received                    
                    with self.lock:
                        self.total_received += self.packets_received[unpacked_data[1]]
                        #self.packets_received[unpacked_data[1]]=0
                        #lo puedo poner a 1 para medir antes y no esperar tanto entre mediciones
                        #self.total_received+=1 #self.packets_received[unpacked_data[1]]                    
                    logger.debug(f"[MEASURING RECEIVE RESP] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]}")
                    
                    if self.role=="server":
                        self.latency_down,self.jitter_down,self.packet_loss_down = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_down,self.total_received)
                        logger.debug(f"[MEASURING (down)] Latency:{self.latency_down:.10f} Jitter: {self.jitter_down:.10f} Packet_loss: {self.packet_loss_down:.3f}")
                    elif self.role=="client":
                        self.latency_up,self.jitter_up,self.packet_loss_up = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_up,self.total_received)
                        logger.debug(f"[MEASURING (up)] Latency:{self.latency_up:.10f} Jitter: {self.jitter_up:.10f} Packet_loss: {self.packet_loss_up:.3f}")    
                    
                    #Combinacion de medidas
                    self.latency_combined = COMBINED_FUNC(self.latency_up,self.latency_down,self.role)
                    self.packet_loss_combined = COMBINED_FUNC(self.packet_loss_up,self.packet_loss_down,self.role)
                    
                    #Posible TODO: Printar y comprobar alertas cada n paquetes, los necesarios para dar una alarma cada SMOOTHING_PARAM Paquetes
                    #mejor llamar mucho y comprobarlo dentro, en caso de fallo llegan pocos recoveries y puedes perder tiempo
                    print(f"[MEASURING (combined)] Latency:{self.latency_combined:.10f} Packet_loss: {self.packet_loss_combined:.3f}", end="\r")
                    #print(f"[MEASURING (combined)] Latency:{self.latency_combined:.10f} Packet_loss: {self.packet_loss_combined}", end="\r")
                    self.check_alert(self.latency_combined>=LATENCY_ALERT,self.packet_loss_combined>=PACKET_LOSS_ALERT)
                    if self.latency_decoration > 0:
                        time.sleep(self.latency_decoration)

            except KeyboardInterrupt:
                self.measuring=False
            except socket.timeout:
                self.measuring = False
                self.running = False
                #if self.event != None:
                self.event.set()
                print("\nConection timeout")
            except ConnectionResetError as e:
                #Si el so cierra la conexion porque no esta levantado el otro extremo
                #Tambien si se cae el otro extremo, esto ocurre cuando lo pruebo en local, en dos maquinas se podra gestionar bien TODO
                #Esto ocurre en cuanto se corta la conexion
                #TODO: Podria volver al init conection para esperar al otro extremo
                self.measuring = False
                self.running = False
                #if self.event != None:
                self.event.set()
                print("\nConection error")
                
                #continue
            except Exception as error:
                #pass
                #print(f"Error recibiendo mensajes {error}")#suelen entrar timeouts, tratar en el futuro
                #self.measuring = False
                continue
        self.socket.close()
        print("\n[MEASURING] END")
        return

        

    def run(self):
        #try:
        #inicio conexion
        self.running = True
        if self.role=="server":
            init = self.init_connection_server()
        elif self.role=="client":
            init = self.init_connection_client()
        else:
            init = -1
        if init == 0:
            '''print(f"[NEGOTIATION PHASE] during {NEGOTIATION_TIME} seconds")
            self.negotiation_rcv = threading.Thread(target=self.negotiation_receive, daemon=True, name="hilo_negotiation_rcv")
            self.negotiation_snd = threading.Thread(target=self.negotiation_send, daemon=True, name="hilo_negotiation_snd")
            self.negotiating = True
            if self.role=="server":
                self.negotiation_rcv.start()
                self.negotiation_snd.start()
            else:
                self.negotiation_snd.start()
                self.negotiation_rcv.start()
            
            time.sleep(NEGOTIATION_TIME)
            self.negotiating = False
            self.negotiation_rcv.join()
            self.negotiation_snd.join()

            if self.latency_combined > LATENCY_ALERT or self.packet_loss_combined > PACKET_LOSS_ALERT:
                print(f"[NEGOTIATION PHASE] WARNING: Latency alerts during negotiation: {self.negotiation_latency_alert} Packet loss alerts during negotiation: {self.negotiation_packet_loss_alert}")
                print(f"[NEGOTIATION PHASE] ERROR: The network parameters do not allow the minimum quality of service Latency: {self.latency_combined} Packet_loss: {self.packet_loss_combined}")

            else:
                if self.negotiation_latency_alert > 0 or self.negotiation_packet_loss_alert > 0:
                    print(f"[NEGOTIATION PHASE] WARNING: Latency alerts during negotiation: {self.negotiation_latency_alert} Packet loss alerts during negotiation: {self.negotiation_packet_loss_alert}")
                #Puedes continuar con la medicion'''
                
            self.socket.settimeout(1)#un segundo antes de perdida de conex, mejor valor 360ms, podria ser una vble global, o a fuego por precaucion
            
            self.hilo_rcv = threading.Thread(target=self.measurement_receive_message, daemon=True, name="hilo_rcv")
            self.hilo_snd = threading.Thread(target=self.measurement_send_ping, daemon=True, name="hilo_snd")
            
            self.state=("normal",time.time())
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


if __name__=="__main__":
    main_run = True
    #os.system('cls' if os.name == 'nt' else 'clear')
    if len(sys.argv)<2:
        print("Usage")
    elif len(sys.argv)==2:
        if sys.argv[1] == "-s":            
            logger.addHandler(server_handler)
            q4s_node = q4s_lite_node("server",server_address, server_port, client_address, client_port)
            q4s_node.run()
            try:
                while q4s_node.running:#Aqui se puede poner menu de control con simulacion de perdidas etc...
                    time.sleep(0.1)
                    '''option = input("\npulsa 0 para salir\n")
                    if option == '0':
                        main_run=False'''
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
                    time.sleep(0.1)
                    '''option = input("\npulsa 0 para salir\n")
                    if option == '0':
                        main_run=False'''
            except KeyboardInterrupt:
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()
            print("\nYou can see q4s_client.log for viewing execution")
        else:
            print("Opcion no reconocida\nUsage:  ")
    else:
        print("Too much arguments\nUsage:  ")

    #os.system('cls' if os.name == 'nt' else 'clear')
   #modo libreria con init, q reciba funcion de callback para avisar de las alertas 
