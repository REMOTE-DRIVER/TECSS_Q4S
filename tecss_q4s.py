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

UDPSocket.bind(serverAddressPort)

def receive_data(serverAddressPort):
	'''Funcion que recibe datos en un socket udp'''
	global UDPSocket
	while True:
		try:
			data, address = UDPSocket.recvfrom(100) #buffersize 10000
			print("	Recibido")
		except:
			#print("	Fallo recibiendo mensajes")
			continue

		data_rcvd = struct.unpack('f',data)
		timestamp_rcvd = data_rcvd[0]
		timestamp_str = datetime.fromtimestamp(timestamp_rcvd).strftime('%H:%M:%S')
		print(f"	Timestamp: {timestamp_str}")
		#time.sleep(0.01)
	print("	Fallo general en receive_data")

def send_data(serverAddressPort) :   
	'''Funcion que envia datos en un socket udp'''
	global UDPSocket
	timestamp=time.time()
	datos = struct.pack('f',timestamp)
	try:
		UDPSocket.sendto(datos, serverAddressPort)
		print("	Datos enviados")
	except:
		print("	Error al enviar datos")
	

_thread.start_new_thread(receive_data, (serverAddressPort,))

print("Empezamos:")
time.sleep(1.00)
for i in range(5):
	print(f"Enviando paquete {i}")
	send_data(serverAddressPort)

