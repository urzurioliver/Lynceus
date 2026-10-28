import collections
import queue
import sys
import threading
import time
from CSIKit.filters.passband import bandpass
import numpy as np
import serial
from scipy.signal import find_peaks

# NUEVO: del receptor se reutiliza lo que lee y valida las tramas del cable (CRC incluido)
from csi_serial_receiver import Deframer, parse_csi, PUERTO, BAUD

# Comentado mientras pruebas sin conexión a BD
from db import guardar_medicion, sesionActiva

# --- NUEVO: constantes del remuestreo ---
FS = 20             # muestras por segundo parejas tras remuestrear (igual al fs=20 de más abajo)
VENTANA_S = 30      # segundos de señal que se analizan (antes: 100 muestras ~ 4 s)
MAX_HUECO_S = 2.0   # si pasan más segundos sin frames, se considera un corte

# CAMBIO: ahora guarda pares (tiempo_s, valor) y se recorta por tiempo, no por cantidad
# (antes: collections.deque(maxlen=100) con solo valores)
buffer_temporal = collections.deque()

# NUEVO: cola para guardar en la BD desde otro hilo. Si Atlas tarda, el puerto serie
# no se atrasa (con serial, un atraso largo haría perder frames).
cola_bd = queue.Queue(maxsize=10)


def parseCsi(f):
  # CAMBIO: ya no recibe bytes de un paquete UDP. Recibe el frame decodificado por
  # csi_receiver.parse_csi (f["z"] = subportadoras complejas, con real/imag en el orden correcto).
  csi_complex = f["z"]

  # Tu cálculo original con fase (comentado, no borrado). La fase cruda del ESP32 tiene saltos
  # aleatorios entre paquetes, por eso se usa la amplitud:
  #fase = np.angle(csi_complex)
  #fasePromedio = np.mean(np.unwrap(fase))
  #return fasePromedio
  amp = np.abs(csi_complex)
  amp = amp[amp > 0]                        # descarta subportadoras nulas
  if len(amp) == 0:
    return None
  return float(amp.mean())


# --- NUEVO: remuestrea a tiempos parejos usando el tiempo real de cada frame ---
def prepararOnda(muestras):
  t = np.array([m[0] for m in muestras])
  v = np.array([m[1] for m in muestras])
  duracion = t[-1] - t[0]
  if duracion < VENTANA_S * 0.9:
    return None, f"juntando señal ({duracion:.0f}/{VENTANA_S} s)"
  hueco = np.diff(t).max()
  if hueco > MAX_HUECO_S:
    return None, f"hubo un corte de {hueco:.1f} s dentro de la ventana de {VENTANA_S} s"
  t_new = np.arange(t[0], t[-1], 1 / FS)
  onda = np.interp(t_new, t, v)
  return (onda - onda.mean()) / onda.mean(), ""   # variación relativa, centrada en 0


def CalcularRPM(ondaLimpia, fs=20):
  picos, _ = find_peaks(ondaLimpia, distance=fs, prominence=0.02)
  if len(picos) < 2:
    return False, 0.0

  distanciaPromedio = np.mean(np.diff(picos)) / fs
  rpm = 60 / distanciaPromedio
  return True, round(float(rpm), 1)


# NUEVO: tu lógica de BD, sin cambios, pero ejecutada en un hilo aparte
def trabajadorBD():
  while True:
    presencia, rpm = cola_bd.get()
    try:
      sesion_activa = sesionActiva()
      if sesion_activa:
          guardar_medicion(str(sesion_activa["_id"]), presencia, rpm)
          print(f"Guardado en BD -> Presencia: {presencia} | RPM: {rpm}")
      else:
          print("No hay sesión activa")
    except Exception as e:
      print(f"Error guardando en BD: {e}")


threading.Thread(target=trabajadorBD, daemon=True).start()


# NUEVO: abre el puerto serie igual que el receptor (sin resetear la placa) y reintenta si falla
def abrirSerial(puerto):
  while True:
    try:
      ser = serial.Serial()
      ser.port, ser.baudrate, ser.timeout = puerto, BAUD, 0.1
      ser.dtr = ser.rts = False              # evita que Windows resetee la placa al abrir
      ser.open()
      try:
        ser.set_buffer_size(rx_size=65536)   # solo Windows: más margen en el buffer de entrada
      except Exception:
        pass
      return ser
    except serial.SerialException as e:
      print(f"No se pudo abrir {puerto}: {e}")
      print("Cerrá csi_receiver.py, el monitor u otro programa que use ese puerto y revisá el número de COM. Reintentando...")
      time.sleep(3)


