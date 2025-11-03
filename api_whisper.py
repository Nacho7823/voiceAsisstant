import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from faster_whisper import WhisperModel
import os
import tempfile
from typing import Literal
from fastapi.middleware.cors import CORSMiddleware

# ------------------
# Cache local de modelos
# ------------------
SAVE_AUDIOS = True # Mantienes tu configuración

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
COMPUTE_DEVICE = "cpu"
COMPUTE_TYPE = "int8" 
# ----------------------------------------------------

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

model_cache = {}

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

@app.post("/translate")
async def translate_audio(
    model_size: ModelSize = Form("base"),
    audio_file: UploadFile = File(...),
    # El cliente envía "" (vacío) para auto, no "auto". El default "auto"
    # solo se usaría si el cliente NO envía el parámetro.
    language: str = Form("auto") 
):
    """
    Endpoint de API para traducir audio.
    Recibe un archivo de audio y el tamaño del modelo a utilizar.
    """
    tmp_file_path = None
    try:
        # 1. Cargar el modelo
        model = get_model(model_size)

        # 2. Guardar el archivo de audio
        if SAVE_AUDIOS:
            os.makedirs(AUDIOS_DIR, exist_ok=True)
            name = "audio" + str(int(os.times().system * 1000))
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
                # Lanzamos el error para que FastAPI devuelva un 500
                raise HTTPException(status_code=500, detail=f"Error al guardar audio: {e}")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=audio_file.filename) as tmp_file:
                content = await audio_file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name

        
        # 3. Ejecutar la transcripción/traducción.
        
        # --- CORRECCIÓN DEL BUG 1 (Error 500) ---
        # El cliente envía "" (string vacío) para 'auto-detectar'.
        # Tratamos "" y "auto" (default) como auto-detección.
        is_auto_detect = (language == "auto" or language == "")
        
        language_param = None if is_auto_detect else language
        
        # Si es auto-detect O el idioma es inglés, traducimos (task='translate')
        if is_auto_detect or language == "en":
            task = "translate"
        else:
            # Si se especifica un idioma (es, fr, de...), transcribimos (task='transcribe')
            task = "transcribe"
        # --- FIN DE LA CORRECCIÓN ---

        transcribe_kwargs = { 'task': task }
        if language_param:
            transcribe_kwargs['language'] = language_param

        segments, info = model.transcribe(
            tmp_file_path,
            **transcribe_kwargs
        )

        print(f"Idioma detectado: {info.language} (Probabilidad: {info.language_probability:.2f}) | task={task} | forced_language={language_param}")

        # 4. Concatenar todos los segmentos de texto
        full_text = "".join(segment.text for segment in segments)

        # 5. Retornar el resultado
        return {
            "model_used": model_size,
            "detected_language": info.language,
            "language_requested": language, # Devuelve "" si fue auto
            "task_used": task,
            "result_text": full_text.strip()
        }

    except Exception as e:
        # Manejo de errores
        print(f"[ERROR] Error durante la transcripción: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # --- CORRECCIÓN DEL BUG 2 (Borrado de archivos) ---
        # 6. Limpiar el archivo temporal SI NO estamos guardando audios
        if not SAVE_AUDIOS and tmp_file_path and os.path.exists(tmp_file_path):
            print(f"Limpiando archivo temporal: {tmp_file_path}")
            os.unlink(tmp_file_path)
        elif SAVE_AUDIOS and tmp_file_path:
            # Si SAVE_AUDIOS es True, no lo borramos.
            print(f"Audio conservado en: {tmp_file_path}")
        # --- FIN DE LA CORRECCIÓN ---

if __name__ == "__main__":
    print(f"--- Iniciando Servidor de API Whisper ---")
    print(f"Dispositivo: {COMPUTE_DEVICE} (Tipo: {COMPUTE_TYPE})")
    print(f"Modelos disponibles: tiny, base, small, medium, large-v2, large-v3")
    print(f"Endpoint disponible en: http://127.0.0.1:8000/translate")
    print("Inicia con: uvicorn api_whisper:app --host 127.0.0.1 --port 8000")
    
    # Descomenta la siguiente línea si prefieres correr con 'python api_whisper.py'
    # uvicorn.run(app, host="127.0.0.1", port=8000)
