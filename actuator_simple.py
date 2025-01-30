import threading
import time
import q4s_lite

#Parametros q4s
event = threading.Event()
server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 2000

#Parametros del actuador
actuator_alive = False
actuator_host,actuator_port = "127.0.0.1",20003

def send_command(command: str) -> str:
    """Envía un comando al dispositivo y recibe la respuesta mediante UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(command.encode() + b"\0", (actuator_host, actuator_port))  # Añadir byte cero al final
        response, _ = s.recvfrom(1024)  # Recibir respuesta
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
			print("1: empeora latencia")
			print("2: mejora latencia")
			print("3: pierde un 10 por ciento de paquetes")
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

	print("EXIT")
	