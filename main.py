from fastapi import FastAPI
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import json
from flask import Flask
from flask_cors import CORS


load_dotenv()  # Carga las variables del archivo .
url = os.getenv("mongourl")
client = MongoClient(url)
db = client["Lynceus"]
sesiones = db["sesiones"]

app = FastAPI()
CORS(app) 
#rutas
@app.get("/")
def mostrarinfo():
    return {"message": "Lynceus es un proyecto que permite la detección de vida dentro de derrumbes u otros terrenos de rescatismo"}
@app.get("/mappeo")
def mappeo():
    return {"message": f"acá podrás ver el mappeo, rpm: {rpm} y ritmo cardíaco"}
#hacer en compu ort pip install flask-cors