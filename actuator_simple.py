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
actuator_alive = False
actuator_host,actuator_port = "127.0.0.1",8889

#logging
logger = logging.getLogger('q4s_logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(message)s')
client_handler = logging.FileHandler('q4s_client.log',mode='w')
client_handler.setLevel(logging.DEBUG)
client_handler.setFormatter(formatter)

#mejor usar q4s_lite.LATENCY_ALERT
LATENCY_ALERT = q4s_lite.LATENCY_ALERT#360 #milisegundos
PACKET_LOSS_ALERT = q4s_lite.PACKET_LOSS_ALERT#0.1#0.02 #2%

def send_command(command: str) -> str:
    """Envía un comando al dispositivo y recibe la respuesta mediante TCP."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((actuator_host,actuator_port))
        #No se envia con send, para asegurar que se envia el mensaje entero
        s.sendall(command.encode() + b"\0")  # Añadir byte cero al final
        response = s.recv(1024)  # Recibir respuesta
    return response.decode().strip("\0")  # Quitar byte cero al final


def get_target_bw_orig() -> str:
    return send_command("GET_TARGET_BW_ORIG")


def set_target_bw_orig(value: int) -> str:
	#Comentado en el caso que sea necesario que el numero entero explicito en big endian
	#value_bytes = struct.pack(">I", value)  # Convierte a big-endian
    #command = f"SET_TARGET_BW_ORIG:".encode() + value_bytes + b"\0"
    #return send_command(command)
    return send_command(f"SET_TARGET_BW_ORIG:{value}")


def set_noise_resist(enable: bool) -> str:
    return send_command(f"SET_NOISE_RESIST:{int(enable)}")


def actuator(q4s_node):
	global actuator_alive
	while actuator_alive:
		q4s_node.event.wait()
		q4s_node.event.clear()
		#Alerta de perdida de conexion o de latencia/packet loss
		if q4s_node.running==False:
			print("Alerta por perdida de conexion")
			actuator_alive = False
			#Si esta implementado el reset haces continue del bucle
			#Ahora lo que haces es emitir un mensaje de que terminas
		else:
			#check alerts
			#maquina estados, pides subidas y bajadas
			
			if q4s_node.latency_combined > LATENCY_ALERT and q4s_node.packet_loss_combined > PACKET_LOSS_ALERT:
				print(f"Me ha llegado una alerta de latencia y packet loss\n")
			elif q4s_node.latency_combined > LATENCY_ALERT:
				print("Me ha llegado una alerta por latencia")
			elif q4s_node.packet_loss_combined > PACKET_LOSS_ALERT:
				print("Me ha llegado una alerta por packet loss")
		#peticion a lhe
	print("\nFinished actuation you must relaunch the program\nPress 0 to exit\n")
				

def main():
	global actuator_alive
	logger.addHandler(client_handler)
	#El actuador es el cliente por defecto, ya que va en el coche
	q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event)
	q4s_node.run()
	actuator_alive = True
	actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
	actuator_thread.start()

	#main_thread_alive = True
	
	while True:
			#time.sleep(0.1)
			print("")
			print("1: empeora latencia")
			print("2: mejora latencia")
			print("3: pierde un 10 por ciento de paquetes")
			print("4: No pierdas paquetes")
			#print("5: restart actuator")
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
				q4s_node.latency_decoration+=0.1
			elif option == '2':
				q4s_node.latency_decoration=0
			elif option == '3':
				q4s_node.packet_loss_decoration+=0.1
			elif option == '4':
				q4s_node.packet_loss_decoration=0
			'''elif option == '5':#Opcion desactivada
				actuator_alive=False
				#actuator_thread.join()
				q4s_node.running=False
				q4s_node.measuring=False
				q4s_node.hilo_snd.join()
				q4s_node.hilo_rcv.join()
				actuator_thread.join()
				main()'''
				

	print("EXIT")

if __name__=="__main__":
	main()
	'''logger.addHandler(client_handler)
	#El actuador es el cliente por defecto, ya que va en el coche
	q4s_node = q4s_lite.q4s_lite_node("client",client_address, client_port, server_address, server_port,event)
	q4s_node.run()
	actuator_alive = True
	actuator_thread = threading.Thread(target=actuator,args=(q4s_node,),daemon=True)
	actuator_thread.start()

	#main_thread_alive = True
	
	while True:
			#time.sleep(0.1)
			print("")
			print("1: empeora latencia")
			print("2: mejora latencia")
			print("3: pierde un 10 por ciento de paquetes")
			print("4: pierde un 10 por ciento de paquetes")
			print("5: restart actuator")
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
				q4s_node.latency_decoration+=0.1
			elif option == '2':
				q4s_node.latency_decoration=0
			elif option == '3':
				q4s_node.packet_loss_decoration+=0.1

	print("EXIT")'''
	