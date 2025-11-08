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

const SAMPLE_RATE = 16000;
const POST_ROLL_TIME = 1 * 1000; // ms

// --- Instancias de componentes ---
let recorder = null;
let vad = null;
let whisper = null;
let llm = null;
let tts = null;

let postRollTimer = null;

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
  const bubble = document.createElement('div');
  bubble.classList.add('chat-bubble', role);
  bubble.textContent = text;
  chatContainer.appendChild(bubble);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

// --- Flujo: enviar audio a Whisper y LLM ---
async function sendSpeechBufferToWhisperAndLLM() {
  try {
    const speechBuf = recorder.getSpeechBuffer();
    // No enviar si demasiado corto
    if (!speechBuf || speechBuf.length < (SAMPLE_RATE * 0.5)) {
      log('Audio demasiado corto, descartado.', 'idle');
      recorder.clearSpeechBuffer();
      return;
    }

    log('Traduciendo (Whisper)...', 'processing');
    const wavBlob = recorder.createWavBlob(speechBuf);
    recorder.clearSpeechBuffer();

    const transcription = await whisper.transcribe(wavBlob, {
      modelSize: modelSelect.value,
      language: languageSelect.value
    });

    if (transcription && transcription.trim()) {
      const trimmed = transcription.trim();
      addMessageToChat('user', trimmed);

      // Enviar a LLM
      try {
        log('Enviando a LLM...', 'processing');
        const response = await llm.complete({
          apiUrl: llmApiUrl.value.trim(),
          apiKey: llmApiKey.value.trim(),
          modelName: llmModelName.value.trim(),
          prompt: llmPrompt.value.trim(),
          text: trimmed
        });

        if (response && response.trim()) {
          const finalText = response.trim();
          addMessageToChat('assistant', finalText);

          if (ttsToggle.checked) {
            // Determinar idioma para TTS
            let targetLang = 'en-US';
            const sel = languageSelect.value;
            if (sel && sel.length > 0 && sel !== 'en') {
              targetLang = sel;
            } else if (sel === 'en') {
              targetLang = 'en-US';
            }
            // speak (fire-and-forget; TTSEngine gestiona eventos)
            try {
              await tts.speak(finalText, { lang: targetLang });
              // onend del TTS volverá a 'Escuchando...'
            } catch (err) {
              console.error('TTS speak error', err);
              log('Escuchando...', 'idle');
            }
          } else {
            log('Escuchando...', 'idle');
          }
        } else {
          log('Escuchando...', 'idle');
        }
      } catch (err) {
        console.error('Error LLM', err);
        log(`Error de LLM: ${err.message}`, 'error');
        addMessageToChat('error', `Error de LLM: ${err.message}`);
      }

    } else {
      log('Escuchando...', 'idle');
    }
  } catch (err) {
    console.error('Error al procesar audio:', err);
    log(`Error de Whisper: ${err.message || err}`, 'error');
    addMessageToChat('error', `Error de Whisper: ${err.message || err}`);
  }
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

    // Eventos VAD
    vad.on('speech_start', () => {
      // Cancelar TTS si interrumpe
      if (tts && tts.isPlaying && tts.isPlaying()) {
        tts.stop();
      }

      log('Hablando...', 'speaking');

      // Cancelar post-roll si existía
      if (postRollTimer) {
        clearTimeout(postRollTimer);
        postRollTimer = null;
      }

      // Indicar al recorder que arranque
      recorder.markSpeechStart();
    });

    vad.on('speech_end', () => {
      log('Fin de voz detectado...', 'processing');
      // Indicar fin de grabación y arrancar post-roll
      recorder.markSpeechEnd();
      if (postRollTimer) clearTimeout(postRollTimer);
      postRollTimer = setTimeout(async () => {
        postRollTimer = null;
        await sendSpeechBufferToWhisperAndLLM();
      }, POST_ROLL_TIME);
    });

    vad.on('error', (e) => {
      console.error('VAD error', e);
      log('Error de VAD', 'error');
    });

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
clearBtn.addEventListener('click', () => { chatContainer.innerHTML = ''; });

// Inicializar estado UI
log('Haz clic en "Iniciar" para comenzar', 'idle');
stopBtn.disabled = true;
