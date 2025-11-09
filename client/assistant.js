// javascript
// assistant.js
// Orquestador que conecta UI con Recorder, VAD, Whisper, LLM y TTSEngine.

import Recorder from './components/Recorder.js';
import VAD from './components/VAD.js';
import Whisper from './components/Whisper.js';
import LLM from './components/LLM.js';
import TTSEngine from './components/TTSEngine.js';

// --- Referencias al DOM ---
const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const statusLog = document.getElementById('status-log');
const vadLight = document.getElementById('vad-light');
const modelSelect = document.getElementById('model-select');
const languageSelect = document.getElementById('language-select');
// Referencias de LLM
const llmApiUrl = document.getElementById('llm-api-url');
const llmPrompt = document.getElementById('llm-prompt');
const llmApiKey = document.getElementById('llm-api-key');
const llmModelName = document.getElementById('llm-model-name');

const chatContainer = document.getElementById('chat-container');
const clearBtn = document.getElementById('clear-btn');
const ttsToggle = document.getElementById('tts-toggle');

// --- Configuración de endpoints y tiempos ---
const VAD_API_URL = "ws://127.0.0.1:8001/ws/vad";
const WHISPER_API_URL = "http://127.0.0.1:8000/translate";
const LLM_API_URL = "http://localhost:3002/v1/chat/completions";
const LLM_MODEL_NAME = "openai/gpt-4.1"
const LLM_API_KEY = ""; // Poner aquí la API Key por defecto si se desea

const SAMPLE_RATE = 16000;
const POST_ROLL_TIME = 2 * 1000; // ms

// --- Instancias de componentes ---
let recorder = null;
let vad = null;
let whisper = null;
let llm = null;
let tts = null;

let postRollTimer = null;

let chatHistory = [];
//add system message
// chatHistory.push({ role: 'system', text: 'Eres un asistente útil y amable que responde de manera concisa.' });

// --- Utilidades UI ---
function log(message, state = 'idle') {
  statusLog.textContent = message;
  if (state === 'speaking') {
    vadLight.classList.add('speaking');
  } else {
    vadLight.classList.remove('speaking');
  }
  statusLog.style.color = state === 'error' ? '#c0392b' : '#34495e';
}

