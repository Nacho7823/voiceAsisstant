'''
install torch with cuda
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install torchaudio --index-url https://download.pytorch.org/whl/cu121
'''


import uvicorn
import torch
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# --- Configuración ---
app = FastAPI()
VAD_PORT = 8001

# --- CORRECCIÓN 1 (Fatal) ---
# El modelo Silero VAD, con un sample rate de 16kHz, espera
# chunks de exactamente 512 muestras. El valor anterior (1536) era incorrecto.
VAD_CHUNK_SIZE = 512
VAD_SAMPLE_RATE = 16000 # El modelo Silero VAD espera 16kHz
# --- FIN DE LA CORRECCIÓN 1 ---

# --- Carga del Modelo VAD ---
try:
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=False
    )
    (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
    print("Modelo Silero VAD cargado exitosamente.")
except Exception as e:
    print(f"Error al cargar el modelo Silero VAD: {e}")
    print("Asegúrate de tener PyTorch instalado (`pip install torch`)")
    model = None
    VADIterator = None

# --- Configuración de CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "Servidor VAD en línea."}


@app.websocket("/ws/vad")
async def websocket_vad_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Cliente WebSocket conectado para VAD.")
    
    if model is None or VADIterator is None:
        await websocket.send_json({"error": "Modelo VAD no está cargado en el servidor."})
        await websocket.close()
        return

    vad_iterator = VADIterator(model, threshold=0.5, sampling_rate=VAD_SAMPLE_RATE)
    audio_buffer = torch.tensor([])

    try:
        while True:
            data = await websocket.receive_bytes()
            
            try:
                # --- CORRECCIÓN 2 (Warning) ---
                # Añadimos .copy() para crear un array de numpy escribible.
                # Esto soluciona la 'UserWarning' que vimos en el log.
                writable_audio_chunk = np.frombuffer(data, dtype=np.float32).copy()
                new_audio_chunk = torch.from_numpy(writable_audio_chunk)
                # --- FIN DE LA CORRECCIÓN 2 ---

            except Exception as e:
                print(f"Error al decodificar audio: {e}")
                continue 

            audio_buffer = torch.cat([audio_buffer, new_audio_chunk])

            # 6. Procesar el buffer en los tamaños de chunk que espera el VAD
            # Este bucle ahora procesará el buffer en chunks de 512
            while audio_buffer.shape[0] >= VAD_CHUNK_SIZE:
                chunk_to_process = audio_buffer[:VAD_CHUNK_SIZE]
                audio_buffer = audio_buffer[VAD_CHUNK_SIZE:]
                
                # 7. Ejecutar el VAD
                # Esta llamada ahora recibirá un chunk de 512, como espera
                speech_dict = vad_iterator(chunk_to_process, return_seconds=True)
                
                if speech_dict:
                    if "start" in speech_dict:
                        print(f"Evento VAD: speech_start (tiempo: {speech_dict['start']:.2f}s)")
                        await websocket.send_json({"event": "speech_start"})
                    elif "end" in speech_dict:
                        print(f"Evento VAD: speech_end (tiempo: {speech_dict['end']:.2f}s)")
                        await websocket.send_json({"event": "speech_end"})

    except WebSocketDisconnect:
        print("Cliente WebSocket desconectado.")
    except Exception as e:
        print(f"Error en la conexión WebSocket VAD: {e}")
    finally:
        if 'vad_iterator' in locals() and vad_iterator:
            vad_iterator.reset_states()
        print("Limpiando conexión VAD.")

if __name__ == "__main__":
    print(f"--- Iniciando Servidor de API VAD en puerto {VAD_PORT} ---")
    print(f"Endpoint WebSocket disponible en: ws://127.0.0.1:{VAD_PORT}/ws/vad")
    uvicorn.run(app, host="127.0.0.1", port=VAD_PORT)

#uvicorn api_vad:app --host 127.0.0.1 --port 8001