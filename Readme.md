pip install "fastapi[all]" uvicorn faster-whisper python-multipart


uvicorn api_whisper:app --host 127.0.0.1 --port 8000


curl -X 'POST' \
  'http://127.0.0.1:8000/translate' \
  -F 'model_size=small' \
  -F 'audio_file=@/ruta/a/tu/audio_en_espanol.mp3'

  pip install fastapi-cors

  python api_whisper.py


Correr servidor whisper(audio -> texto):
uvicorn api_whisper:app --host 127.0.0.1 --port 8000
Correr servidor VAD (detección de voz en audio):
uvicorn api_vad:app --host 127.0.0.1 --port 8001