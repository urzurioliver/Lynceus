from fastapi import FastAPI
from db import detenerSesion, sesionActiva, nuevaSesion, guardar_medicion
from flask import Flask
from flask_cors import CORS

app = FastAPI()
CORS(app) 
#rutas
@app.get("/")
def mostrarinfo():
    return {"message": "Lynceus es un proyecto que permite la detección de vida dentro de derrumbes u otros terrenos de rescatismo"}
@app.get("/mappeo")
def mappeo():
    return {"message": f"acá podrás ver el mappeo, rpm: {rpm} y ritmo cardíaco"}