function addMessageToChat(role, text) {
  // Solo agregar mensajes válidos y evitar duplicados consecutivos
  if (
    chatHistory.length === 0 ||
    chatHistory[chatHistory.length - 1].role !== role ||
    chatHistory[chatHistory.length - 1].text !== text
  ) {
    chatHistory.push({ role, text });
  }
  const bubble = document.createElement('div');
  bubble.classList.add('chat-bubble', role);
  bubble.textContent = text;
  chatContainer.appendChild(bubble);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

let speaking = false;
let ttsSpeaking = false;
let textQuery = "";

// --- Lógica principal basada en logic.md ---
function setupVADLogic() {
  vad.on('speech_start', () => {
    statusLog.textContent = 'Detectado habla...';
    vadLight.classList.add('speaking');
    recorder.markSpeechStart();
    speaking = true;
    if (ttsSpeaking) {
      tts.stop();
      ttsSpeaking = false;
    }
  });

  vad.on('speech_end', async () => {
    vadLight.classList.remove('speaking');
    statusLog.textContent = 'Detectado fin de habla...';
    speaking = false;
    // Esperar post-roll antes de procesar
    await new Promise(resolve => setTimeout(resolve, POST_ROLL_TIME));
    if(speaking) {
      // Se ha reactivado el habla durante el post-roll
      return;
    }
    statusLog.textContent = 'Procesando...';

    recorder.markSpeechEnd();
    const buffer = recorder.getSpeechBuffer();

    // Reconocimiento ASR
    let wavBlob = recorder.createWavBlob(buffer);
    let transcript = await whisper.transcribe(wavBlob);

    if (speaking) {
      textQuery += transcript;
      console.log('Habla reanudada, acumulando texto:', textQuery);
      // La próxima llamada mandará el texto completo a LLM
    } else {
      textQuery += transcript;
      // Enviar a LLM y TTS
      try {
        addMessageToChat('user', textQuery);
        const textToSend = chatHistory.length > 0 ? chatHistory : [{ role: 'user', text: textQuery }];
        textQuery = ""; // resetear consulta

        log('Generando respuesta...', 'processing');
        console.log('Enviando a LLM:', textToSend);

        const systemPrompt = llmPrompt.value.trim();

        const response = await llm.complete({
          apiUrl: llmApiUrl.value || LLM_API_URL,
          apiKey: llmApiKey.value || LLM_API_KEY,
          modelName: llmModelName.value || LLM_MODEL_NAME,
          systemPrompt: systemPrompt,
          messages: textToSend
        });
        addMessageToChat('system', response);

        statusLog.textContent = 'Esperando habla...';

        await tts.speak(response);
        ttsSpeaking = true;
      } catch (err) {
        console.error('Error en LLM o TTS', err);
      }
    }
  });
}

// --- Start / Stop ---
async function startDetection() {
  try {
    log('Iniciando...', 'processing');
    startBtn.disabled = true;
    stopBtn.disabled = false;
    modelSelect.disabled = true;
    languageSelect.disabled = true;
    llmApiUrl.disabled = true;
    llmPrompt.disabled = true;
    llmApiKey.disabled = true;
    llmModelName.disabled = true;
    ttsToggle.disabled = true;

    // Crear instancias
    recorder = new Recorder({ sampleRate: SAMPLE_RATE, preRollTime: 2 });
    vad = new VAD(VAD_API_URL);
    whisper = new Whisper({ url: WHISPER_API_URL });
    llm = new LLM();
    tts = new TTSEngine();

    // Conectar VAD
    await vad.connect();
    log('VAD conectado. Solicitando micrófono...', 'processing');

    // Inicializar Recorder y empezar a recibir audio
    recorder.onAudio((float32arr) => {
      // Enviar audio bruto al VAD (VAD siempre activo)
      vad.sendAudio(float32arr.buffer);
    });

    await recorder.start();
    log('Micrófono activo. Escuchando...', 'idle');

    setupVADLogic();

    // TTSEngine events (solo para UI)
    tts.on('start', () => {
      log('Asistente hablando...', 'idle');
      vadLight.classList.remove('speaking');
    });
    tts.on('end', () => {
      // Volver a escucha si seguimos activos
      if (!stopBtn.disabled) {
        log('Escuchando...', 'idle');
      }
    });
    tts.on('error', () => {
      if (!stopBtn.disabled) log('Escuchando...', 'idle');
    });

  } catch (err) {
    console.error('Error al iniciar:', err);
    log(`Error al iniciar: ${err.message || err}`, 'error');
    stopDetection();
  }
}

async function stopDetection() {
  // Detener TTS
  if (tts) {
    try { tts.stop(); } catch {}
  }

  if (postRollTimer) {
    clearTimeout(postRollTimer);
    postRollTimer = null;
  }

  if (vad) {
    try { vad.disconnect(); } catch {}
    vad = null;
  }
  if (recorder) {
    try { await recorder.stop(); } catch {}
    recorder = null;
  }

  whisper = null;
  llm = null;
  tts = null;

  log('Haz clic en "Iniciar" para comenzar', 'idle');
  startBtn.disabled = false;
  stopBtn.disabled = true;
  modelSelect.disabled = false;
  languageSelect.disabled = false;
  llmApiUrl.disabled = false;
  llmPrompt.disabled = false;
  llmApiKey.disabled = false;
  llmModelName.disabled = false;
  ttsToggle.disabled = false;
}

// --- Event listeners UI ---
startBtn.addEventListener('click', startDetection);
stopBtn.addEventListener('click', stopDetection);
clearBtn.addEventListener('click', () => {
  chatContainer.innerHTML = '';
  chatHistory = [];
});

// Inicializar estado UI
log('Haz clic en "Iniciar" para comenzar', 'idle');
stopBtn.disabled = true;
