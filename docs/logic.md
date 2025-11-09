




const recorder
const buffer
const VAD
const ASR
const LLM
const TTS
const textQuery = ""

let speaking = false
let ttsSpeaking = false


recorder -> buffer -> VAD -> ASR -> textQuery -> LLM -> TTS 


VAD.onStartSpeech {
    buffer.startSpeech()
    speaking = true
    if (ttsSpeaking) {
        TTS.stop()
        ttsSpeaking = false
    }
}

VAD.onEndSpeech {
    waitPostRoll()  // esperar post-roll antes de finalizar el buffer
    if (speaking == true) {
        // se ha reactivado el habla durante el post-roll
        return
    }

    buffer = buffer.endSpeech()
    speaking = false

    async recognize(buffer)

}

async recognize(buffer) {
    transcript = await ASR.recognize(buffer)

    if (speaking) {
        textQuery += transcript
        // la proxima llamada mandara el texto completo a LLM
    }
    else {
        textQuery += transcript
        async sendToChat(textQuery)
        textQuery = ""
    }

}

async sendToChat(text) {
    addUserMessageToUI(text)
    response = await LLM.send(text)
    addAssistantMessageToUI(response)
    audio = await TTS.synthesize(response)

    TTS.play(audio)
    ttsSpeaking = true
}