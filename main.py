from fastapi import FastAPI

app = FastAPI()
#rutas
@app.get("/")
def mostrarinfo():
    return {"message": "Lynceus es un proyecto que permite la detección de vida dentro de derrumbes u otros terrenos de rescatismo"}
@app.get("/mappeo")
def mappeo():
    return {"message": f"acá podrás ver el mappeo, rpm: {rpm} y ritmo cardíaco"}
#creo que debo primero hacer una base de datos no relacional jajan't 
#Might use MongoDB
#python -m uvicorn main:app --reload --port 8000
#pip install fastapi "uvicorn[standard]" pip install fastapi
