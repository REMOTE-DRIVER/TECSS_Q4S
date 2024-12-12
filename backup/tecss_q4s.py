''' 
NOKIA TECSS
Implementacion de q4s bla bla

Autores:
Juan Ramos Diaz
Juan Jose Guerrero Lopez
'''

#Version 0.0:Solo montar socket udp y mandar timestamps

import struct
import time
import socket
import _thread
from datetime import datetime
import sys

#Variables globales
#serverAddressPort = ("127.0.0.1", 20001) #Direccion
#UDPSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) #Socket
#UDPSocket.setblocking(False) # Configura el socket en modo no bloqueante
n_seq = 0

#serverAddressPort = ("127.0.0.1", 20001)  # Dirección del servidor
serverAddressPort = ("192.168.1.113", 20001)  # Dirección del servidor
#clientAddressPort = ("127.0.0.1", 20002)  # Dirección del cliente
clientAddressPort = ("192.168.1.50", 20002)  # Dirección del cliente
serverSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)  # Socket del servidor
clientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) 

def server(serverAddressPort):
	#Recibe paquetes num secuencia y timestamp
	#Envia ese mismo numero secuencia
	#si lo recibe, desempaqueta y envia el numero de secuencia para confirmar al cliente la recepcion
	#global UDPSocket
	UDPSocket = serverSocket
	UDPSocket.setblocking(False)
	UDPSocket.bind(serverAddressPort)
	n_seq_sent=-1
	while True:
	#for i in range(10):
		try:
			data, address = UDPSocket.recvfrom(12)
			#print("	Recibido")
			
		except BlockingIOError:
			#print("BlockingIOError")
			#No se recibe repuesta se sigue con el siguiente
			continue
		except Exception as error:
			print(f"	Fallo recibiendo mensajes {error}")
			continue
		#Recepcion de datos
		data_rcvd = struct.unpack('>di', data)  # 20 caracteres para la cadena
		timestamp_rcvd = data_rcvd[0]
		n_seq_server = data_rcvd[1]
		#Aqui se tomarian las medidas
		print(f"	SERVER: Recibido: n_seq: {n_seq_server} timestamp:{timestamp_rcvd}")
		datos = struct.pack('>di', timestamp_rcvd,n_seq_server)
		#Reenvio de datos
		if n_seq_server==5:
			continue
		if n_seq_sent ==n_seq_server:
			continue
		try:
			UDPSocket.sendto(datos, clientAddressPort)
			print(f"	SERVER: Reenviado: n_seq:{n_seq_server}")
			n_seq_sent = n_seq_server
		except Exception as error:
			print(f"	SERVER:Error al reenviar datos {error}")
			continue
		#time.sleep(0.5)

def client(clientAddressPort):
	#Manda paquetes com mum secuencia y timestamp
	#Recibe paquetes con num secuencia y timestamp
	global UDPSocket
	global n_seq
	UDPSocket = clientSocket
	UDPSocket.setblocking(False)
	UDPSocket.bind(clientAddressPort)
	
	n_seq_sent = -1
	latencia_actual=0
	packets_received=[1]*1000
	total_received = 1000
	#while True:
	for i in range(10):
		if n_seq == n_seq_sent:
			continue
		timestamp=time.time()
		datos = struct.pack('>di', timestamp, n_seq) #se pude codificar en utf-8 tambien
		try:
			UDPSocket.sendto(datos, serverAddressPort)
			n_seq_sent = n_seq
			total_received -= packets_received[n_seq]
			print(f"CLIENT: Enviado: n_seq:{n_seq}")
			n_seq+=1

		except:
			print("CLIENT: Error al enviar datos")
		
		try:
			data, address = UDPSocket.recvfrom(12) 
			timestamp_recepcion = time.time()
			#Recepcion de datos	
			data_rcvd = struct.unpack('>di', data)  # 20 caracteres para la cadena
			n_seq_server = data_rcvd[1]
			#Aqui se tomarian las medidas
			##############LATENCY
			latencia_nueva = 500*(timestamp_recepcion-data_rcvd[0])
			#############JITTER
			jitter = latencia_actual-latencia_nueva
			#amortiguacion de latencia
			if (latencia_nueva>latencia_actual+1):
				latencia_actual = latencia_actual+1
			elif (latencia_nueva<latencia_actual-1):
				latencia_actual=latencia_actual-1
			else:
				latencia_actual = latencia_nueva 
			#print(f"CLIENT:Recibido aceptacion de n_seq: {n_seq_server} con latencia(nueva,vieja): {latencia_nueva},{latencia_actual}")
			#############JITTER

			#################PACKET LOSS
			packets_received[n_seq_server]=1
			total_received+=packets_received[n_seq_server]%1000
			loss=1000-total_received #Para la division entre 1000 puedo desplazar a la derecha 10 bits y dividir entre 1024
			#Si hago deplazamientos, puedo multiplicar el resultado por 1,024 para aproximarlo mejor
			#resultado_aproximado = round((numero >> 10) * 1.024)
			print(f"CLIENT:Recibido aceptacion de n_seq: {n_seq_server}. Medidas(actual,loss,jitter): {latencia_actual},{loss},{jitter}")

		except BlockingIOError:
			#No se recibe repuesta se sigue con el siguiente
			continue
		except Exception as error:
			print(f"	Fallo recibiendo mensajes {error}")
			continue
		time.sleep(0.5)



#_thread.start_new_thread(server, (serverAddressPort,))
#time.sleep(1)
#client(clientAddressPort)
server(serverAddressPort)