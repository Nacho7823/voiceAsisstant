// javascript
// Recorder.js
// Responsable de: AudioContext, AudioWorklet, pre-roll/speech buffers y creación de WAV blobs.
// Exporta la clase Recorder con una API mínima para integrarse con VAD / orquestador.


import AudioBufferManager from './audioBuffer.js';

export default class Recorder {
  constructor({ sampleRate = 16000, preRollTime = 2, constraints = {} } = {}) {
    this.sampleRate = sampleRate;
    this.preRollSamples = sampleRate * preRollTime;

    // Forzar AEC nativo del navegador como valor por defecto,
    // pero permitir que el llamador sobreescriba otras constraints.
    this.constraints = Object.assign({
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true
    }, constraints);

    this.audioContext = null;
    this.workletNode = null;
    this.mediaStream = null;
    this.mediaStreamSource = null;

    this.preRollBuffer = new Float32Array(0);
    this.audioBufferManager = new AudioBufferManager();

    this.isRecording = false; // controlado externamente vía markSpeechStart/End
    this.onAudioCallback = null;
  }

  async init() {
    if (this.audioContext) return;
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: this.sampleRate
    });
    await this.audioContext.resume();

    // Crear worklet desde Blob (igual que en el original)
    const workletBlob = new Blob([`
      class VADAudioProcessor extends AudioWorkletProcessor {
        process(inputs) {
          const inputChannel = inputs[0] && inputs[0][0];
          if (inputChannel) {
            this.port.postMessage(inputChannel.slice());
          }
          return true;
        }
      }
      registerProcessor('vad-audio-processor', VADAudioProcessor);
    `], { type: 'application/javascript' });

    const workletURL = URL.createObjectURL(workletBlob);
    await this.audioContext.audioWorklet.addModule(workletURL);
    URL.revokeObjectURL(workletURL);

    this.workletNode = new AudioWorkletNode(this.audioContext, 'vad-audio-processor');
    this.workletNode.port.onmessage = (e) => {
      // e.data es Float32Array
      this._handleAudioData(e.data);
      if (typeof this.onAudioCallback === 'function') {
        // Enviar copia para que otros módulos (p.e. VAD WS) la usen
        try {
          this.onAudioCallback(e.data);
        } catch (err) { console.error('onAudioCallback error', err); }
      }
    };
  }

  async start() {
    await this.init();
    if (this.mediaStream) return;

    // Usar las constraints configuradas en el constructor (forzamos AEC por defecto)
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: this.constraints
    });

    // Condición de carrera check
    if (!this.audioContext) throw new Error('AudioContext cerrado inesperadamente.');

    this.mediaStreamSource = this.audioContext.createMediaStreamSource(this.mediaStream);
    this.mediaStreamSource.connect(this.workletNode);

    // Conectar a ganancia 0 para mantener grafo sin feedback
    const silentGain = this.audioContext.createGain();
    silentGain.gain.value = 0;
    this.workletNode.connect(silentGain);
    silentGain.connect(this.audioContext.destination);
  }

  // Detiene y libera recursos
  async stop() {
    if (this.workletNode) {
      this.workletNode.port.onmessage = null;
      try { this.workletNode.disconnect(); } catch {}
      this.workletNode = null;
    }
    if (this.mediaStreamSource) {
      try {
        this.mediaStream.getTracks().forEach(t => t.stop());
      } catch {}
      try { this.mediaStreamSource.disconnect(); } catch {}
      this.mediaStreamSource = null;
      this.mediaStream = null;
    }
    if (this.audioContext) {
      try { await this.audioContext.close(); } catch {}
      this.audioContext = null;
    }
    // reset buffers
    this.preRollBuffer = new Float32Array(0);
    this.speechBuffer = new Float32Array(0);
    this.isRecording = false;
  }

  onAudio(cb) { this.onAudioCallback = cb; }

  // Llamar cuando VAD notifique speech_start
  markSpeechStart() {
    if (this.isRecording) return;
    this.isRecording = true;
    this.audioBufferManager.startSpeech();
  }

  // Llamar cuando VAD notifique speech_end
  markSpeechEnd() {
    this.isRecording = false;
  }

  getSpeechBuffer() {
    return this.audioBufferManager.getBuffer();
  }

  clearSpeechBuffer() {
    this.audioBufferManager.clear();
  }

  // Interno: gestionar pre-roll / speech append
  _handleAudioData(audioData) {
    if (this.isRecording) {
      this.audioBufferManager.push(audioData);
    } else {
      const newBuf = new Float32Array(this.preRollBuffer.length + audioData.length);
      newBuf.set(this.preRollBuffer);
      newBuf.set(audioData, this.preRollBuffer.length);
      if (newBuf.length > this.preRollSamples) {
        this.preRollBuffer = newBuf.slice(newBuf.length - this.preRollSamples);
      } else {
        this.preRollBuffer = newBuf;
      }
    }
  }

  // Utilidad: crear WAV a partir de Float32Array
  createWavBlob(float32Array) {
    const sampleRate = this.sampleRate;
    const audioData = float32Array;
    const buffer = new ArrayBuffer(44 + audioData.length * 2);
    const view = new DataView(buffer);

    function writeString(viewInner, offset, string) {
      for (let i = 0; i < string.length; i++) {
        viewInner.setUint8(offset + i, string.charCodeAt(i));
      }
    }

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + audioData.length * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // byte rate
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, audioData.length * 2, true);

    let offset = 44;
    for (let i = 0; i < audioData.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, audioData[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }

    return new Blob([view], { type: 'audio/wav' });
  }
}
