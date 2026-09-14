import socket
import numpy as np

# Configuración del socket UDP
UDP_IP = "0.0.0.0"  # Escucha en todas las interfaces de red locales
UDP_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Escuchando datos CSI en el puerto {UDP_PORT} (UDP)...")
try:
    while True:
    # Recibe hasta 4096 bytes por paquete
        data, addr = sock.recvfrom(4096)
    
    # 'data' contiene los bytes crudos del payload CSI
        print(f"Paquete recibido desde {addr} - Tamaño: {len(data)} bytes")
    
    # Aquí irá tu lógica para parsear la matriz de amplitud y fase
    # ej: csi_matrix = parse_csi_payload(data)
    #corro con python receptor.py
        data, addr = sock.recvfrom(4096)
        raw_array = np.frombuffer(data, dtype=np.int8)
        real=raw_array[0::2]
        imag=raw_array[1::2]
        csi_complejo = real +1j * imag
        amplitud = np.abs(csi_complejo)
            
