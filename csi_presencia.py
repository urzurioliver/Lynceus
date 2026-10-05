from CSIKit.filters.butterworth import bandpass
import numpy as np
import socket
import numpy as np

buffer_temporal = collections.deque(maxlen=100);
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
sock.bind(("0.0.0.0", 5005))

print(f"Escuchando datos CSI en el puerto {5005}")

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
        
    except KeyboardInterrupt:
        print("\nDeteniendo escucha UDP...")
        break
    except Exception as e:
        print(f"Error procesando paquete: {e}")
sock.close()

fase_unwrapped = np.unwrap(phase)
fase_promedio = np.mean(fase_unwrapped)
buffer_temporal.append(fase_promedio)

# 3. Filtrar con el filtro paso banda de CSIKit
# bandpass(datos, lowcut_hz, highcut_hz, fs_hz, order)
if len(buffer_temporal) >= 100:  # Ejemplo: 5 segundos a 20 Hz
  onda_limpia = bandpass(
      np.array(buffer_temporal), lowcut=0.1, highcut=0.5, fs=20, order=2
  )

  # El último valor indica el estado del pecho:
  # Valor sube -> Pecho se infla
  # Valor baja -> Pecho se defla
  valor_actual = onda_limpia[-1]