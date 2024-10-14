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
serverAddressPort = ("127.0.0.1", 20001) #Direccion
UDPSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) #Socket
n_seq = 0

def receive_data(serverAddressPort):
	'''Funcion que recibe datos en un socket udp'''
	global UDPSocket
	while True:
		try:
			data, address = UDPSocket.recvfrom(24) #20 timestamp + 4 int
			#print("	Recibido")
		except:
			#print("	Fallo recibiendo mensajes")
			continue

		data_rcvd = struct.unpack('20sI', data)  # 20 caracteres para la cadena
		timestamp_rcvd_str = data_rcvd[0].decode('ascii').strip('\x00')  # Decodificar la cadena y eliminar relleno
		n_seq_server = data_rcvd[1]
		print(f"	Recibido: n_seq: {n_seq_server} timestamp:{timestamp_rcvd_str}")
	print("	Fallo general en receive_data")

def send_data(serverAddressPort) :   
	'''Funcion que envia datos en un socket udp'''
	global UDPSocket
	global n_seq

	timestamp=time.time()
	timestamp_str = str(timestamp)
	#TO DO:Se puede ajustar mas el timestamp, si en vez de dejar 20bytes, dejamos el maximo que pueda ocupar un timestamp 
	datos = struct.pack('20sI', timestamp_str.encode('ascii'), n_seq) #se pude codificar en utf-8 tambien
	try:
		UDPSocket.sendto(datos, serverAddressPort)
		print(f"	Enviado: n_seq:{n_seq}")
		n_seq+=1
	except:
		print("	Error al enviar datos")


'''UDPSocket.bind(serverAddressPort)
_thread.start_new_thread(receive_data, (serverAddressPort,))

print("Empezamos:")
for i in range(5):
	print(f"Enviando paquete {i}")
	send_data(serverAddressPort)'''

def server(serverAddressPort):
	#Recibe paquetes num secuencia y timestamp
	#Envia ese mismo numero secuencia
	global UDPSocket
	UDPSocket.bind(serverAddressPort)
	while True:
		try:
			data, address = UDPSocket.recvfrom(24) #20 timestamp + 4 int
			#print("	Recibido")
		except:
			#print("	Fallo recibiendo mensajes")
			continue
		try:
			UDPSocket.sendto(datos, serverAddressPort)
			print(f"	Enviado: n_seq:{n_seq}")
			n_seq+=1
		except:
			print("	Error al enviar datos")

def client(serverAddressPort):
	#Manda paquetes com mum secuencia y timestamp
	#Recibe paquetes con num secuencia
	global UDPSocket
	global n_seq
	UDPSocket.bind(serverAddressPort)
	while True:
		try:
			UDPSocket.sendto(datos, serverAddressPort)
			print(f"	Enviado: n_seq:{n_seq}")
			n_seq+=1
		except:
			print("	Error al enviar datos")
		try:
			data, address = UDPSocket.recvfrom(24) #20 timestamp + 4 int
			#print("	Recibido")
		except:
			#print("	Fallo recibiendo mensajes")
			continue