puerto = sys.argv[1] if len(sys.argv) > 1 else PUERTO    # python csi_presencia.py COM5
print(f"Leyendo datos CSI por serial desde {puerto} a {BAUD} baud...")
try:
  ser = abrirSerial(puerto)
except KeyboardInterrupt:
  print("\nCancelado")
  sys.exit()

dfr = Deframer()
nsub_votos = collections.Counter()
nsub_ref = None            # tamaño de frame que se analiza (el más frecuente al arrancar)
ultimo_t = None
t_off = 0
ultimo_frame_pc = time.time()
escuchando = True
ultimo_guardado = 0

ultimo_print = 0
while escuchando:
  try:
    data = ser.read(max(1, ser.in_waiting))

    for t_us, payload in dfr.feed(data):
      f = parse_csi(payload)
      if f is None:
        continue                          # paquete de sincronización u otro que no es CSI

      # NUEVO: el ESP32 puede mandar frames de distinto tamaño; mezclarlos ensucia la señal.
      # Se vota con los primeros 40 y después se usa solo el tamaño más frecuente.
      if nsub_ref is None:
        nsub_votos[f["nsub"]] += 1
        if sum(nsub_votos.values()) < 40:
          continue
        nsub_ref = nsub_votos.most_common(1)[0][0]
        print(f"Se analizan los frames de {nsub_ref} subportadoras")
      if f["nsub"] != nsub_ref:
        continue

      # NUEVO: tiempo del ESP32 en segundos. El contador es de 32 bits y da la vuelta
      # cada ~71 min; si vuelve a 0 antes, el ESP32 se reinició.
      if ultimo_t is not None and t_us < ultimo_t:
        if ultimo_t > (1 << 31):
          t_off += 1 << 32
        else:
          buffer_temporal.clear()
          t_off = 0
      ultimo_t = t_us

      valor = parseCsi(f)
      if valor is None:
        continue
      buffer_temporal.append(((t_us + t_off) / 1e6, valor))
      ultimo_frame_pc = time.time()
      # NUEVO: se descartan las muestras más viejas que la ventana
      while buffer_temporal[-1][0] - buffer_temporal[0][0] > VENTANA_S:
        buffer_temporal.popleft()

    # CAMBIO: el análisis corre una vez por segundo (antes corría con cada paquete y solo
    # se mostraba una vez por segundo; el resultado es el mismo)
    tiempo_actual = time.time()
    if tiempo_actual - ultimo_print >= 1.0:
      ultimo_print = tiempo_actual

      if not buffer_temporal:
        onda, motivo = None, "todavía no llegan frames CSI"
      elif tiempo_actual - ultimo_frame_pc > MAX_HUECO_S:
        onda, motivo = None, f"no llegan frames hace {tiempo_actual - ultimo_frame_pc:.0f} s"
      else:
        onda, motivo = prepararOnda(buffer_temporal)
      if onda is None:
        print(f"Esperando datos continuos... ({motivo})")
        continue

      ondaLimpia = bandpass(
          onda,
          low_cut=0.1,  # Nombre correcto del parámetro
          high_cut=0.5,
          fs=20,
          order=2,
      )
      presencia, rpm = CalcularRPM(ondaLimpia, fs=20)
      # Muestra los datos en consola cada vez que calcula
      print(f"Presencia: {presencia} | RPM: {rpm}")

      # Lógica de BD (descomentar cuando tengas conexión a Internet/MongoDB)
      tiempo_actual = time.time()
      if tiempo_actual - ultimo_guardado >= 1.0:
           ultimo_guardado = tiempo_actual
           try:
             cola_bd.put_nowait((presencia, rpm))
           except queue.Full:
             pass                         # la BD está muy lenta: se salta esta medición

  except KeyboardInterrupt:
    print("\nDeteniendo lectura serial...")
    escuchando = False
    break
  except OSError as e:
    # NUEVO: el cable se desconectó o el puerto dejó de responder
    print(f"Se perdió la conexión con {puerto}: {e}")
    try:
      ser.close()
    except Exception:
      pass
    try:
      time.sleep(2)
      ser = abrirSerial(puerto)
    except KeyboardInterrupt:
      escuchando = False
      break
    dfr = Deframer()
    ultimo_t = None
    t_off = 0
    buffer_temporal.clear()
    ultimo_frame_pc = time.time()
  except Exception as e:
    print(f"Error procesando paquete: {e}")

try:
  ser.close()
except Exception:
  pass