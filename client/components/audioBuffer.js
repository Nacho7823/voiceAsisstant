/**
 * audioBuffer.js
 * Buffer de audio simple para almacenar y gestionar fragmentos de audio.
 */

export default class AudioBufferManager {
  constructor() {
    this.buffer = [];
    this.speechActive = false;
  }

  push(chunk) {
    if (this.speechActive) {
      this.buffer.push(chunk);
    }
  }

  startSpeech() {
    this.speechActive = true;
    this.buffer = [];
  }

  endSpeech() {
    this.speechActive = false;
    const result = this.getBuffer();
    this.clear();
    return result;
  }

  getBuffer() {
    // Devuelve un solo Float32Array concatenado
    if (this.buffer.length === 0) return new Float32Array(0);
    const totalLength = this.buffer.reduce((acc, arr) => acc + arr.length, 0);
    const out = new Float32Array(totalLength);
    let offset = 0;
    for (const arr of this.buffer) {
      out.set(arr, offset);
      offset += arr.length;
    }
    return out;
  }

  clear() {
    this.buffer = [];
  }
}
