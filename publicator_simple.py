import threading
import time
import q4s_lite
import logging,sys

#Parametros q4s
event = threading.Event()
server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 2000

#Parametros del actuador
publicator_alive = False
mqtt_host,mqtt_port = "127.0.0.1",8889
PUBLICATION_TIME = 3

#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_client.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

LATENCY_ALERT = q4s_lite.LATENCY_ALERT#360 #milisegundos
PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT#0.1#0.02 #2%

def alert_publicator(q4s_node):
	global publicator_alive
	while publicator_alive:
		q4s_node.event.wait()
		q4s_node.event.clear()
		#Alerta de perdida de conexion o de latencia/packet loss
		if q4s_node.running==False:
			print("Alerta por perdida de conexion")
			publicator_alive = False
		else:
			#check alerts
			if q4s_node.latency_combined > LATENCY_ALERT and q4s_node.packet_loss_combined > PACKET_LOSS_ALERT:
				print(f"Me ha llegado una alerta de latencia y packet loss\n")#Faltan packetloss y jitter
			elif q4s_node.latency_combined > LATENCY_ALERT:
				print("Me ha llegado una alerta por latencia")
			elif q4s_node.packet_loss_combined > PACKET_LOSS_ALERT:
				print("Me ha llegado una alerta por packet loss")
		#peticion a lhe
	print("\nFinished alert publication you must relaunch the program\nPress 0 to exit\n")

def measures_publicator(q4s_node):
	global publicator_alive
	while publicator_alive:
		print(f"[PUBLICATOR] Measures Latency:{q4s_node.latency_combined:.10f} Packet_loss: {q4s_node.packet_loss_combined:.3f}")
		time.sleep(PUBLICATION_TIME)				

def main():
	global publicator_alive
	logger.addHandler(client_handler)
	#El actuador es el server por defecto, ya que va en el proxy de video
	q4s_node = q4s_lite.q4s_lite_node("server", server_address, server_port,client_address, client_port,event)
	q4s_node.run()
	publicator_alive = True
	alert_publicator_thread = threading.Thread(target=alert_publicator,args=(q4s_node,),daemon=True)
	alert_publicator_thread.start()
	measures_publicator_thread = threading.Thread(target=measures_publicator,args=(q4s_node,),daemon=True)
	measures_publicator_thread.start()

	#main_thread_alive = True
	
	while True:
			#time.sleep(0.1)
			print("")
			print("1: empeora latencia")
			print("2: mejora latencia")
			print("3: pierde un 10 por ciento de paquetes")
			print("4: pierde un 10 por ciento de paquetes")
			#print("5: restart publicator")
			print("0: Salir")
			option = input("\nElige una opcion\n")
			if option == '0':#Mata el actuador y los hilos del cliente q4s
				publicator_alive=False
				#publicator_thread.join()
				q4s_node.running=False
				q4s_node.measuring=False
				q4s_node.hilo_snd.join()
				q4s_node.hilo_rcv.join()
				break
			elif option == '1':
				q4s_node.latency_decoration+=0.1
			elif option == '2':
				q4s_node.latency_decoration=0
			elif option == '3':
				q4s_node.packet_loss_decoration+=0.1
			elif option == '4':
				q4s_node.packet_loss_decoration=0
			'''elif option == '5':#Opcion desactivada
				publicator_alive=False
				#publicator_thread.join()
				q4s_node.running=False
				q4s_node.measuring=False
				q4s_node.hilo_snd.join()
				q4s_node.hilo_rcv.join()
				publicator_thread.join()
				main()'''
				

	print("EXIT")

if __name__=="__main__":
	main()
	'''logger.addHandler(client_handler)
	#El actuador es el cliente por defecto, ya que va en el coche
	q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event)
	q4s_node.run()
	publicator_alive = True
	publicator_thread = threading.Thread(target=publicator,args=(q4s_node,),daemon=True)
	publicator_thread.start()

	#main_thread_alive = True
	
	while True:
			#time.sleep(0.1)
			print("")
			print("1: empeora latencia")
			print("2: mejora latencia")
			print("3: pierde un 10 por ciento de paquetes")
			print("4: pierde un 10 por ciento de paquetes")
			print("5: restart publicator")
			print("0: Salir")
			option = input("\nElige una opcion\n")
			if option == '0':#Mata el actuador y los hilos del cliente q4s
				publicator_alive=False
				#publicator_thread.join()
				q4s_node.running=False
				q4s_node.measuring=False
				q4s_node.hilo_snd.join()
				q4s_node.hilo_rcv.join()
				break
			elif option == '1':
				q4s_node.latency_decoration+=0.1
			elif option == '2':
				q4s_node.latency_decoration=0
			elif option == '3':
				q4s_node.packet_loss_decoration+=0.1

	print("EXIT")'''
	