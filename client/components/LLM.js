// javascript
// LLM.js
// Encapsula el envío de texto a un endpoint LLM genérico (compatible con esquema de chat).
// Uso:
//   const llm = new LLM();
//   const text = await llm.complete({ apiUrl, apiKey, modelName, prompt, text });

export default class LLM {
  constructor() {}

  /**
   * Envía texto a la API del LLM y devuelve la respuesta como string.
   * Intenta manejar la forma típica de "chat completions".
   * Ahora soporta un array de mensajes (para historial de chat).
   */
  async complete({ apiUrl, apiKey, modelName, systemPrompt = '', messages = [], text = '' } = {}) {
    if (!apiUrl || !apiKey || !modelName) {
      throw new Error('LLM: falta apiUrl, apiKey o modelName');
    }

    let chatMessages = [];
    if (Array.isArray(messages) && messages.length > 0) {
      chatMessages = messages.map(m => ({
        role: m.role || 'user',
        content: m.text || m.content || ''
      }));
    } else {
      let fullPrompt = text;
      if (prompt && prompt.trim()) {
        fullPrompt = `${prompt}\n\n"${text}"`;
      }
      chatMessages = [{ role: 'user', content: fullPrompt }];
    }

    // add system prompt if provided
    if (systemPrompt && systemPrompt.trim()) {
      chatMessages.unshift({ role: 'system', content: systemPrompt });
    }

    console.log('LLM.complete chatMessages:', chatMessages);

    const payload = {
      model: modelName,
      messages: chatMessages
    };

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    };

    try {
      const resp = await fetch(apiUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      });

      const data = await resp.json().catch(() => null);

      if (!resp.ok) {
        const msg = data?.error?.message || `HTTP ${resp.status}`;
        throw new Error(msg);
      }

      // Intentar formatos comunes:
      const chatContent = data?.choices?.[0]?.message?.content;
      if (typeof chatContent === 'string') return chatContent.trim();

      // Algunas APIs devuelven data.choices[0].text
      const altText = data?.choices?.[0]?.text;
      if (typeof altText === 'string') return altText.trim();

      // Otros endpoints pueden usar output_text u otros campos
      if (typeof data?.output_text === 'string') return data.output_text.trim();

      throw new Error('Respuesta inesperada del LLM');
    } catch (err) {
      console.error('LLM.complete error:', err);
      throw err;
    }
  }
}
