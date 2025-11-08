// javascript
// TTSEngine.js
// Encapsula la Web Speech API para TTS.
// API:
//   const tts = new TTSEngine();
//   tts.on('start', cb); tts.on('end', cb); tts.on('error', cb);
//   await tts.speak(text, { lang });
//   tts.stop();
//   tts.isPlaying();

export default class TTSEngine {
  constructor() {
    this._isPlaying = false;
    this._listeners = new Map(); // event -> [cb,...]
    this._utterance = null;

    if ('speechSynthesis' in window) {
      // for browsers que cargan voces asíncronas
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
      };
    }
  }

  on(eventName, cb) {
    if (!this._listeners.has(eventName)) this._listeners.set(eventName, []);
    this._listeners.get(eventName).push(cb);
  }

  off(eventName, cb) {
    if (!this._listeners.has(eventName)) return;
    const arr = this._listeners.get(eventName).filter(f => f !== cb);
    this._listeners.set(eventName, arr);
  }

  _emit(eventName, payload) {
    const arr = this._listeners.get(eventName) || [];
    for (const cb of arr) {
      try { cb(payload); } catch (e) { console.error('TTSEngine listener error', e); }
    }
  }

  isPlaying() {
    return this._isPlaying;
  }

  stop() {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    this._isPlaying = false;
    this._utterance = null;
    this._emit('end');
  }

  /**
   * Reproduce texto por TTS. Opcionalmente se puede pasar lang (ej: 'es-ES').
   * Devuelve una promesa que resuelve cuando empieza la reproducción.
   */
  speak(text, { lang = null } = {}) {
    return new Promise((resolve, reject) => {
      if (!('speechSynthesis' in window)) {
        const err = new Error('TTS no soportado en este navegador');
        this._emit('error', err);
        return reject(err);
      }

      try {
        // cancelar cualquier reproducción previa
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        this._utterance = utterance;

        // asignar idioma si se proporcionó
        if (lang) {
          utterance.lang = lang;
        }

        // intentar seleccionar voz adecuada
        const voices = window.speechSynthesis.getVoices() || [];
        let chosen = null;
        if (lang) {
          chosen = voices.find(v => v.lang && v.lang.toLowerCase().startsWith(lang.toLowerCase()));
          if (!chosen) {
            const base = lang.split('-')[0];
            chosen = voices.find(v => v.lang && v.lang.toLowerCase().startsWith(base));
          }
        }
        if (chosen) utterance.voice = chosen;

        utterance.pitch = 1;
        utterance.rate = 1;

        utterance.onstart = () => {
          this._isPlaying = true;
          this._emit('start');
          resolve();
        };

        utterance.onend = () => {
          this._isPlaying = false;
          this._utterance = null;
          this._emit('end');
        };

        utterance.onerror = (ev) => {
          this._isPlaying = false;
          this._utterance = null;
          const err = ev?.error || new Error('TTS error');
          this._emit('error', err);
          reject(err);
        };

        window.speechSynthesis.speak(utterance);
      } catch (err) {
        this._isPlaying = false;
        this._utterance = null;
        this._emit('error', err);
        reject(err);
      }
    });
  }
}
