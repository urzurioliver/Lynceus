import os
from datetime import datetime, timezone
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()  # Carga las variables del archivo .
url = os.getenv("mongourl")
client = MongoClient(url)
db = client["Lynceus"]
sesiones = db["sesiones"]

def nuevaSesion(nombre="Nueva Sesión"):
  # Desactivar cualquier otra sesión previa 
  db.sesiones.update_many({"activa": True}, {"$set": {"activa": False}})

  nueva_sesion = {
      "nombre": nombre,
      "fecha_inicio": datetime.now(timezone.utc),
      "fecha_fin": None,
      "activa": True,
      "mediciones": [],
  }
  resultado = db.sesiones.insert_one(nueva_sesion)
  return str(resultado.inserted_id)

def detenerSesion():
  db.sesiones.update_many(
      {"activa": True},
      {"$set": {"activa": False, "fecha_fin": datetime.now(timezone.utc)}},
  )

def sesionActiva():
  return db.sesiones.find_one({"activa": True})

def guardar_medicion(sesion_id, presencia, rpm):
  medicion = {
      "medicion_id": str(ObjectId()),
      "timestamp": datetime.now(timezone.utc),
      "presencia": presencia,
      "rpm": rpm
  }
  db.sesiones.update_one(
      {"_id": ObjectId(sesion_id)},
      {"$push": {"mediciones": medicion}}
  )