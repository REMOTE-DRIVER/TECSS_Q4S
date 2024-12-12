''' 
NOKIA TECSS
Implementacion de q4s bla bla

Autores:
Juan Ramos Diaz
Juan Jose Guerrero Lopez
'''
import socket
import struct
import threading
import time
import sys

#Paquete con tipo_mensaje,num secuencia, timestam, latencia_up/down, jitter_up/down, packet_loss_up/down 
#tipo mensaje 1 byte: SYN (0),ACK (1),PING (2),RESP (3)
PACKET_FORMAT = ">4sifffffff"  # Formato de los datos
PACKET_SIZE = 40

server_address, server_port = "127.0.0.1",20001
client_address, client_port = "127.0.0.1",20002
#server_address, server_port = "192.168.1.113", 20001
#client_address, client_port = "192.168.1.50", 20002


class q4s_lite_server():

    def __init__(self, address, port, target_address, target_port):
        #udp socket params
        self.address = address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((address, port))
        self.target_address = (target_address, target_port)
        #measurement stage params
        self.hilo_rcv=None
        self.hilo_snd=None
        self.running=True
        #measurement params
        self.seq_number = 0
        self.latency_up=0.0
        self.latency_down=0.0
        self.jitter_up=0.0
        self.jitter_down=0.0
        self.packet_loss_up=0.0
        self.packet_loss_down=0.0


    def measurement_send_message(self):
        message_type="PING".encode('utf-8')
        while self.running:
            #Se prepara el paquete
            packet_data=(
                message_type,
                self.seq_number,
                time.time(),
                self.latency_up,
                self.latency_down,
                self.jitter_up,
                self.jitter_down,
                self.packet_loss_up,
                self.packet_loss_down
                )
            packet = struct.pack(PACKET_FORMAT, *packet_data)
            try:
                self.socket.sendto(packet, self.target_address)
                print(f"Enviado paquete #{self.seq_number} (Tipo={message_type}) a {self.target_address}")
                self.seq_number += 1
                time.sleep(0.03)
            except KeyboardInterrupt:
                self.running=False
            except Exception as e:
                #Si el so cierra la conexion porque no esta levantado el otro extremo
                #Tambien si se cae el otro extremo
                print(f"SERVER: ERROR in sending message {e}")
                continue

    def measurement_receive_message(self):
        ping_message = "PING".encode('utf-8')
        resp_message = "RESP".encode('utf-8')
        while self.running:
            #recibe mensaje bloqueante
            try:
                data,addr = self.socket.recvfrom(PACKET_SIZE)
                unpacked_data = struct.unpack(PACKET_FORMAT, data)
                message_type = unpacked_data[0].decode('utf-8').strip()  # El tipo de mensaje es el primer campo
                print(f"Recibido paquete de {addr}: Tipo={message_type}, Datos={unpacked_data[1:]}")
                if message_type == "PING": #PING
                    #pass
                    packet_data = (resp_message,unpacked_data[1],unpacked_data[2],unpacked_data[3],unpacked_data[4],unpacked_data[5],unpacked_data[6],unpacked_data[7],unpacked_data[8])
                    packet = struct.pack(PACKET_FORMAT, *packet_data)
                    self.socket.sendto(packet,self.target_address)
                    #no toco timestamp y mando un resp
                elif message_type == "RESP": #RESP
                    pass
                    #actualizo medidas
            except KeyboardInterrupt:
                self.running=False
            except ConnectionResetError as e:
                #Si el so cierra la conexion porque no esta levantado el otro extremo
                #Tambien si se cae el otro extremo
                continue
            except Exception as error:
                #pass
                print(f"Error recibiendo mensajes {error}")
                #self.running = False

    def init_connection(self):
        ack_message = "ACK".ljust(4).encode('utf-8')
        syn_message = "SYN".ljust(4).encode('utf-8')
        print("SERVER: Waiting for connection")
        self.socket.settimeout(15)
        try:
            data, _ = self.socket.recvfrom(PACKET_SIZE)
            data_rcvd = struct.unpack(PACKET_FORMAT,data)
            message_type = data_rcvd[0].decode('utf-8').strip()
            if "SYN" in message_type:
                for i in range(3):
                    print(f"SERVER: Received connexion attempt")
                    #Responde al syn con ack
                    packet_data=(ack_message,0,time.time(),0.0,0.0,0.0,0.0,0.0,0.0)
                    datos = struct.pack(PACKET_FORMAT,*packet_data)
                    self.socket.sendto(datos,self.target_address)
                    #Ahora espero el ack de vuelta
                    data,_ = self.socket.recvfrom(PACKET_SIZE)
                    data_rcvd = struct.unpack(PACKET_FORMAT,data)
                    message_type = data_rcvd[0].decode('utf-8').strip()
                    if "ACK" in message_type:
                        print("SERVER: Start")
                        return 0
                    elif "SYN" in message_type:
                        continue
                    else:
                        print("SERVER: Error, invalid confirmation")
                        return -1
        except socket.timeout:
            print("SERVER:Timeout")
            return -1



    def run(self):
        #try:
        #inicio conexion
        if self.init_connection() == 0:
            self.socket.settimeout(0.360)#un segundo antes de perdida de conex, mejor valor 360ms
            #self.hilo_rcv = threading.Thread(target=self.measurement_receive_message, daemon=True, name="hilo_rcv")
            #self.hilo_snd = threading.Thread(target=self.measurement_send_message, daemon=True, name="hilo_snd")
            self.hilo_rcv = threading.Thread(target=self.measurement_receive_message, name="hilo_rcv")
            self.hilo_snd = threading.Thread(target=self.measurement_send_message, name="hilo_snd")

            self.hilo_rcv.start()
            self.hilo_snd.start()

            #self.hilo_snd.join()
            #self.hilo_rcv.join()

            #A la espera de que termine el programa con ctrl+c
            '''try:
                while True:
                    #time.sleep(0.1)
                    salir = input("pulsa q para salir")
                    if salir=="q":
                        self.running=False
            except KeyboardInterrupt:
                self.running=False
                print("hilos terminando")
                self.hilo_snd.join()
                self.hilo_rcv.join()  '''    
        else:
            print("Conexion fallida")
        '''except KeyboardInterrupt:
            print("Closing Server")
            self.running=False
            self.socket.close()
            self.hilo_rcv.join()
            self.hilo_snd.join() '''


    


'''def menu_principal():

    while True:
        print("\n--- Menú Principal ---")
        print("1. Start Server")
        print("2. Start Client")
        print("3. Exit program")
        opcion = input("Selecciona una opción: \n")

        if opcion == "1":
            q4s_node = q4s_lite_node("server",server_address, server_port, client_address, client_port)
            q4s_node.run()


        if opcion == "2":
            q4s_node = q4s_lite_node("client", client_address, client_port, server_address, server_port)
            q4s_node.run()

        if opcion == "3":
            try:
                q4s_node.running=False
            except:
                print("No q4s node instantiated")
            print("Saliendo del programa...")
            break'''

if __name__=="__main__":

    #menu_principal()
    q4s_node = q4s_lite_server(server_address, server_port, client_address, client_port)
    q4s_node.run()
    try:
        while True:
            #time.sleep(0.1)
            salir = input("pulsa q para salir")
            if salir=="q":
                q4s_node.running=False
                q4s_node.hilo_snd.join()
                q4s_node.hilo_rcv.join() 
                sys.exit()
    except KeyboardInterrupt:
        q4s_node.running=False
        print("hilos terminando")
        q4s_node.hilo_snd.join()
        q4s_node.hilo_rcv.join()

