import collections
import socket
from CSIKit.filters.butterworth import bandpass
import numpy as np
from scipy.signal import find_peaks

buffer_temporal = collections.deque(maxlen=100)


def parseCsi(data):
  # Convertir el buffer de bytes a enteros de 8 bits con signo
  csiBase = np.frombuffer(data, dtype=np.int8)

  # Separo componentes real e imaginario
  real = csiBase[0::2].astype(np.float32)
  imag = csiBase[1::2].astype(np.float32)
  csi_complex = real + 1j * imag

  # Amplitud y Fase
  amplitud = np.abs(csi_complex)
  fase = np.angle(csi_complex)

  fasePromedio = np.mean(np.unwrap(fase))
  return fasePromedio

# socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 5005))

print(f"Escuchando datos CSI en el puerto {5005}")
escuchando = True

while escuchando == True:
  try:
    # Recibe hasta 4096 bytes por paquete
    data, addr = sock.recvfrom(4096)

    # Filtro básico para descartar paquetes vacíos o dañados
    if len(data) < 10:
      continue

    fasePromedio = parseCsi(data)
    buffer_temporal.append(fasePromedio)

    # 3. filtro de CSIKit
    # bandpass(datos, lowcut_hz, highcut_hz, fs_hz, order)
    if len(buffer_temporal) >= 100:  # con menos lecturas tira datos basura
      ondaLimpia = bandpass(  # funcion de csikit para filtrar
          np.array(buffer_temporal),
          lowcut=0.1,
          highcut=0.5,
          fs=20,
          order=2,  # cuts medidos en hertz. 0,1 es 6rpm, 0,5 30
      )
def CalcuarRPM (ondaLimpia, fs =20):

  return 
  
  except KeyboardInterrupt:
    print("\nDeteniendo escucha UDP...")
    escuchando = False
    break
  except Exception as e:
    print(f"Error procesando paquete: {e}")

sock.close()