class AudioPlaybackQueue {
  constructor() {
    this.chain = Promise.resolve()
    this.currentAudio = null
    this.generation = 0
  }

  enqueue(base64Audio, mimeType = 'audio/wav') {
    const generation = this.generation
    const binary = atob(base64Audio)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
    const url = URL.createObjectURL(new Blob([bytes], { type: mimeType }))

    this.chain = this.chain
      .catch(() => undefined)
      .then(() => {
        if (generation !== this.generation) {
          URL.revokeObjectURL(url)
          return
        }
        return new Promise((resolve) => {
          const audio = new Audio(url)
          this.currentAudio = audio
          const finish = () => {
            URL.revokeObjectURL(url)
            if (this.currentAudio === audio) this.currentAudio = null
            resolve()
          }
          audio.onended = finish
          audio.onerror = finish
          audio.play().catch(finish)
        })
      })
  }

  clear() {
    this.generation += 1
    if (this.currentAudio) {
      this.currentAudio.pause()
      this.currentAudio = null
    }
    this.chain = Promise.resolve()
  }
}

class VoiceService {
  constructor() {
    this.socket = null
    this.eventCallback = null
    this.connectionCallback = null
    this.player = new AudioPlaybackQueue()
  }

  connect(url) {
    this.disconnect()
    this.socket = new WebSocket(url)
    this.socket.binaryType = 'arraybuffer'
    this.socket.onopen = () => this.connectionCallback?.(true)
    this.socket.onclose = () => this.connectionCallback?.(false)
    this.socket.onerror = () => this.eventCallback?.({ type: 'error', message: 'Voice connection failed' })
    this.socket.onmessage = (message) => {
      const event = JSON.parse(message.data)
      if (event.type === 'audio') this.player.enqueue(event.content, event.mime_type)
      this.eventCallback?.(event)
    }
  }

  begin(sessionId, userId, mimeType) {
    return this.sendJson({ type: 'audio_start', session_id: sessionId, user_id: userId, mime_type: mimeType })
  }

  sendRecording(arrayBuffer) {
    if (this.socket?.readyState !== WebSocket.OPEN) return false
    this.socket.send(arrayBuffer)
    return this.sendJson({ type: 'audio_end' })
  }

  sendJson(payload) {
    if (this.socket?.readyState !== WebSocket.OPEN) return false
    this.socket.send(JSON.stringify(payload))
    return true
  }

  onEvent(callback) {
    this.eventCallback = callback
  }

  onConnection(callback) {
    this.connectionCallback = callback
  }

  clearPlayback() {
    this.player.clear()
  }

  disconnect() {
    this.player.clear()
    if (this.socket) {
      this.socket.onclose = null
      this.socket.close(1000, 'Client disconnecting')
      this.socket = null
    }
    this.connectionCallback?.(false)
  }
}

export default new VoiceService()
