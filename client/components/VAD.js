// javascript
// VAD.js
// Responsable de la conexión WebSocket al servicio VAD y de emitir eventos
// 'speech_start', 'speech_end', 'error'.
// API mínima:
//   const vad = new VAD(url);
//   vad.on('speech_start', cb);
//   await vad.connect();
//   vad.sendAudio(arrayBuffer); // opcional
//   vad.disconnect();


export default class VAD {
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.listeners = new Map(); // eventName -> [cb,...]
  }

  async connect() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) return;
    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      this._emit('open');
    };

    this.socket.onclose = () => {
      this._emit('close');
    };

    this.socket.onerror = (err) => {
      this._emit('error', err);
    };

    this.socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.event) {
          this._emit(msg.event, msg);
        } else if (msg.error) {
          this._emit('error', msg.error);
        } else {
          // mensajes no estructurados
          this._emit('message', msg);
        }
      } catch (e) {
        this._emit('error', e);
      }
    };

    // Espera hasta que esté abierto o falle (timeout implícito no provisto)
    await new Promise((resolve, reject) => {
      const onOpen = () => {
        cleanup();
        resolve();
      };
      const onError = (e) => {
        cleanup();
        reject(e);
      };
      const cleanup = () => {
        this.off('open', onOpen);
        this.off('error', onError);
      };
      this.on('open', onOpen);
      this.on('error', onError);
    });
  }

  disconnect() {
    if (this.socket) {
      try { this.socket.close(); } catch {}
      this.socket = null;
    }
  }

  sendAudio(arrayBuffer) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(arrayBuffer);
      } catch (e) {
        this._emit('error', e);
      }
    }
  }

  on(eventName, cb) {
    if (!this.listeners.has(eventName)) this.listeners.set(eventName, []);
    this.listeners.get(eventName).push(cb);
  }

  off(eventName, cb) {
    if (!this.listeners.has(eventName)) return;
    const arr = this.listeners.get(eventName).filter(f => f !== cb);
    this.listeners.set(eventName, arr);
  }

  _emit(eventName, payload) {
    const arr = this.listeners.get(eventName) || [];
    for (const cb of arr) {
      try { cb(payload); } catch (e) { console.error('VAD listener error', e); }
    }
  }
}
