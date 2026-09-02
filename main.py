from fastapi import FastAPI
app = FastAPI()
@app.get("/hola")
def read_root():
    return {"message": "lynceus aura"}

#python -m uvicorn main:app --reload --port 8000
#pip install fastapi "uvicorn[standard]" pip install fastapi
