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

PACKET_LOSS_PRECISSION = 1000 #Precision de los paquetes perdidos
LATENCY_ALERT = 360 #milisegundos
PACKET_LOSS_ALERT = 0.02 #50%
RECOVERY_TIME = 2 #segundos

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

    def __init__(self, role, address, port, target_address, target_port):
        #El rol importa para iniciar conex o medir up/down
        self.role = role 
        #udp socket params
        self.address = address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((address, port))
        self.target_address = (target_address, target_port)
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
        self.state=None,None #Es una tupla de nombre estado, timestamp cuando se puso, para poder calcular el recovery
        #lock para acceso critico
        self.lock = threading.Lock()

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

    @staticmethod
    def get_metrics(reception_time,sent_time,last_latency,total_received):
        new_latency = ((reception_time-sent_time)*1000)/2 #rtt/2
        jitter = abs(new_latency-last_latency) #El valor absoluto
        #amortiguacion sencilla
        '''if (new_latency>last_latency+1):
            new_latency = last_latency+1
        elif (new_latency<last_latency-1):
            new_latency=last_latency-1
        else:
            new_latency = last_latency'''
        #loss
        loss=((PACKET_LOSS_PRECISSION-total_received)/PACKET_LOSS_PRECISSION)
        #Hay que restar las perdidas por transito: rtt*frecuencia envio paquetes, no son perdidos todavia
        #JJ: No considerar perdida los ultimos paquetes en transito
        #
        return new_latency,jitter,loss

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
                
                self.socket.sendto(packet, self.target_address)
                logger.debug(f"[MEASURING SEND PING] n_seq:{packet_data[1]}: lat_up:{packet_data[3]} lat_down:{packet_data[4]} jit_up:{packet_data[5]} jit_down:{packet_data[6]} pl_up:{packet_data[7]} pl_down:{packet_data[8]}")
                #print(f"ENVIO PING n_seq:{packet_data[1]}: lat_up:{packet_data[3]} lat_down:{packet_data[4]} jit_up:{packet_data[5]} jit_down:{packet_data[6]} pl_up:{packet_data[7]} pl_down:{packet_data[8]}")
                #TODO: METER EL LOCK AQUI
                self.total_received-=self.packets_received[self.seq_number]
                self.packets_received[self.seq_number] = 1
                self.seq_number = (self.seq_number+1)%PACKET_LOSS_PRECISSION
                time.sleep(0.03)#Esto es la cadencia de paquetes por segundo, configurable tambien
                #responsividad es packetloss_precission/cadencia
            except KeyboardInterrupt:
                self.measuring=False
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

    def check_alert(self,latency,packet_loss,data):
        logger.debug(f"ESTADO: {self.state}")
        #check_alert.last_check=timestamp
        #si ha pasado menos de un segundo desde la ultima invocacion a alert, return
        if self.state[0]=="normal":
            if latency > LATENCY_ALERT or packet_loss>PACKET_LOSS_ALERT:
                self.state="alert",time.time()
                #sendalert
                packet_data=(alert_message,0,self.state[1],data[3],data[4],data[5],data[6],data[7],data[8])#mejor mando self y no data
                datos = struct.pack(PACKET_FORMAT,*packet_data)
                #self.socket.sendto(datos,self.target_address)
                #Logica del actuador, que sería una funcion de callback con la que le han llamado
                print(f"\n[ALERT]: Latency:{latency}/{LATENCY_ALERT} Packet_loss: {packet_loss}/{PACKET_LOSS_ALERT}")
        elif self.state[0]=="alert":#el recovery debe ser cuando se ha recuperado durante un tiempo, habria que guardar el timestamp del alert
            if latency < LATENCY_ALERT and packet_loss < PACKET_LOSS_ALERT:
                #check tiempo pasado para salir de alerta mandar reco o no
                if (self.state[1]-time.time()) > RECOVERY_TIME:
                    self.state="normal",None
                    #sendreco #con los datos self?
                    #llamo a callback para recovery
                    #la logica del actuador es la que se encarga de todo, el callback es el mismo
            elif latency > LATENCY_ALERT or packet_loss>PACKET_LOSS_ALERT:
                #sendalert
                packet_data=(alert_message,0,self.state[1],data[3],data[4],data[5],data[6],data[7],data[8])#mejor mando self y no data
                datos = struct.pack(PACKET_FORMAT,*packet_data)
                #self.socket.sendto(datos,self.target_address)
                print(f"\n[ALERT]: Latency:{latency}/{LATENCY_ALERT} Packet_loss: {packet_loss}/{PACKET_LOSS_ALERT}")

    def measurement_receive_message(self):
        while self.measuring:
            #recibe mensaje bloqueante
            try:
                data,addr = self.socket.recvfrom(PACKET_SIZE)
                #timestamp_recepcion solo se usa para medir, es decir si el mensaje es tipo resp, aqui es mas preciso pero se puede mover para optimizar el proceso
                timestamp_recepcion = time.time()
                unpacked_data = struct.unpack(PACKET_FORMAT, data)
                message_type = unpacked_data[0].decode(MSG_FORMAT).strip()  # El tipo de mensaje es el primer campo
                #Estoy actualizando solo si el mensaje es tipo ping que esta mas actualizado que el resp que puede arrastrar ceros desde el principio
                #with self.lock:
                #    self.update_measures(unpacked_data)
                #print(f"Me llega un mensaje {unpacked_data[0]} ({unpacked_data[2]}) con n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]}")
                #print(f"Me llega un mensaje {unpacked_data[0]} ({unpacked_data[2]}) con n_seq:{unpacked_data[1]}: lat_up:{self.latency_up} lat_down:{self.latency_down} jit_up:{self.jitter_up} jit_down:{self.jitter_down} pl_up:{self.packet_loss_up} pl_down:{self.packet_loss_down}")
                #logger.debug(f"[MEASURING] Recibido paquete (Tipo={message_type}, Datos={unpacked_data})")
                if message_type == "PING": #PING
                    self.update_measures(unpacked_data)
                    logger.debug(f"[MEASURING RECEIVE PING] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]}")
                    packet_data = (resp_message,*unpacked_data[1:])#,unpacked_data[1],unpacked_data[2],unpacked_data[3],unpacked_data[4],unpacked_data[5],unpacked_data[6],unpacked_data[7],unpacked_data[8])
                    packet = struct.pack(PACKET_FORMAT, *packet_data)
                    self.socket.sendto(packet,self.target_address)
                    logger.debug(f"[MEASURING CONTEST RESP] n_seq:{packet_data[1]}: lat_up:{packet_data[3]} lat_down:{packet_data[4]} jit_up:{packet_data[5]} jit_down:{packet_data[6]} pl_up:{packet_data[7]} pl_down:{packet_data[8]}")
                elif message_type == "RESP": #RESP
                    #actualizo el packet received
                    #TODO:Meter el lock aqui
                    self.packets_received[unpacked_data[1]]=0
                    #self.total_received+=1 #self.packets_received[unpacked_data[1]]
                    #si seq_number que me llega esta muy cerca de self.seq_number
                    logger.debug(f"[MEASURING RECEIVE RESP] n_seq:{unpacked_data[1]}: lat_up:{unpacked_data[3]} lat_down:{unpacked_data[4]} jit_up:{unpacked_data[5]} jit_down:{unpacked_data[6]} pl_up:{unpacked_data[7]} pl_down:{unpacked_data[8]}")
                    
                    if self.role=="server":
                        self.latency_down,self.jitter_down,self.packet_loss_down = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_down,self.total_received)
                        #TODO:como imprimire el avg, esto se quitara de aqui
                        if self.seq_number%50==0:
                            print(f"[MEASURING (down)] Latency:{self.latency_down:.10f} Jitter: {self.jitter_down:.10f} Packet_loss: {self.packet_loss_down:.3f}", end="\r")
                
                        #despues de medir si ser superan umbrales de latencia o packet loss se emite mensaje alerta
                        #se pone en estado de alerta, si estando en alerta se arregla se manda recovery y se pasa a estado normal
                        #self.check_alert(self.latency_down,self.packet_loss_down, unpacked_data)
                    elif self.role=="client":
                        self.latency_up,self.jitter_up,self.packet_loss_up = self.get_metrics(timestamp_recepcion,unpacked_data[2],self.latency_up,self.total_received)
                        if self.seq_number%50==0:
                            print(f"[MEASURING (up)] Latency:{self.latency_up:.10f} Jitter: {self.jitter_up:.10f} Packet_loss: {self.packet_loss_up:.3f}", end="\r")
                        #despues de medir si ser superan umbrales de latencia o packet loss se emite mensaje alerta
                        #se pone en estado de alerta, si estando en alerta se arregla se manda recovery y se pasa a estado normal
                        #self.check_alert(self.latency_up,self.packet_loss_up, unpacked_data)
                    #TODO aqui se hace el check_alert con las medias de las medidas up y down
                    #latency_avg = (self.latency_up+self.latency_down)/2
                    #packet_loss_avg=
                    #TODO se quita el checkalert por rol
                    #self.check_alert(self.latency_avg,self.packet_loss_avg)

            except KeyboardInterrupt:
                self.measuring=False
            except ConnectionResetError as e:
                #Si el so cierra la conexion porque no esta levantado el otro extremo
                #Tambien si se cae el otro extremo
                continue
            except Exception as error:
                #pass
                #print(f"Error recibiendo mensajes {error}")#suelen entrar timeouts, tratar en el futuro
                #self.measuring = False
                continue
        return

        

    def run(self):
        #try:
        #inicio conexion
        if self.role=="server":
            init = self.init_connection_server()
        elif self.role=="client":
            init = self.init_connection_client()
        else:
            init = -1
        if init == 0:
            self.socket.settimeout(1)#un segundo antes de perdida de conex, mejor valor 360ms
            
            self.hilo_rcv = threading.Thread(target=self.measurement_receive_message, daemon=True, name="hilo_rcv")
            self.hilo_snd = threading.Thread(target=self.measurement_send_ping, daemon=True, name="hilo_snd")
            
            self.state=("normal",None)
            self.measuring = True
            if self.role=="server":
                self.hilo_rcv.start()
                self.hilo_snd.start()
            else:
                self.hilo_snd.start()
                self.hilo_rcv.start()
            print("[MEASUREMENT PHASE] Press ctrl+c to stop")


        else:
            print("Conexion fallida")


