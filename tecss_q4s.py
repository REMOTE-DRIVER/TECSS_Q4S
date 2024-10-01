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

#Variables globales
serverAddressPort = ("127.0.0.1", 20001) #Direccion
UDPSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) #Socket

def receive_data(serverAddressPort):
	'''Funcion que recibe datos en un socket udp'''
	global UDPSocket
	time.sleep(0.5)
	while True:
		try:
			data, address = UDPSocket.recvfrom(100) #buffersize 10000
			print("	Recibido")
		except:
			print("	Fallo recibiendo mensajes")
			continue

		data_rcvd = struct.unpack('d',data)
		print(data_rcvd)
	print("	Fallo general en receive_data")

def send_data(serverAddressPort) :   
	'''Funcion que envia datos en un socket udp'''
	global UDPSocket
	timestamp=time.time()
	datos = struct.pack('d',timestamp)
	try:
		UDPSocket.sendto(datos, serverAddressPort)
	except:
		print("	Error al enviar datos")
	print("	Datos enviados")

_thread.start_new_thread(receive_data, (serverAddressPort,))

print("Empezamos:")
time.sleep(1.00)
for i in range(5):
	print(f"Enviando paquete {i}")
	send_data(serverAddressPort)

