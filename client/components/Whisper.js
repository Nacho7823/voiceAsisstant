// javascript
// Whisper.js
// Encapsula la llamada al endpoint de Whisper que recibe un audio WAV y devuelve texto.
// Uso:
//   const whisper = new Whisper({ url: 'http://127.0.0.1:8000/translate' });
//   const text = await whisper.transcribe(wavBlob, { modelSize: 'base', language: 'es' });

export default class Whisper {
  constructor({ url }) {
    if (!url) throw new Error('Whisper: se requiere URL');
    this.url = url;
  }

  /**
   * Transcribe/translate un WAV Blob usando el servicio Whisper.
   * @param {Blob} wavBlob
   * @param {Object} opts
   * @param {string} opts.modelSize
   * @param {string} opts.language
   * @returns {Promise<string>} texto transcrito/resultado
   */
  async transcribe(wavBlob, { modelSize = 'base', language = '' } = {}) {
    const formData = new FormData();
    formData.append('audio_file', wavBlob, 'segment.wav');
    formData.append('model_size', modelSize);
    formData.append('language', language);

    try {
      const resp = await fetch(this.url, {
        method: 'POST',
        body: formData
      });

      if (!resp.ok) {
        const txt = await resp.text().catch(() => null);
        throw new Error(`Whisper HTTP ${resp.status} ${resp.statusText} ${txt ? `: ${txt}` : ''}`);
      }

      const data = await resp.json().catch(() => null);
      const resultText = data?.result_text ?? null;
      if (typeof resultText === 'string') return resultText.trim();
      throw new Error('Respuesta de Whisper sin campo "result_text"');
    } catch (err) {
      console.error('Whisper transcribe error:', err);
      throw err;
    }
  }
}
