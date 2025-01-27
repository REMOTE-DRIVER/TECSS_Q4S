import threading
import time
import q4s_lite

event = threading.Event()
server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 2000


def actuator(q4s_node):
	while q4s_node.running:
		q4s_node.event.wait()
		q4s_node.event.clear()
		print(f"Me ha llegado una alerta {q4s_node.latency_combined}")#Faltan packetloss y jitter
	pass


if __name__=="__main__":
	#El actuador es el cliente por defecto, ya que va en el coche
	q4s_node = q4s_lite_node("client",client_address, client_port, server_address, server_port,event)
    q4s_node.run()
    actuator_thread = threading.Thread(target=actuator,args=(q4s_node),daemon=True)
    actuator_thread.start()
    try:
		while True:
			time.sleep(0.1)
	except KeyboardInterrupt:
		q4s_node.running=False
		q4s_node.hilo_snd.join()
        q4s_node.hilo_rcv.join()
    print("\nYou can see q4s_client.log for viewing execution")

	print("EXIT")
	