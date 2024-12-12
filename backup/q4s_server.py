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


class q4s_lite_server(UDPConnection):

    def __init__(self, address, port, client_address, client_port):
        super().__init__(address, port)
        self.client_address = (client_address, client_port)
        self.n_seq_sent = -1
        self.latencia_actual = 0
        self.packets_received = [1] * 1000
        self.total_received = 1000

    def init_connection(self):
        #self.socket.setblocking(True)
        self.socket.settimeout(15)
        print(f"Server running at {self.address}:{self.port}")
        try:
            data, address = self.socket.recvfrom(12)
            data_rcvd = struct.unpack('>di', data)  # 20 caracteres para la cadena
            n_seq_server = data_rcvd[1]
            if n_seq_server == -1:
                for i in range(3):
                    print(f"SERVER: Recibido peticion conexion")
                    self.socket.sendto(data, self.client_address)
                    data,address = self.socket.recvfrom(12)
                    data_rcvd = struct.unpack('>di', data)  # 20 caracteres para la cadena
                    n_seq_server = data_rcvd[1]
                    if n_seq_server==0:
                        print(f"SERVER: Sesion iniciada")
                        return 0
                    #Si no ha llegado la confirmacion, vuelve a llegar un 0
                    if n_seq_server==-1:
                        continue
                    else:
                        print(f"SERVER: Error, confirmacion no valida")
                        return -1
        except socket.timeout:
            print("SERVER: Timeout")
            return -1

    def measurement(self):
        self.socket.setblocking(True)
        self.socket.settimeout(0.033)
        print(f"Server running at {self.address}:{self.port}")
        while True:
            try:
                data, address = self.socket.recvfrom(12)
                timestamp_recepcion = time.time()
                #Recepcion de datos
                data_rcvd = struct.unpack('>di', data) 
                timestamp_rcvd = data_rcvd[0]
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
                #print(f":Recibido aceptacion de n_seq: {n_seq_server} con latencia(nueva,vieja): {latencia_nueva},{self.latencia_actual}")
                #############JITTER

                #################PACKET LOSS
                self.packets_received[n_seq_server]=1
                self.total_received+=self.packets_received[n_seq_server]%1000
                loss=(1000-self.total_received)/1000 #Para la division entre 1000 puedo desplazar a la derecha 10 bits y dividir entre 1024
                #Si hago deplazamientos, puedo multiplicar el resultado por 1,024 para aproximarlo mejor
                #resultado_aproximado = round((numero >> 10) * 1.024)
                print(f"SERVER:Recibido aceptacion de n_seq: {n_seq_server}.\nMedidas_down(actual,jitter,loss): {self.latencia_actual},{jitter},{loss}")
                
                print(f"SERVER: Recibido: n_seq: {n_seq_server} timestamp:{timestamp_rcvd}")
                
                datos = struct.pack('>di', timestamp_rcvd,n_seq_server)
                try:
                    self.socket.sendto(datos, self.client_address)
                    print(f"    SERVER: Reenviado: n_seq:{n_seq_server}")
                    self.total_received -= self.packets_received[n_seq_server]
                    self.n_seq_sent = n_seq_server
                except Exception as error:
                    #print(f"    SERVER:Error al reenviar datos {error}")
                    continue               
            except BlockingIOError:
                #print("BlockingIOError")
                #No se recibe repuesta se sigue con el siguiente
                continue
            except Exception as error:
                #print(f"    Fallo recibiendo mensajes {error}")
                continue
            #time.sleep(0.06)
            

    def run(self):
        if self.init_connection()==0:
            print("hecho")
            self.measurement()



server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 20002



server = q4s_lite_server(server_address, server_port, client_address, client_port)
server.run()