if __name__=="__main__":

    #os.system('cls' if os.name == 'nt' else 'clear')
    if len(sys.argv)<2:
        print("Usage")
    elif len(sys.argv)==2:
        if sys.argv[1] == "-s":            
            logger.addHandler(server_handler)
            q4s_node = q4s_lite_node("server",server_address, server_port, client_address, client_port)
            q4s_node.run()
            try:
                while True:#Aqui se puede poner menu de control con simulacion de perdidas etc...
                    time.sleep(0.1)
            except KeyboardInterrupt:
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()
                print("")
            print("You can see q4s_server.log for viewing execution")
        elif sys.argv[1] == "-c":
            logger.addHandler(client_handler)

            q4s_node = q4s_lite_node("client",client_address, client_port, server_address, server_port)
            q4s_node.run()
            try:
                while True:#Aqui se puede poner menu de control con simulacion de perdidas etc...
                    time.sleep(0.1)
            except KeyboardInterrupt:
                q4s_node.measuring=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join()

            print("You can see q4s_client.log for viewing execution")
        else:
            print("Opcion no reconocida\nUsage:  ")
    else:
        print("Too much arguments\nUsage:  ")

    #os.system('cls' if os.name == 'nt' else 'clear')
   #modo libreria con init, q reciba funcion de callback para avisar de las alertas 
