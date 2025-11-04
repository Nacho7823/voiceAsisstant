const uploadForm = document.getElementById('upload-form');
const submitButton = document.getElementById('submit-button');
const statusDiv = document.getElementById('status');
const resultText = document.getElementById('result-text');
const recordButton = document.getElementById('record-button');
const stopButton = document.getElementById('stop-button');
const playButton = document.getElementById('play-button');
const recordTimer = document.getElementById('record-timer');
const modelSelect = document.getElementById('model-select');
const modelInfoDiv = document.getElementById('model-info');
const languageSelect = document.getElementById('language-select');

// Variables para la grabación
let mediaRecorder = null;
let recordedChunks = [];
let recordedBlob = null;
let recordInterval = null;
let recordStartTime = null;

// Información aproximada de tamaño/peso por modelo (valores aproximados)
// Nota: números aproximados, utilízalos solo como referencia.
const MODEL_SIZES = {
    'tiny': { size: '≈ 35 MB', ram: '≈ 100 MB' },
    'base': { size: '≈ 70 MB', ram: '≈ 200 MB' },
    'small': { size: '≈ 240 MB', ram: '≈ 500 MB' },
    'medium': { size: '≈ 760 MB', ram: '≈ 1.5 GB' },
    'large-v3': { size: '≈ 1.6 GB', ram: '≈ 4+ GB' }
};

function updateModelInfo() {
    const model = modelSelect.value;
    const info = MODEL_SIZES[model];
    if (info) {
        modelInfoDiv.textContent = `Tamaño en disco (aprox.): ${info.size} · RAM requerida (aprox.): ${info.ram}`;
    } else {
        modelInfoDiv.textContent = 'Tamaño aproximado: —';
    }
}

// Inicializar info al cargar
updateModelInfo();
modelSelect.addEventListener('change', updateModelInfo);

function formatTimer(ms) {
    const s = Math.floor(ms / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `${mm}:${ss}`;
}

async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('La grabación no está soportada en este navegador.');
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recordedChunks = [];
        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.addEventListener('dataavailable', (e) => {
            if (e.data && e.data.size > 0) recordedChunks.push(e.data);
        });

        mediaRecorder.addEventListener('stop', () => {
            recordedBlob = new Blob(recordedChunks, { type: recordedChunks[0]?.type || 'audio/webm' });
            playButton.disabled = false;
            stopButton.disabled = true;
            recordButton.disabled = false;
            clearInterval(recordInterval);
            recordInterval = null;
        });

        mediaRecorder.start();
        recordStartTime = Date.now();
        recordTimer.textContent = '00:00';
        recordInterval = setInterval(() => {
            recordTimer.textContent = formatTimer(Date.now() - recordStartTime);
        }, 250);

        recordButton.disabled = true;
        stopButton.disabled = false;
        playButton.disabled = true;
    } catch (err) {
        console.error('Error al acceder al micrófono:', err);
        alert('No se pudo acceder al micrófono. Revisa permisos.');
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
}

function playRecording() {
    if (!recordedBlob) return;
    const url = URL.createObjectURL(recordedBlob);
    const audio = new Audio(url);
    audio.play();
}

recordButton.addEventListener('click', startRecording);
stopButton.addEventListener('click', stopRecording);
playButton.addEventListener('click', playRecording);

uploadForm.addEventListener('submit', async (event) => {
    // Prevenir que el formulario recargue la página
    event.preventDefault(); 

        // 1. Obtener los datos del formulario
        // FormData se encarga de empaquetar los archivos
        const formData = new FormData(uploadForm);

        // Añadir idioma seleccionado (si aplica)
        const selectedLang = languageSelect?.value;
        if (selectedLang) {
            formData.set('language', selectedLang);
        }

        // Si hay una grabación en memoria, usarla en lugar del input file
        if (recordedBlob) {
            // Crear un filename razonable; el servidor debe manejar audio/webm
            formData.set('audio_file', recordedBlob, 'recording.webm');
        }
    
    // 2. Deshabilitar botón y mostrar estado de carga
    submitButton.disabled = true;
    statusDiv.textContent = 'Traduciendo... (El primer modelo puede tardar en cargar)';
    resultText.textContent = '';

    try {
        // 3. Enviar la petición a la API de FastAPI
        const response = await fetch('http://127.0.0.1:8000/translate', {
            method: 'POST',
            body: formData,
            // NOTA: No se pone 'Content-Type'. 
            // El navegador lo pone solo (multipart/form-data)
            // y añade el 'boundary' necesario.
        });

        // 4. Analizar la respuesta
        const data = await response.json();

        if (response.ok) {
            // Éxito
            statusDiv.textContent = `Traducción completada (Idioma detectado: ${data.detected_language})`;
            console.log('Respuesta de la API:', data);
            resultText.textContent = data.result_text;
        } else {
            // Error de la API (ej: 500)
            statusDiv.textContent = 'Error de la API:';
            resultText.textContent = data.detail || 'Ocurrió un error desconocido';
        }

    } catch (error) {
        // Error de red (ej: la API no está corriendo)
        console.error('Error de conexión:', error);
        statusDiv.textContent = 'Error de conexión:';
        resultText.textContent = 'No se pudo conectar a la API en http://127.0.0.1:8000. \n¿Revisaste que el script de Python esté corriendo y que tenga CORS habilitado?';
    } finally {
        // 5. Reactivar el botón
        submitButton.disabled = false;
    }
});
