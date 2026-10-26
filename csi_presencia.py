import collections
import socket
import time
from CSIKit.filters.passband import bandpass
import numpy as np
from scipy.signal import find_peaks

# Comentado mientras pruebas sin conexión a BD
from db import guardar_medicion, sesionActiva

buffer_temporal = collections.deque(maxlen=100)


def parseCsi(data):
  csiBase = np.frombuffer(data, dtype=np.int8)
  real = csiBase[0::2].astype(np.float32)
  imag = csiBase[1::2].astype(np.float32)
  csi_complex = real + 1j * imag

  fase = np.angle(csi_complex)
  fasePromedio = np.mean(np.unwrap(fase))
  return fasePromedio


def CalcularRPM(ondaLimpia, fs=20):
  picos, _ = find_peaks(ondaLimpia, distance=fs, prominence=0.02)
  if len(picos) < 2:
    return False, 0.0

  distanciaPromedio = np.mean(np.diff(picos)) / fs
  rpm = 60 / distanciaPromedio
  return True, round(float(rpm), 1)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 5005))

print("Escuchando datos CSI en el puerto 5005...")
escuchando = True
ultimo_guardado = 0

ultimo_print = 0
while escuchando:
  try:
    data, addr = sock.recvfrom(4096)

    if len(data) < 10:
      continue

    fasePromedio = parseCsi(data)
    buffer_temporal.append(fasePromedio)

    if len(buffer_temporal) >= 100:
      ondaLimpia = bandpass(
          np.array(buffer_temporal),
          low_cut=0.1,  # Nombre correcto del parámetro
          high_cut=0.5,
          fs=20,
          order=2,
      )
      presencia, rpm = CalcularRPM(ondaLimpia, fs=20)
      tiempo_actual = time.time()
    if tiempo_actual - ultimo_print >= 1.0:
      print(f"Presencia: {presencia} | RPM: {rpm}")
      ultimo_print = tiempo_actual
      # Muestra los datos en consola cada vez que calcula
      print(f"Presencia: {presencia} | RPM: {rpm}")

      # Lógica de BD (descomentar cuando tengas conexión a Internet/MongoDB)
      tiempo_actual = time.time()
      #if tiempo_actual - ultimo_guardado >= 1.0:
           #ultimo_guardado = tiempo_actual
           #sesion_activa = sesionActiva()
           #if sesion_activa:
               #guardar_medicion(str(sesion_activa["_id"]), presencia, rpm) 
               #print(f"Guardado en BD -> Presencia: {presencia} | RPM: {rpm}")
           #else:
               #print("No hay sesión activa")

  except KeyboardInterrupt:
    print("\nDeteniendo escucha UDP...")
    escuchando = False
    break
  except Exception as e:
    print(f"Error procesando paquete: {e}")

sock.close()