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
			data, address = UDPSocket.recvfrom(100) #buffersize 10000
			#print("	Recibido")
		except:
			#print("	Fallo recibiendo mensajes")
			continue

		data_rcvd = struct.unpack('20sI', data)  # 20 caracteres para la cadena
		timestamp_rcvd_str = data_rcvd[0].decode('utf-8').strip('\x00')  # Decodificar la cadena y eliminar relleno
		n_seq_server = data_rcvd[1]
		print(f"	Recibido: n_seq: {n_seq_server} timestamp:{timestamp_rcvd_str}")
	print("	Fallo general en receive_data")

def send_data(serverAddressPort) :   
	'''Funcion que envia datos en un socket udp'''
	global UDPSocket
	global n_seq

	timestamp=time.time()
	timestamp_str = str(timestamp) 
	datos = struct.pack('20sI', timestamp_str.encode('utf-8'), n_seq)
	try:
		UDPSocket.sendto(datos, serverAddressPort)
		print(f"	Enviado: n_seq:{n_seq}")
		n_seq+=1
	except:
		print("	Error al enviar datos")
	

UDPSocket.bind(serverAddressPort)
_thread.start_new_thread(receive_data, (serverAddressPort,))

print("Empezamos:")
for i in range(5):
	print(f"Enviando paquete {i}")
	send_data(serverAddressPort)

