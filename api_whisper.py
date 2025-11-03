import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from faster_whisper import WhisperModel
import os
import tempfile
from typing import Literal
from fastapi.middleware.cors import CORSMiddleware  # <-- AÑADIR ESTA LÍNEA

# ------------------
# Cache local de modelos
# ------------------
# Directorio donde se guardarán los modelos descargados para evitar
# descargarlos cada vez. Puedes cambiar esto a una ruta absoluta
# si lo prefieres (ej: r"C:\models_whisper").
BASE_DIR = os.path.dirname(__file__)
MODELS_DIR = os.path.join(BASE_DIR, "models")

# Asegurarse que el directorio exista
os.makedirs(MODELS_DIR, exist_ok=True)

# Indicar a las librerías de HuggingFace / transformers que usen este
# directorio como cache para los modelos. Esto evita descargas repetidas.
# También establecemos XDG_CACHE_HOME por compatibilidad con algunas libs.
os.environ.setdefault("HF_HOME", MODELS_DIR)
os.environ.setdefault("TRANSFORMERS_CACHE", MODELS_DIR)
os.environ.setdefault("XDG_CACHE_HOME", MODELS_DIR)

# Para información del usuario en logs
print(f"Model cache dir: {MODELS_DIR}")
# ------------------

# --- Configuración (Modifica esto según tu PC) ---

# Define si usarás "cuda" (GPU NVIDIA) o "cpu"
COMPUTE_DEVICE = "cpu"
# Define el tipo de cómputo: "float16" para GPU, "int8" para CPU
COMPUTE_TYPE = "int8" 

# ----------------------------------------------------

# Define los modelos permitidos que el usuario puede elegir
ModelSize = Literal["tiny", "base", "small", "medium", "large-v2", "large-v3"]

app = FastAPI()

# --- Configuración de CORS ---                 # <-- AÑADIR ESTA LÍNEA
# Esto permite que tu navegador (desde cualquier origen)
# se conecte a esta API.
origins = ["*"]  # Para desarrollo. Sé más restrictivo en producción.

app.add_middleware(                             # <-- AÑADIR ESTA LÍNEA
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -----------------------------

# Usamos un diccionario como caché simple para no recargar modelos
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
            # Si falla la carga (ej: modelo no existe, VRAM insuficiente)
            raise HTTPException(
                status_code=500, 
                detail=f"Error al cargar el modelo {model_size}: {e}"
            )
    return model_cache[model_size]

@app.post("/translate")
async def translate_audio(
    # El usuario puede elegir el modelo desde el formulario. 'base' es el default.
    model_size: ModelSize = Form("base"),
    audio_file: UploadFile = File(...),
    # target_language acepta 'auto' (detectar), o códigos como 'es','en','fr', etc.
    target_language: str = Form("auto")
):
    """
    Endpoint de API para traducir audio.
    Recibe un archivo de audio y el tamaño del modelo a utilizar.
    """
    tmp_file_path = None
    try:
        # 1. Cargar el modelo (o tomarlo del caché)
        model = get_model(model_size)

        # 2. Guardar el archivo de audio temporalmente
        # Usamos tempfile para manejar archivos temporales de forma segura
        with tempfile.NamedTemporaryFile(delete=False, suffix=audio_file.filename) as tmp_file:
            content = await audio_file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        # 3. Ejecutar la transcripción/traducción.
        # Lógica:
        # - Si target_language == 'auto' o 'en' usamos task='translate' (traduce al inglés).
        # - Si target_language es otro código (ej: 'es','fr'), hacemos task='transcribe'
        #   y devolvemos la transcripción en el idioma detectado/forzado.
        # Nota: faster-whisper soporta pasar 'language' para forzar el idioma fuente.
        language_param = None if target_language == 'auto' else target_language
        if target_language == 'auto' or target_language == 'en':
            task = "translate"
        else:
            task = "transcribe"

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
            "target_language_requested": target_language,
            "task_used": task,
            "result_text": full_text.strip()
        }

    except Exception as e:
        # Manejo de errores
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 6. Limpiar el archivo temporal después de usarlo
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)

if __name__ == "__main__":
    print(f"--- Iniciando Servidor de API Whisper ---")
    print(f"Dispositivo: {COMPUTE_DEVICE} (Tipo: {COMPUTE_TYPE})")
    print(f"Modelos disponibles: tiny, base, small, medium, large-v2, large-v3")
    print(f"Endpoint disponible en: http://127.0.0.1:8000/translate")
    print("Inicia con: uvicorn api_whisper:app --host 127.0.0.1 --port 8000")
    # uvicorn.run(app, host="127.0.0.1", port=8000) # Descomenta para correr con 'python api_whisper.py'
    
# uvicorn api_whisper:app --host 127.0.0.1 --port 8000