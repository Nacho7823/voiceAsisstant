# Voice asistant

## Instalación de dependencias

pip install "fastapi[all]" uvicorn faster-whisper python-multipart fastapi-cors


## Api de whisper
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/translate' \
  -F 'model_size=small' \
  -F 'audio_file=@/ruta/a/tu/audio_en_espanol.mp3'
```

## Iniciar
uv venv -p 3.11 .venv
.\.venv\Scripts\activate


## Correr servidor whisper(audio -> texto):
uvicorn api_whisper:app --host 127.0.0.1 --port 8000

## Correr servidor VAD (detección de voz en audio):
uvicorn api_vad:app --host 127.0.0.1 --port 8001

## Correr web cliente:
cd client
python -m http.server 8080

## Correr llm proxy(error cors):
uvicorn api_llm:app --host 0.0.0.0 --port 3001

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
El modelo de traduccion de audio a texto puede cometer errores y mandar textos incoherentes.
Por lo tanto, si detectas incoherencias en el texto no debes responder nada.
Cuando el usuario haga una pregunta, debes analizar el contexto y proporcionar una respuesta relevante y útil. Si no tienes suficiente información, pide aclaraciones.
Si el usuario pide que no hables(por ejemplo, "silencio"), no debes responder nada("").
La respuesta no debe exceder las 50 palabras.



## Probar whisper.cpp
curl 127.0.0.1:8080/inference \
    -H "Content-Type: multipart/form-data" \
    -F file="@<file-path>" \
    -F temperature="0.0" \
    -F temperature_inc="0.2" \
    -F response_format="json"

    
