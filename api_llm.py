# main.py (Tu API en el puerto 3000)

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# --- CONFIGURACIÓN ---

# ¡IMPORTANTE! Esta es la URL de la API REAL a la que quieres llamar
# Puede ser la de OpenAI o la de tu modelo local (ej: vLLM en el puerto 8000)
# ¡OJO! No pongas aquí "localhost:3000", eso crearías un bucle infinito.
# REAL_LLM_API_URL = "https://api.openai.com/v1/chat/completions"
REAL_LLM_API_URL = "http://localhost:3000/v1/chat/completions"
MODEL="openai/gpt-4.1"

# Tu API Key (mejor si la lees de una variable de entorno)
# No uses la "Bearer 2412" de tu ejemplo, usa tu clave real.
API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx" 

# Orígenes permitidos (tu frontend)
origins = ["*"]

# --- APLICACIÓN FASTAPI ---

app = FastAPI()

# Añade el middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Creamos un cliente HTTP que reutilizaremos
client = httpx.AsyncClient()

@app.post("/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    """
    Esta ruta recibe la petición de tu frontend,
    le añade la API key real, y la reenvía a la API de OpenAI.
    """
    print("[Proxy] Nueva petición de chat/completions recibida")
    print("[Proxy] Datos recibidos:", await request.json())
    try:
        # 1. Lee el JSON que envió tu frontend
        data = await request.json()

        # 2. Prepara las cabeceras para la API REAL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"  # ¡Usamos la clave secreta!
        }

        # 3. Llama a la API real del LLM
        response = await client.post(
            REAL_LLM_API_URL,
            json=data,
            headers=headers,
            timeout=60.0  # Damos un timeout de 60 segundos
        )

        # 4. Devuelve la respuesta exacta del LLM al frontend
        response.raise_for_status()  # Lanza un error si la API del LLM falló
        return JSONResponse(content=response.json(), status_code=response.status_code)

    except httpx.HTTPStatusError as e:
        # Si la API del LLM da un error (ej: 400, 401, 500), pásalo al frontend
        return JSONResponse(content=e.response.json(), status_code=e.response.status_code)
    except Exception as e:
        # Error genérico del proxy
        raise HTTPException(status_code=500, detail=f"Error en el proxy: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "Proxy de FastAPI para LLM está corriendo"}

# run: uvicorn api_llm:app --host 0.0.0.0 --port 3001