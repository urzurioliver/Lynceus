import os
from datetime import datetime, timezone
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi

load_dotenv()
url = os.getenv("mongourl")
client = MongoClient(url, serverSelectionTimeoutMS=5000, tlsCAFile=certifi.where())
try:
  client.admin.command("ping")
  print("Conectado exitosamente a MongoDB Atlas")
except Exception as e:
  print(f"ADVERTENCIA: No se pudo conectar a MongoDB Atlas ({e})")

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
  # Solo trae la última medición, no el arreglo completo
  return db.sesiones.find_one({"activa": True}, {"mediciones": {"$slice": -1}})

def mostrarSesiones():
  cursor = (
      db.sesiones.find({}, {"mediciones": {"$slice": -7}})
      .sort("fecha_inicio", -1)
      .limit(3)
  )
  return [
      {
          "id": str(sesion["_id"]),
          "nombre": sesion["nombre"],
          "fecha_inicio": sesion["fecha_inicio"],
          "fecha_fin": sesion.get("fecha_fin"),
          "activa": sesion["activa"],
          "mediciones": sesion["mediciones"],
      }
      for sesion in cursor
  ]

def renombrarSesion(sesion_id, nombre):
  db.sesiones.update_one(
      {"_id": ObjectId(sesion_id)},
      {"$set": {"nombre": nombre}}
  )

def guardar_medicion(sesion_id, presencia, rpm, **extra):
  medicion = {
      "medicion_id": str(ObjectId()),
      "timestamp": datetime.now(timezone.utc),
      "presencia": presencia,
      "rpm": rpm,
      **extra,
  }
  db.sesiones.update_one(
      {"_id": ObjectId(sesion_id)},
      {"$push": {"mediciones": medicion}}
  )