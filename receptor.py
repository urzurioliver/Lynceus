import socket
import numpy as np

# Configuración del socket UDP
UDP_IP = "0.0.0.0"  # Escucha en todas las interfaces de red locales
UDP_PORT = 5005

def parse_csi_payload(data):
    # Convertir el buffer de bytes a enteros de 8 bits con signo
    csi_raw = np.frombuffer(data, dtype=np.int8)
    
    # Separar componentes real e imaginaria
    real = csi_raw[0::2].astype(np.float32)
    imag = csi_raw[1::2].astype(np.float32)
    
    # Reconstruir números complejos (H = Real + j*Imag)
    csi_complex = real + 1j * imag
    print (f"csi: {csi_complex}")
    # Extraer Amplitud |H| y Fase arg(H)
    amplitude = np.abs(csi_complex)
    phase = np.angle(csi_complex)
    
    return csi_complex, amplitude, phase

# Inicializar socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Escuchando datos CSI en el puerto {UDP_PORT} (UDP)...")

while True:
    try:
        # Recibe hasta 4096 bytes por paquete
        data, addr = sock.recvfrom(4096)
        
        # Filtro básico para descartar paquetes vacíos o dañados
        if len(data) < 10:
            continue
            
        # Parsear la matriz CSI
        csi_matrix, amplitude, phase = parse_csi_payload(data)
        
        # Mostrar información procesada
        num_subcarrieres = len(amplitude)
        promedio_amplitud = np.mean(amplitude)
        
      #  print(f"Paquete recibido desde {addr[0]}:{addr[1]} | "
       #       f"Subportadoras: {num_subcarrieres} | "
        #      f"Amplitud media: {promedio_amplitud:.2f}")

        # AQUÍ PUEDES USAR 'amplitude' Y 'phase' PARA TU LÓGICA
        # Por ejemplo:
        # subportadora_10_amp = amplitude[10]
        # subportadora_10_fase = phase[10]

    except KeyboardInterrupt:
        print("\nDeteniendo escucha UDP...")
        break
    except Exception as e:
        print(f"Error procesando paquete: {e}")

sock.close()