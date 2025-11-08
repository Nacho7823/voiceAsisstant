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




import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from faster_whisper import WhisperModel
import os
import tempfile
from typing import Literal, Dict, Any, Optional
from fastapi.middleware.cors import CORSMiddleware

# Nuevos imports para streaming / control
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
COMPUTE_DEVICE = "cpu"  # Opciones: "cpu", "cuda", "mps"
COMPUTE_TYPE = "int16"  # Opciones: "int8", "int16", "float16", "float32"
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

model_cache: Dict[str, WhisperModel] = {}


def get_model(model_size: str) -> WhisperModel:
    """
    Carga un modelo en el caché si no existe y lo retorna.
    """
    if model_size not in model_cache:
        print(f"Cargando modelo '{model_size}' en {COMPUTE_DEVICE}...")
        try:
            model = WhisperModel(model_size, device=COMPUTE_DEVICE, compute_type=COMPUTE_TYPE)
            model_cache[model_size] = model
            print(f"Modelo '{model_size}' cargado y listo.")
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al cargar el modelo {model_size}: {e}"
            )
    return model_cache[model_size]


# -------------------------------
# Job registry global para control de parada
# job_registry: job_id -> threading.Event()
# -------------------------------
job_registry: Dict[str, threading.Event] = {}
# opcional para debug/info: guardar metadatos
job_meta: Dict[str, Dict[str, Any]] = {}


def sse_format(data: str) -> str:
    """Formatea un string para SSE"""
    return f"data: {data}\n\n"


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
    # El cliente envía "" (vacío) para auto, no "auto". El default "auto"
    # solo se usaría si el cliente NO envía el parámetro.
    language: str = Form("es")
):
    """
    Endpoint de API para traducir audio (respuesta tradicional).
    """
    tmp_file_path: Optional[str] = None
    try:
        # 1. Cargar el modelo
        model = get_model(model_size)

        # 2. Guardar el archivo de audio
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

        # 3. Ejecutar la transcripción/traducción.
        is_auto_detect = (language == "auto" or language == "")
        language_param = None if is_auto_detect else language
        if is_auto_detect or language == "en":
            task = "translate"
        else:
            task = "transcribe"

        transcribe_kwargs = {'task': task}
        if language_param:
            transcribe_kwargs['language'] = language_param

        segments, info = get_model(model_size).transcribe(
            tmp_file_path,
            **transcribe_kwargs
        )

        print(f"Idioma detectado: {info.language} (Probabilidad: {getattr(info, 'language_probability', 0):.2f}) | task={task} | forced_language={language_param}")

        full_text = "".join(segment.text for segment in segments)

        return {
            "model_used": model_size,
            "detected_language": info.language,
            "language_requested": language,
            "task_used": task,
            "result_text": full_text.strip()
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


@app.post("/translate_stream")
async def translate_stream(
    model_size: ModelSize = Form("small"),
    audio_file: UploadFile = File(...),
    language: str = Form("es")
):
    """
    Endpoint streaming vía SSE. Emite eventos JSON en formato:
    { "type": "meta"|"segment"|"stopped"|"error"|"end", "payload": { ... } }
    Primer evento incluye job_id y metadatos.
    """
    tmp_file_path: Optional[str] = None
    try:
        # Guardar audio (reutiliza lógica)
        if SAVE_AUDIOS:
            os.makedirs(AUDIOS_DIR, exist_ok=True)
            name = "audio" + str(int(time.time() * 1000))
            name += "_" + (audio_file.filename or "upload.wav")
            safe_name = os.path.basename(name)
            dst_path = os.path.join(AUDIOS_DIR, safe_name)
            content = await audio_file.read()
            with open(dst_path, "wb") as f:
                f.write(content)
            tmp_file_path = dst_path
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=audio_file.filename or ".wav") as tmp_file:
                content = await audio_file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name

        # Preparar job
        model = get_model(model_size)
        job_id = str(uuid.uuid4())
        q: asyncio.Queue = asyncio.Queue()
        cancel_flag = threading.Event()
        job_registry[job_id] = cancel_flag
        job_meta[job_id] = {"model_used": model_size, "created_at": time.time()}

        loop = asyncio.get_running_loop()

        def transcribe_worker():
            try:
                is_auto_detect = (language == "auto" or language == "")
                language_param = None if is_auto_detect else language
                task = "translate" if (is_auto_detect or language == "en") else "transcribe"
                transcribe_kwargs = {'task': task}
                if language_param:
                    transcribe_kwargs['language'] = language_param

                # Ejecuta transcripción. segments puede ser iterable/generador
                segments, info = model.transcribe(tmp_file_path, **transcribe_kwargs)

                # enviar meta
                meta = {
                    "job_id": job_id,
                    "model_used": model_size,
                    "detected_language": getattr(info, "language", None),
                    "task_used": task
                }
                loop.call_soon_threadsafe(q.put_nowait, json.dumps({"type": "meta", "payload": meta}))

                for segment in segments:
                    if cancel_flag.is_set():
                        loop.call_soon_threadsafe(q.put_nowait, json.dumps({"type": "stopped", "payload": {"reason": "cancelled"}}))
                        break
                    payload = {
                        "text": segment.text,
                        "start": getattr(segment, "start", None),
                        "end": getattr(segment, "end", None)
                    }
                    loop.call_soon_threadsafe(q.put_nowait, json.dumps({"type": "segment", "payload": payload}))

            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, json.dumps({"type": "error", "payload": {"detail": str(e)}}))
            finally:
                # señal de fin
                loop.call_soon_threadsafe(q.put_nowait, None)

        thread = threading.Thread(target=transcribe_worker, daemon=True)
        thread.start()

        async def event_generator():
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        yield sse_format(json.dumps({"type": "end"}))
                        break
                    yield sse_format(item)
            except asyncio.CancelledError:
                # cliente cerró la conexión; solicitar parada
                cancel_flag.set()
                raise
            finally:
                # cleanup
                job_registry.pop(job_id, None)
                job_meta.pop(job_id, None)
                if not SAVE_AUDIOS and tmp_file_path and os.path.exists(tmp_file_path):
                    try:
                        os.unlink(tmp_file_path)
                    except Exception:
                        pass

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        # En caso de error, intentar limpieza inmediata
        if job_registry.get(job_id):
            job_registry.pop(job_id, None)
        if tmp_file_path and not SAVE_AUDIOS and os.path.exists(tmp_file_path):
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stop/{job_id}")
async def stop_job(job_id: str):
    """
    Endpoint que solicita la parada de una transcripción en curso.
    """
    ev = job_registry.get(job_id)
    if not ev:
        raise HTTPException(status_code=404, detail="job_id no encontrado o ya finalizado")
    ev.set()
    return JSONResponse({"job_id": job_id, "stopped": True})


if __name__ == "__main__":
    print(f"--- Iniciando Servidor de API Whisper ---")
    print(f"Dispositivo: {COMPUTE_DEVICE} (Tipo: {COMPUTE_TYPE})")
    print(f"Modelos disponibles: tiny, base, small, medium, large-v2, large-v3")
    print(f"Endpoint disponible en: http://127.0.0.1:8000/translate_stream (SSE)")
    print("Inicia con: uvicorn api_whisper:app --host 127.0.0.1 --port 8000")
    # uvicorn.run(app, host="127.0.0.1", port=8000)
