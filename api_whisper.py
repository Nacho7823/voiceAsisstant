'''
Endpoints
---------
GET /models
    - Descripción: Devuelve la lista de tamaños de modelo soportados.
    - Respuesta (200): JSON con lista de modelos, p. ej. ["tiny","base","small","medium","large-v2","large-v3"]

GET /languages
    - Descripción: Devuelve la lista de idiomas soportados por la API (incluye "auto").
    - Respuesta (200): JSON con lista de códigos de idioma, p. ej. ["auto","en","es",...]

POST /translate
    - Descripción: Transcribe o traduce un archivo de audio (respuesta tradicional).
    - Tipo: multipart/form-data

POST /translate_stream
    - Descripción: Transcribe/Traduce audio y emite segmentos por SSE (server-sent events).
    - Respuesta: text/event-stream. Primer evento contiene job_id y metadatos.

POST /stop/{job_id}
    - Descripción: Solicita la parada de una transcripción en curso.
'''

'''
GGML_VULKAN=1 pip install git+https://github.com/absadiki/pywhispercpp
'''
    
    
'''
llamada a whisper.cpp
curl 127.0.0.1:8080/inference \
-H "Content-Type: multipart/form-data" \
-F file="@<file-path>" \
-F temperature="0.0" \
-F temperature_inc="0.2" \
-F response_format="json"
'''

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
import os
import tempfile
from typing import Literal, Dict, Any, Optional
from fastapi.middleware.cors import CORSMiddleware
import requests
import uuid
import threading
import asyncio
from fastapi.responses import StreamingResponse, JSONResponse
import json
import time

# ------------------
# Cache local de modelos
# ------------------
SAVE_AUDIOS = True  # Mantienes tu configuración

BASE_DIR = os.path.dirname(__file__)
MODELS_DIR = os.path.join(BASE_DIR, "models")
AUDIOS_DIR = os.path.join(BASE_DIR, "audios")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(AUDIOS_DIR, exist_ok=True)

os.environ.setdefault("HF_HOME", MODELS_DIR)
os.environ.setdefault("TRANSFORMERS_CACHE", MODELS_DIR)
os.environ.setdefault("XDG_CACHE_HOME", MODELS_DIR)

print(f"Model cache dir: {MODELS_DIR}")
# ------------------

# --- Configuración (Modifica esto según tu PC) ---
COMPUTE_DEVICE = "cuda"  # Opciones: "cpu", "cuda", "mps"
COMPUTE_TYPE = "float32"  # Opciones: "int8", "int16", "float16", "float32"
# ----------------------------------------------------

availableModels = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
availableLanguajes = ["auto", "en", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "ko"]

ModelSize = Literal["tiny", "base", "small", "medium", "large-v2", "large-v3"]

app = FastAPI()

# --- Configuración de CORS ---
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -----------------------------

def call_whisper_cpp_api(
    audio_path: str, 
    temperature: float = 0.0, 
    temperature_inc: float = 0.2,
    language: str = "auto"
) -> Dict[str, Any]:
    """
    Llama a la API de whisper.cpp para procesar el archivo de audio.
    """
    url = "http://127.0.0.1:8080/inference"
    with open(audio_path, "rb") as audio_file:
        files = {"file": audio_file}
        data = {
            "temperature": temperature,
            "temperature_inc": temperature_inc,
            "response_format": "json",
            "language": language
        }
        response = requests.post(url, files=files, data=data)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        text = response.json().get("text", "")
        print(f"[whisper.cpp] Respuesta recibida: {response.json()}")   
        print(f"[whisper.cpp] Respuesta recibida: {text}")   
        return text

@app.get("/models")
async def getModels():
    """
    Endpoint para obtener la lista de modelos disponibles.
    """
    return availableModels

@app.get("/languages")
async def getLanguajes():
    return availableLanguajes

@app.post("/translate")
async def translate_audio(
    model_size: ModelSize = Form("small"),
    audio_file: UploadFile = File(...),
    language: str = Form("es")
):
    """
    Endpoint de API para traducir audio (respuesta tradicional).
    """
    tmp_file_path: Optional[str] = None
    try:
        # Guardar el archivo de audio
        if SAVE_AUDIOS:
            os.makedirs(AUDIOS_DIR, exist_ok=True)
            name = "audio" + str(int(time.time() * 1000))
            name += "_" + (audio_file.filename or "upload.wav")
            safe_name = os.path.basename(name)
            dst_path = os.path.join(AUDIOS_DIR, safe_name)
            try:
                print(f"[audio] Guardando audio en: {dst_path}")
                content = await audio_file.read()
                with open(dst_path, "wb") as f:
                    f.write(content)
                tmp_file_path = dst_path
                try:
                    size = os.path.getsize(dst_path)
                    print(f"[audio] Guardado {size} bytes en {dst_path}")
                except Exception:
                    print(f"[audio] Guardado en {dst_path} (tamaño desconocido)")
            except Exception as e:
                print(f"[audio][error] No se pudo guardar el audio en {dst_path}: {e}")
                raise HTTPException(status_code=500, detail=f"Error al guardar audio: {e}")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=audio_file.filename or ".wav") as tmp_file:
                content = await audio_file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name

        # Llamar a whisper.cpp API
        result = call_whisper_cpp_api(tmp_file_path, language=language)
        
        return {
            "model_used": model_size,
            # "detected_language": info.language,
            "language_requested": language,
            # "task_used": task,
            "result_text": result
        }
        

    except Exception as e:
        print(f"[ERROR] Error durante la transcripción: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Limpieza de archivo temporal si corresponde
        if not SAVE_AUDIOS and tmp_file_path and os.path.exists(tmp_file_path):
            try:
                print(f"Limpiando archivo temporal: {tmp_file_path}")
                os.unlink(tmp_file_path)
            except Exception:
                pass
        elif SAVE_AUDIOS and tmp_file_path:
            print(f"Audio conservado en: {tmp_file_path}")

if __name__ == "__main__":
    print(f"--- Iniciando Servidor de API Whisper ---")
    print(f"Dispositivo: {COMPUTE_DEVICE} (Tipo: {COMPUTE_TYPE})")
    print(f"Modelos disponibles: tiny, base, small, medium, large-v2, large-v3")
    print(f"Endpoint disponible en: http://127.0.0.1:8000/translate_stream (SSE)")
    print("Inicia con: uvicorn api_whisper:app --host 127.0.0.1 --port 8000")
    # uvicorn.run(app, host="127.0.0.1", port=8000")
