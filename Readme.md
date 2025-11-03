pip install "fastapi[all]" uvicorn faster-whisper python-multipart


uvicorn api_whisper:app --host 127.0.0.1 --port 8000


curl -X 'POST' \
  'http://127.0.0.1:8000/translate' \
  -F 'model_size=small' \
  -F 'audio_file=@/ruta/a/tu/audio_en_espanol.mp3'

  pip install fastapi-cors


## Iniciar
uv venv -p 3.11 .venv
.\.venv\Scripts\activate


## Correr servidor whisper(audio -> texto):
uvicorn api_whisper:app --host 127.0.0.1 --port 8000

## Correr servidor VAD (detección de voz en audio):
uvicorn api_vad:app --host 127.0.0.1 --port 8001

## Correr web cliente:
python -m http.server 8080

## Probar endpoint de traducción:
test_vad_whisper.html

## Probar llm
testllm.html

## Probar vad
testvad.html

## System Prompt

Eres un asistente personal llamado jarvis.
Tu tarea es ayudar al usuario con sus preguntas y solicitudes de la mejor manera posible.
Siempre responde en español.
Recibes texto traducido desde audios, por lo que pueden tener errores de traducción.
Debes dar respuestas claras y concisas.


