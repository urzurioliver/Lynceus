from fastapi import FastAPI
from db import (detenerSesion, sesionActiva, nuevaSesion, guardar_medicion, mostrarSesiones, renombrarSesion)
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#rutas
@app.post("/sesiones/nueva")
def postNuevaSesion(nombre: str = "prueba"):
  sesion_id = nuevaSesion(nombre)
  return {
      "mensaje": "Sesión iniciada correctamente",
      "sesion_id": sesion_id,
  }
@app.get("/live")
def getSesionActiva():
  sesion_activa = sesionActiva()

  if not sesion_activa or not sesion_activa.get("mediciones"):
    return {
        "activa": False,
        "presencia": False,
        "rpm": 0.0,
    }

  ultima_medicion = sesion_activa["mediciones"][-1] #-1 agarra el ultimo
  ultima_medicion["activa"] = True
  ultima_medicion["sesion_id"] = str(sesion_activa["_id"])
  return ultima_medicion

@app.post("/sesiones/detener")
def postDetenerSesion():
  detenerSesion()
  return {"mensaje": "Sesión finalizada"}

@app.get("/sesiones/historial")
def postHistorial():
  return mostrarSesiones()

@app.put("/sesiones/{sesion_id}/nombre")
def putNombre(sesion_id: str, nombre: str):
  renombrarSesion(sesion_id, nombre)
  return {"mensaje": "Nombre actualizado"}

