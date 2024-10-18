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

'''
def receive_data(serverAddressPort):
	#Funcion que recibe datos en un socket udp
	global UDPSocket
	while True:
		try:
			data, address = UDPSocket.recvfrom(24) #20 timestamp + 4 int
			#print("	Recibido")
		except Exception as e:
			#print(f"	Fallo recibiendo mensajes {e}")
			continue

		data_rcvd = struct.unpack('20sI', data)  # 20 caracteres para la cadena
		timestamp_rcvd_str = data_rcvd[0].decode('ascii').strip('\x00')  # Decodificar la cadena y eliminar relleno
		n_seq_server = data_rcvd[1]
		print(f"	Recibido: n_seq: {n_seq_server} timestamp:{timestamp_rcvd_str}")
	print("	Fallo general en receive_data")

def send_data(serverAddressPort) :   
	#Funcion que envia datos en un socket udp
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


UDPSocket.bind(serverAddressPort)
_thread.start_new_thread(receive_data, (serverAddressPort,))

print("Empezamos:")
for i in range(5):
	print(f"Enviando paquete {i}")
	send_data(serverAddressPort)
'''

def server(serverAddressPort):
	#Recibe paquetes num secuencia y timestamp
	#Envia ese mismo numero secuencia
	#si lo recibe, desempaqueta y envia el numero de secuencia para confirmar al cliente la recepcion
	global UDPSocket
	#while True:
	for i in range(10):
		try:
			data, address = UDPSocket.recvfrom(24) #20 timestamp + 4 int
			#print("	Recibido")
		except:
			#print("	Fallo recibiendo mensajes")
			continue

		#Recepcion de datos	
		data_rcvd = struct.unpack('20sI', data)  # 20 caracteres para la cadena
		timestamp_rcvd_str = data_rcvd[0].decode('ascii').strip('\x00')  # Decodificar la cadena y eliminar relleno
		n_seq_server = data_rcvd[1]
		#Aqui se tomarian las medidas
		print(f"	SERVER: Recibido: n_seq: {n_seq_server} timestamp:{timestamp_rcvd_str}")
		datos = struct.pack('I', n_seq_server) #Solo envia el numero de secuencia, trabajamos con el reloj del cliente
		#Reenvio de datos
		try:
			UDPSocket.sendto(datos, serverAddressPort)
			print(f"	SERVER: Reenviado: n_seq:{n_seq_server}")
			#n_seq+=1
		except:
			print("	SERVER:Error al reenviar datos")
			continue

def client(serverAddressPort):
	#Manda paquetes com mum secuencia y timestamp
	#Recibe paquetes con num secuencia
	#Intenta recibir la respuesta del server y manda el siguiente
	#	¿deberia intentar mas veces?quizas solo un intento de respuesta sea demasiado poco
	global UDPSocket
	global n_seq
	#while True:
	for i in range(10):
		timestamp=time.time()
		timestamp_str = str(timestamp)
		#TO DO:Se puede ajustar mas el timestamp, si en vez de dejar 20bytes, dejamos el maximo que pueda ocupar un timestamp 
		datos = struct.pack('20sI', timestamp_str.encode('ascii'), n_seq) #se pude codificar en utf-8 tambien
		try:
			UDPSocket.sendto(datos, serverAddressPort)
			print(f"CLIENT: Enviado: n_seq:{n_seq}")
			n_seq+=1
		except:
			print("CLIENT: Error al enviar datos")
		try:
			data, address = UDPSocket.recvfrom(4) #20 timestamp + 4 int
			#print("	Recibido")
			#Recepcion de datos	
			data_rcvd = struct.unpack('I', data)  # 20 caracteres para la cadena
			n_seq_server = data_rcvd[0]
			#Aqui se tomarian las medidas
			print(f"CLIENT:Recibido aceptacion de n_seq: {n_seq_server}")
		except:
			#print("	Fallo recibiendo mensajes")
			continue


UDPSocket.bind(serverAddressPort)
#TODO: Lanzar un proceso en lugar de un thread, aunque tampoco influye muchisimo
_thread.start_new_thread(server, (serverAddressPort,))
client(serverAddressPort)