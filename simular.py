import random
import time
from db import guardar_medicion, sesionActiva

while True:
  sesion = sesionActiva()
  if sesion:
    guardar_medicion(
        str(sesion["_id"]), True, round(random.uniform(12, 20), 1),
        distancia=round(random.uniform(1, 3.5), 2),
        angulo=round(random.uniform(20, 100), 1),
        ppm=round(random.uniform(60, 90), 1),
    )
    print("Medición simulada guardada")
  else:
    print("No hay sesión activa: apretá Iniciar en la web")
  time.sleep(1)