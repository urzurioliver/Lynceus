import collections
import os
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

from db import guardar_medicion, sesionActiva

# --- NUEVO: constantes del remuestreo ---
FS = 20             # muestras por segundo parejas tras remuestrear (igual al fs=20 de más abajo)
VENTANA_S = 20      # segundos de señal que se analizan (antes: 100 muestras ~ 4 s)
MAX_HUECO_S = 2.0   # si pasan más segundos sin frames, se considera un corte

# NUEVO: CSI crudo (carpeta junto a este archivo, un archivo por minuto)
CARPETA_CRUDO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos_crudos")
GUARDAR_CADA_S = 60
CSI_HDR_LEN = 20    # bytes de header del frame CSI antes de los datos I/Q

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

def prepararOnda(muestras):
    t = np.array([m[0] for m in muestras])
    v = np.array([m[1] for m in muestras])

    # Si hubo cortes largos, me quedo solo con el tramo posterior al último corte
    huecos = np.where(np.diff(t) > MAX_HUECO_S)[0]
    if len(huecos):
        t = t[huecos[-1] + 1:]
        v = v[huecos[-1] + 1:]

    if len(t) < 2:
        return None, "juntando señal tras un corte (0 s)"

    duracion = t[-1] - t[0]
    if duracion < VENTANA_S:
        return None, f"juntando señal continua tras un corte ({duracion:.0f}/{VENTANA_S} s)"

    # Remuestreo a ritmo fijo (las muestras llegan a intervalos irregulares)
    t_new = np.arange(t[0], t[-1], 1 / FS)
    onda = np.interp(t_new, t, v)
    return (onda - onda.mean()) / onda.mean(), ""

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
      print(f"Error guardando en BD ({type(e).__name__})")   # CAMBIO: mensaje corto


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


# NUEVO: CSI crudo -> datos_crudos/AAAAMMDD_HHMMSS_0001.npz, uno por minuto
#   iq   int8 (frames, 2*subportadoras), orden [imag, real, ...]:  z = iq[:, 1::2] + 1j * iq[:, 0::2]
#   t_s  tiempo del ESP32 (s)      t_pc  hora de la PC (epoch UTC, para cruzar con el timestamp de Mongo)
os.makedirs(CARPETA_CRUDO, exist_ok=True)
prefijo = time.strftime("%Y%m%d_%H%M%S")
lote = {"t_s": [], "t_pc": [], "seq": [], "rssi": [], "ruido": [], "iq": []}
n_archivo = 0
ultimo_volcado = time.time()


def guardarLote():
  global n_archivo
  if not lote["t_s"]:
    return
  n_archivo += 1
  np.savez_compressed(
      os.path.join(CARPETA_CRUDO, f"{prefijo}_{n_archivo:04d}.npz"),
      t_s=np.array(lote["t_s"], dtype=np.float64),
      t_pc=np.array(lote["t_pc"], dtype=np.float64),
      seq=np.array(lote["seq"], dtype=np.uint32),
      rssi=np.array(lote["rssi"], dtype=np.int8),
      ruido=np.array(lote["ruido"], dtype=np.int8),
      iq=np.array(lote["iq"], dtype=np.int8),
  )
  for k in lote:
    lote[k].clear()


puerto = sys.argv[1] if len(sys.argv) > 1 else PUERTO    # python csi_presencia.py COM5
print(f"Leyendo datos CSI por serial desde {puerto} a {BAUD} baud...")
print(f"CSI crudo en: {CARPETA_CRUDO}")
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
      t_seg = (t_us + t_off) / 1e6
      buffer_temporal.append((t_seg, valor))
      ultimo_frame_pc = time.time()
      # NUEVO: se descartan las muestras más viejas que la ventana
      while buffer_temporal[-1][0] - buffer_temporal[0][0] > VENTANA_S:
        buffer_temporal.popleft()

      # NUEVO: CSI crudo
      lote["t_s"].append(t_seg)
      lote["t_pc"].append(ultimo_frame_pc)
      lote["seq"].append(f["seq"])
      lote["rssi"].append(f["rssi"])
      lote["ruido"].append(f["ruido"])
      lote["iq"].append(np.frombuffer(payload, dtype=np.int8, offset=CSI_HDR_LEN))

    # CAMBIO: el análisis corre una vez por segundo (antes corría con cada paquete y solo
    # se mostraba una vez por segundo; el resultado es el mismo)
    tiempo_actual = time.time()
    if tiempo_actual - ultimo_print >= 1.0:
      ultimo_print = tiempo_actual

      if tiempo_actual - ultimo_volcado >= GUARDAR_CADA_S:   # NUEVO: cada minuto a disco
        guardarLote()
        ultimo_volcado = tiempo_actual

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

      # Lógica de BD
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
    guardarLote()
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

guardarLote()                             # NUEVO: lo que quedaba del CSI crudo
print("CSI crudo guardado.")