''' 
NOKIA TECSS
Implementacion de q4s bla bla

Autores:
Juan Ramos Diaz
Juan Jose Guerrero Lopez
'''

import struct
import time
import socket
import _thread
from datetime import datetime
import sys

class UDPConnection:
    def __init__(self, address, port):
        self.address = address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        #self.socket.setblocking(False)
        self.socket.bind((address, port))

class q4s_lite_client(UDPConnection):

    def __init__(self, address, port, server_address, server_port):
        super().__init__(address, port)
        self.server_address = (server_address, server_port)
        self.n_seq = 0
        self.latencia_actual = 0
        self.packets_received = [1] * 1000
        self.total_received = 1000

    def init_connection(self):
        retries = 0
        self.n_seq = -1
        #self.socket.setblocking(True)
        self.socket.settimeout(3)
        timestamp=time.time()
        while retries < 3:
            try:
                print("CLIENT: Iniciando conexion")
                #timestamp=time.time()
                datos = struct.pack('>di', timestamp, self.n_seq)
                print(f"CLIENT: Iniciando conexion: n_seq:{self.n_seq}")
                self.socket.sendto(datos, self.server_address)
                
                data, address = self.socket.recvfrom(12) 
                timestamp_recepcion = time.time()
                data_rcvd = struct.unpack('>di', data)  # 20 caracteres para la cadena
                n_seq_server = data_rcvd[1]
                if n_seq_server == -1:
                    print(f"CLIENT: Conexion establecida ha tardado {timestamp_recepcion-timestamp} segundos")
                    datos = struct.pack('>di', timestamp, 0)
                    self.socket.sendto(datos, self.server_address)
                    return 0
                else:
                    print("CLIENT: Respuesta invalida server")
            except socket.timeout:
                retries+=1
                print(f"CLIENT: Timeout, reintentando {retries}/3")
        else:
            print("CLIENT: Error no se puede conectar con el servidor")
            return -1

            
    def measurement(self):
        self.socket.setblocking(True)
        self.socket.settimeout(0.033)
        n_seq_sent = -1
        self.n_seq = 1
        for i in range(10):
        #while True:
            #if self.n_seq == n_seq_sent:
            #    continue
            timestamp=time.time()
            datos = struct.pack('>di', timestamp, self.n_seq) #se pude codificar en utf-8 tambien
            try:
                self.socket.sendto(datos, self.server_address)
                n_seq_sent = self.n_seq
                self.total_received -= self.packets_received[self.n_seq]
                print(f"CLIENT: Enviado: n_seq:{self.n_seq}")
                self.n_seq+=1

            except Exception as error:
                print(f"CLIENT: Error al enviar datos {error}")
            
            try:
                data, address = self.socket.recvfrom(12) 
                timestamp_recepcion = time.time()
                #Recepcion de datos 
                data_rcvd = struct.unpack('>di', data)  # 20 caracteres para la cadena
                n_seq_server = data_rcvd[1]
                #Aqui se tomarian las medidas
                ##############LATENCY
                latencia_nueva = (timestamp_recepcion-data_rcvd[0])/2
                #############JITTER
                jitter = self.latencia_actual-latencia_nueva
                #amortiguacion de latencia
                if (latencia_nueva>self.latencia_actual+1):
                    self.latencia_actual = self.latencia_actual+1
                elif (latencia_nueva<self.latencia_actual-1):
                    self.latencia_actual=self.latencia_actual-1
                else:
                    self.latencia_actual = latencia_nueva 
                #print(f"CLIENT:Recibido aceptacion de n_seq: {n_seq_server} con latencia(nueva,vieja): {latencia_nueva},{self.latencia_actual}")
                #############JITTER

                #################PACKET LOSS
                self.packets_received[n_seq_server]=1
                self.total_received+=self.packets_received[n_seq_server]%1000
                loss=(1000-self.total_received)/1000 #Para la division entre 1000 puedo desplazar a la derecha 10 bits y dividir entre 1024
                #Si hago deplazamientos, puedo multiplicar el resultado por 1,024 para aproximarlo mejor
                #resultado_aproximado = round((numero >> 10) * 1.024)
                print(f"CLIENT:Recibido aceptacion de n_seq: {n_seq_server}.\nMedidas_up(actual,jitter,loss): {self.latencia_actual},{jitter},{loss}")
                
            except BlockingIOError:
                #No se recibe repuesta se sigue con el siguiente
                print("BlockingIOError")
                continue
            except Exception as error:
                print(f"    Fallo recibiendo mensajes {error}")
                continue
            #time.sleep(0.06)
            self.n_seq = self.n_seq%1000

    def run(self):
        if self.init_connection()==0:
            print("hecho")
            self.measurement()
        else:
            print("Sin conexion")

server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 20002


client = q4s_lite_client(client_address, client_port, server_address, server_port)
client.run()
