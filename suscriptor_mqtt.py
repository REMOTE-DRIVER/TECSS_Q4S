import paho.mqtt.client as mqtt

# Configuración del servidor
broker = "remotedriver.dit.upm.es"
port = 41883
username = "nokia"
password = "vZATSQ3xJkLtsFJ3wnVEbQ"

# Callback cuando el cliente recibe un mensaje
def on_message(client, userdata, message):
    print(f"Mensaje recibido en {message.topic}: {message.payload.decode()}")

# Callback cuando se conecta al servidor
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado al servidor MQTT")
        client.subscribe('alertas')
        client.subscribe('medidas')

    else:
        print(f"Error en la conexión: {rc}")

# Cliente MQTT
client = mqtt.Client()
client.username_pw_set(username, password)

client.on_connect = on_connect
client.on_message = on_message

# Conectarse y mantener la suscripción activa
client.connect(broker, port, 60)
client.loop_forever()
