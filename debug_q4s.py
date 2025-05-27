#!/usr/bin/env python3
"""
Script para diagnosticar el problema del flow_id en q4s_lite
"""

import socket
import time
import sys
import os

def check_port_status(host, port):
    """Verifica si un puerto está ocupado"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
        sock.close()
        return False  # Puerto libre
    except OSError as e:
        return True   # Puerto ocupado
    finally:
        try:
            sock.close()
        except:
            pass

def cleanup_q4s_environment():
    """Limpia el entorno de q4s_lite"""
    print("🔧 Limpiando entorno Q4S...")
    
    # 1. Verificar puertos
    server_port = 20001
    client_port = 20002
    
    print(f"📡 Puerto servidor ({server_port}): {'OCUPADO' if check_port_status('127.0.0.1', server_port) else 'LIBRE'}")
    print(f"📡 Puerto cliente ({client_port}): {'OCUPADO' if check_port_status('127.0.0.1', client_port) else 'LIBRE'}")
    
    # 2. Limpiar archivos de log
    log_files = ['q4s_server.log', 'q4s_client.log']
    for log_file in log_files:
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
                print(f"🗑️  Eliminado: {log_file}")
            except Exception as e:
                print(f"❌ Error eliminando {log_file}: {e}")
        else:
            print(f"ℹ️  No existe: {log_file}")
    
    # 3. Verificar procesos Python que puedan estar usando Q4S
    try:
        import psutil
        q4s_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python' or proc.info['name'] == 'python3':
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'q4s_lite' in cmdline or 'publicator' in cmdline or 'actuator' in cmdline:
                        q4s_processes.append((proc.info['pid'], cmdline))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if q4s_processes:
            print(f"⚠️  Procesos Q4S encontrados:")
            for pid, cmd in q4s_processes:
                print(f"   PID {pid}: {cmd}")
            print(f"💡 Considera terminar estos procesos si el problema persiste")
        else:
            print(f"✅ No hay procesos Q4S ejecutándose")
            
    except ImportError:
        print("ℹ️  psutil no disponible, saltando verificación de procesos")
    
    # 4. Esperar un poco para que se liberen recursos
    print("⏳ Esperando 2 segundos para liberar recursos...")
    time.sleep(2)
    
    print("🎯 Limpieza completada\n")

def test_q4s_initialization():
    """Prueba la inicialización de q4s_lite"""
    print("🧪 Probando inicialización Q4S...")
    
    try:
        from q4s_lite import q4s_lite_node, encode_identifier, decode_identifier, VEHICLE_ID
        
        print(f"📋 VEHICLE_ID del config: '{VEHICLE_ID}'")
        print(f"📋 encode_identifier('{VEHICLE_ID}'): {encode_identifier(VEHICLE_ID)}")
        print(f"📋 decode_identifier({encode_identifier(VEHICLE_ID)}): '{decode_identifier(encode_identifier(VEHICLE_ID))}'")
        
        # Crear nodo servidor
        print("\n🖥️  Creando nodo servidor...")
        server_node = q4s_lite_node(
            "server", 
            "127.0.0.1", 20001,
            "127.0.0.1", 20002
        )
        
        print(f"📊 flow_id inicial del servidor: {server_node.flow_id}")
        print(f"📊 decode del flow_id inicial: '{decode_identifier(server_node.flow_id) if server_node.flow_id != 0 else 'VACIO (flow_id=0)'}'")
        
        # Crear nodo cliente  
        print("\n💻 Creando nodo cliente...")
        client_node = q4s_lite_node(
            "client",
            "127.0.0.1", 20002, 
            "127.0.0.1", 20001
        )
        
        print(f"📊 flow_id inicial del cliente: {client_node.flow_id}")
        print(f"📊 decode del flow_id del cliente: '{decode_identifier(client_node.flow_id) if client_node.flow_id != 0 else 'VACIO (flow_id=0)'}'")
        
        # Cerrar sockets
        server_node.socket.close()
        client_node.socket.close()
        
        print("✅ Prueba de inicialización completada")
        
    except Exception as e:
        print(f"❌ Error en prueba de inicialización: {e}")
        import traceback
        traceback.print_exc()

def monitor_q4s_packets():
    """Monitorea paquetes UDP en los puertos de Q4S"""
    print("📡 Monitoreando paquetes UDP (Ctrl+C para parar)...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1', 20003))  # Puerto diferente para monitoreo
        sock.settimeout(1.0)
        
        start_time = time.time()
        packet_count = 0
        
        while time.time() - start_time < 10:  # Monitorear por 10 segundos
            try:
                data, addr = sock.recvfrom(1024)
                packet_count += 1
                print(f"📦 Paquete #{packet_count} desde {addr}: {len(data)} bytes")
                
                # Intentar decodificar si parece un paquete Q4S
                if len(data) >= 52:  # PACKET_SIZE de Q4S
                    try:
                        import struct
                        unpacked = struct.unpack(">4sidffffffi", data)
                        msg_type = unpacked[0].decode('utf-8').strip()
                        flow_id = unpacked[9]
                        print(f"   Tipo: {msg_type}, Flow ID: {flow_id}")
                    except:
                        print(f"   No es paquete Q4S válido")
                        
            except socket.timeout:
                continue
            except Exception as e:
                print(f"❌ Error monitoreando: {e}")
                break
                
        if packet_count == 0:
            print("ℹ️  No se detectaron paquetes UDP residuales")
        else:
            print(f"⚠️  Se detectaron {packet_count} paquetes - esto podría causar problemas")
            
    except Exception as e:
        print(f"❌ Error configurando monitor: {e}")
    finally:
        sock.close()

def main():
    print("🔍 DIAGNÓSTICO Q4S - PROBLEMA FLOW_ID")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "clean":
            cleanup_q4s_environment()
            return
        elif sys.argv[1] == "test":
            test_q4s_initialization()
            return
        elif sys.argv[1] == "monitor":
            monitor_q4s_packets()
            return
    
    # Diagnóstico completo
    cleanup_q4s_environment()
    test_q4s_initialization()
    
    print("\n💡 RECOMENDACIONES:")
    print("1. Ejecuta 'python debug_q4s_issue.py clean' antes de cada prueba")
    print("2. Espera 5 segundos entre ejecuciones de Q4S")
    print("3. Verifica que no hay otros procesos Q4S ejecutándose")
    print("4. Si el problema persiste, reinicia el sistema")

if __name__ == "__main__":
    main()
