import threading
import time
import q4s_lite

event = threading.Event()
server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 2000
actuator_alive = False

def actuator(q4s_node):
	#while q4s_node.running:
	while actuator_alive:
		q4s_node.event.wait()
		q4s_node.event.clear()
		print(f"Me ha llegado una alerta {q4s_node.latency_combined}\n")#Faltan packetloss y jitter
		#peticion a lhe
	print("\nFinished actuation\n")


if __name__=="__main__":
	#global actuator_alive
	#El actuador es el cliente por defecto, ya que va en el coche
	q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event)
	q4s_node.run()
	actuator_alive = True
	actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
	actuator_thread.start()
	
	while True:
			#time.sleep(0.1)
			print("")
			print("1: añade 10 milisegundos de latencia")
			print("0: Salir")
			option = input("\nElige una opcion\n")
			if option == '0':#Mata el actuador y los hilos del cliente q4s
				actuator_alive=False
				#actuator_thread.join()
				q4s_node.running=False
				q4s_node.measuring=False
				q4s_node.hilo_snd.join()
				q4s_node.hilo_rcv.join()
				break
			elif option == '1':
				q4s_node.latency_decoration+=1
	'''actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
	actuator_thread.start()
	#El actuador no tiene que funcionar igual con el while true, podria tener un join y parar cuando quieras en la funcion actuator
	try:
		while True:
			time.sleep(0.1)
			option = input("\npulsa 0 para salir \n")
			if option == '0':
				actuator_alive=False
				actuator_thread.join()
				q4s_node.running=False
				q4s_node.hilo_snd.join()
				q4s_node.hilo_rcv.join()
				
	except KeyboardInterrupt:
		q4s_node.running=False
		q4s_node.hilo_snd.join()
		q4s_node.hilo_rcv.join()
		#actuator_thread.join() TODO cerrar bien el programa
	print("\nYou can see q4s_client.log for viewing execution")'''


	print("EXIT")
	