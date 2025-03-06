import threading
import time
import q4s_lite
import logging

import paho.mqtt.client as mqtt

#Parametros q4s
event = threading.Event()
server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 2000

#Parametros del actuador
publicator_alive = False
mqtt_host, mqtt_port = "remotedriver.dit.upm.es", 41883
username = "nokia"
password = "vZATSQ3xJkLtsFJ3wnVEbQ"
client_mqtt = mqtt.Client()
client_mqtt.username_pw_set(username, password)

PUBLICATION_TIME = 3 #segundos
PUBLICATION_ALERT_TIME = 1 #segundo

#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_server.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

LATENCY_ALERT = q4s_lite.LATENCY_ALERT#360 #milisegundos
PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT#0.1#0.02 #2%

def alert_publicator(q4s_node):
	global publicator_alive
	while publicator_alive:
		#q4s_node.alert_publicator.wait()
		#clear
		#stop_publish_alert = False
		#time_alert = time.time()
		#while not stop_publish_alert:
		#	publicas en mqtt el nuevo mensaje de alerta
		#	time.sleep(publication_alert_time)
		#	check si la alerta sigue activa
		#		si esta activa:
		#			time_alert = time.time()
		#			continue
		#		si no esta activa:
		#			miras time.time() - time_alert > X: x es un numero cualquiera
		#				si es asi:
		#					break
		#				si no:
		#					continue
		if q4s_node.latency_combined > LATENCY_ALERT and q4s_node.packet_loss_combined > PACKET_LOSS_ALERT:
			print(f"[PUBLICATOR ALERTS]Me ha llegado una alerta de latencia y packet loss            \n")#Faltan packetloss y jitter
			client_mqtt.publish('alertas', 'Me ha llegado una alerta de latencia y packet loss')
		elif q4s_node.latency_combined > LATENCY_ALERT:
			print("[PUBLICATOR ALERTS]Me ha llegado una alerta por latencia                     ")
			client_mqtt.publish('alertas', 'Me ha llegado una alerta por latencia')
		elif q4s_node.packet_loss_combined > PACKET_LOSS_ALERT:
			print("[PUBLICATOR ALERTS]Me ha llegado una alerta por packet loss                 ")
			client_mqtt.publish('alertas', 'Me ha llegado una alerta por packet loss')
		time.sleep(PUBLICATION_ALERT_TIME)
	print("\nFinished alert publication you must relaunch the program\nPress 0 to exit\n")

def measures_publicator(q4s_node):
    global publicator_alive
    while publicator_alive:
        print(f"[PUBLICATOR] Measures Latency:{q4s_node.latency_combined:.10f} Packet_loss: {q4s_node.packet_loss_combined:.3f}")
        client_mqtt.publish('medidas', f"Measures Latency:{q4s_node.latency_combined:.10f} Packet_loss: {q4s_node.packet_loss_combined:.3f}")
        time.sleep(PUBLICATION_TIME)


def main():
	global publicator_alive
	logger.addHandler(client_handler)
	#El actuador es el server por defecto, ya que va en el proxy de video
	q4s_node = q4s_lite.q4s_lite_node("server", server_address, server_port,client_address, client_port,event)
	q4s_node.run()
	client_mqtt.connect(mqtt_host, mqtt_port)
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
			print("4: deja de perder paquetes")
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
				client_mqtt.disconnect()
				break
			elif option == '1':
				q4s_node.latency_decoration+=0.1
			elif option == '2':
				q4s_node.latency_decoration=0
			elif option == '3':
				q4s_node.packet_loss_decoration=0.8
				print(f"Packet_loss_decoration =  {q4s_node.packet_loss_decoration}")
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