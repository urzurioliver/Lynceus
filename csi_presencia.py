import collections
import socket
from CSIKit.filters.butterworth import bandpass # type: ignore
import numpy as np
from scipy.signal import find_peaks

buffer_temporal = collections.deque(maxlen=100)
presence = False

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
def CalcularRPM (ondaLimpia, fs =20):
  picos, _ = find_peaks(ondaLimpia, distance=fs , prominence=0.02) #hace que la distancia entre picos tenga 1seg de diferencia y que el tamaño de la cresta o valle sea minimo 0,2
  #devuelve los picos y otro dato irrelevant eque lo saco con _
  if len(picos)<2:
    presence = False, 0.0
    return presence
  else:
    distanciaPromedio = np.mean(np.diff(picos))/fs
    rpm = 60/distanciaPromedio
    presence=True
    return presence, round(float(rpm), 1)
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
      presencia, rpm = CalcularRPM(ondaLimpia, fs=20)
      print(f"Presencia: {presencia} | RPM: {rpm}")

  except KeyboardInterrupt:
    print("\nDeteniendo escucha UDP...")
    escuchando = False
    break
  except Exception as e:
    print(f"Error procesando paquete: {e}")

def agregarMedicion (id, ):
  return
sock.close()