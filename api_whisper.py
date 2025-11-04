'''API Whisper - Documentación de la API

Descripción
-----------
API ligera basada en FastAPI que utiliza `faster_whisper.WhisperModel` para:
- Transcribir audio a texto.
- Traducir audio a otro idioma cuando procede (autodetección o petición explícita).

La API espera recibir archivos de audio mediante multipart/form-data y devuelve el texto resultante junto con metadatos sobre el modelo y el idioma detectado/solicitado.

Endpoints
---------
GET /models
    - Descripción: Devuelve la lista de tamaños de modelo soportados.
    - Respuesta (200): JSON con lista de modelos, p. ej. ["tiny","base","small","medium","large-v2","large-v3"]

GET /languages
    - Descripción: Devuelve la lista de idiomas soportados por la API (incluye "auto").
    - Respuesta (200): JSON con lista de códigos de idioma, p. ej. ["auto","en","es",...]

POST /translate
    - Descripción: Transcribe o traduce un archivo de audio.
    - Tipo: multipart/form-data
    - Campos:
        - model_size (form, opcional): tamaño del modelo a usar. Valores permitidos: "tiny", "base", "small", "medium", "large-v2", "large-v3". Default: "small".
        - audio_file (file, requerido): archivo de audio a procesar (wav, mp3, m4a, etc).
        - language (form, opcional): código de idioma solicitado. 
            - "auto" o cadena vacía ("") → autodetección.
            - "en","es","fr",... → forzar ese idioma.
            - Default en el servidor: "es" si el cliente no envía el campo.
    - Comportamiento:
        - Si `language` es "" o "auto" se realiza autodetección. 
        - Si autodetect o idioma solicitado es "en", la operación usará task="translate" (traduce a inglés->target language por defecto del modelo).
        - Si se especifica un idioma distinto de "en" y no es autodetección, se usa task="transcribe".
        - Si la opción SAVE_AUDIOS está activa, el audio se guarda en la carpeta `audios/`; si no, se usa un archivo temporal que se borra al finalizar.
    - Respuesta (200): JSON con:
        - model_used: tamaño del modelo usado.
        - detected_language: idioma detectado por el modelo.
        - language_requested: valor recibido en el formulario (puede ser "").
        - task_used: "translate" o "transcribe".
        - result_text: texto transcrito/traducido (string).
    - Errores:
        - 400/422: errores de validación de request por parte de FastAPI.
        - 500: errores internos (carga de modelo, I/O, transcripción). Se devuelve {"detail": "..."}.

Configuración importante (en el código)
---------------------------------------
- SAVE_AUDIOS (bool): si True guarda los audios en `audios/`. Si False usa temporales y los borra.
- MODELS_DIR / AUDIOS_DIR: directorios locales para caché de modelos y audios.
- COMPUTE_DEVICE: "cpu", "cuda" o "mps".
- COMPUTE_TYPE: "int8", "int16", "float16", "float32".

Ejemplo de uso (curl)
---------------------
curl -X POST "http://127.0.0.1:8000/translate" \
  -F "model_size=small" \
  -F "language=es" \
  -F "audio_file=@./ejemplo.wav"

Respuesta esperada (ejemplo)
---------------------------
{
  "model_used": "small",
  "detected_language": "es",
  "language_requested": "es",
  "task_used": "transcribe",
  "result_text": "Texto transcrito o traducido..."
}

Notas de implementación
-----------------------
- La API mantiene un caché en memoria (`model_cache`) para evitar recargar modelos entre peticiones.
- CORS está configurado con allow_origins="*" para facilitar pruebas; ajustar en producción.
- Los modelos y caches se almacenan en la carpeta `models/` (variable HF_HOME/TRANSFORMERS_CACHE/XDG_CACHE_HOME).
- Para correr el servidor localmente:
    uvicorn api_whisper:app --host 127.0.0.1 --port 8000

'''
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
COMPUTE_DEVICE = "cpu" # Opciones: "cpu", "cuda", "mps"
COMPUTE_TYPE = "int8" # Opciones: "int8", "int16", "float16", "float32"
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

@app.get("/models")
async def getModels():
    """
    Endpoint para obtener la lista de modelos disponibles.
    """
    return {
        availableModels
    }
    
@app.get("/languages")
async def getLanguajes():
    return {
        availableLanguajes
    }

@app.post("/translate")
async def translate_audio(
    model_size: ModelSize = Form("small"),
    audio_file: UploadFile = File(...),
    # El cliente envía "" (vacío) para auto, no "auto". El default "auto"
    # solo se usaría si el cliente NO envía el parámetro.
    language: str = Form("es") 
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
