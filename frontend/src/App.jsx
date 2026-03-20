import { useEffect, useRef, useState } from 'react'
import ChatInterface from './components/ChatInterface'
import websocketService from './utils/websocketService'
import voiceService from './utils/voiceService'
import './App.css'

const newSessionId = () => crypto.randomUUID()
const stamp = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const persistentUserId = () => {
  const existing = localStorage.getItem('smartstay_user_id')
  if (existing) return existing
  const created = crypto.randomUUID()
  localStorage.setItem('smartstay_user_id', created)
  return created
}

function App() {
  const [sessionId, setSessionId] = useState(newSessionId)
  const [messages, setMessages] = useState([])
  const [isConnected, setConnected] = useState(false)
  const [isVoiceConnected, setVoiceConnected] = useState(false)
  const [isTyping, setTyping] = useState(false)
  const [isRecording, setRecording] = useState(false)
  const [voiceStage, setVoiceStage] = useState('idle')
  const [error, setError] = useState('')
  const streamingId = useRef(null)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const recordedChunksRef = useRef([])
  const userId = useRef(persistentUserId())

  const updateAssistantToken = (token) => {
    setMessages((current) => current.map((message) =>
      message.id === streamingId.current
        ? { ...message, content: message.content + token, streaming: true }
        : message
    ))
  }

  const finishStreaming = () => {
    setMessages((current) => current.map((message) =>
      message.id === streamingId.current ? { ...message, streaming: false } : message
    ))
    streamingId.current = null
    setTyping(false)
  }

  const applyContext = (context) => {
    setMessages((current) => current.map((message) =>
      message.id === streamingId.current
        ? { ...message, sources: context.sources || [], tools: context.tools || [] }
        : message
    ))
  }

  const connect = () => {
    setError('')
    websocketService.connect(import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/chat')
    voiceService.connect(import.meta.env.VITE_VOICE_WS_URL || 'ws://localhost:8000/ws/voice')
  }

  useEffect(() => {
    websocketService.onConnect(() => setConnected(true))
    websocketService.onDisconnect(() => setConnected(false))
    websocketService.onError((message) => {
      setError(message)
      setTyping(false)
    })
    websocketService.onStreamToken(updateAssistantToken)
    websocketService.onMessage(({ type, data }) => {
      if (type === 'end') finishStreaming()
      else if (data?.type === 'context') applyContext(data)
    })

    voiceService.onConnection(setVoiceConnected)
    voiceService.onEvent((event) => {
      if (event.type === 'transcript') {
        const assistantId = crypto.randomUUID()
        streamingId.current = assistantId
        setMessages((current) => [
          ...current,
          { id: crypto.randomUUID(), role: 'user', source: 'voice', content: event.content, timestamp: stamp() },
          { id: assistantId, role: 'assistant', source: 'voice', content: '', timestamp: stamp(), streaming: true },
        ])
        setTyping(true)
      } else if (event.type === 'token') {
        updateAssistantToken(event.content)
      } else if (event.type === 'context') {
        applyContext(event)
      } else if (event.type === 'status') {
        setVoiceStage(event.stage)
      } else if (event.type === 'done') {
        finishStreaming()
        setVoiceStage('idle')
      } else if (event.type === 'audio_error') {
        setError(`Text response completed, but speech playback failed: ${event.message}`)
      } else if (event.type === 'error') {
        setError(event.message)
        setVoiceStage('idle')
        setTyping(false)
      }
    })

    connect()
    return () => {
      websocketService.disconnect()
      voiceService.disconnect()
      streamRef.current?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  const sendMessage = (content) => {
    const assistantId = crypto.randomUUID()
    if (!websocketService.send({ session_id: sessionId, user_id: userId.current, message: content })) {
      setError('Not connected to the SmartStay API.')
      return
    }
    streamingId.current = assistantId
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', source: 'text', content, timestamp: stamp() },
      { id: assistantId, role: 'assistant', source: 'text', content: '', timestamp: stamp(), streaming: true },
    ])
    setTyping(true)
  }

  const startRecording = async () => {
    if (!isVoiceConnected || isTyping || voiceStage !== 'idle') return
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = mediaStream
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      const recorder = new MediaRecorder(mediaStream, { mimeType })
      recorderRef.current = recorder
      recordedChunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size) recordedChunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        const blob = new Blob(recordedChunksRef.current, { type: mimeType })
        recordedChunksRef.current = []
        streamRef.current?.getTracks().forEach((track) => track.stop())
        streamRef.current = null
        setRecording(false)
        setVoiceStage('uploading')
        voiceService.sendRecording(await blob.arrayBuffer())
      }
      if (!voiceService.begin(sessionId, userId.current, mimeType)) throw new Error('Voice socket is unavailable')
      recorder.start()
      setRecording(true)
      setVoiceStage('recording')
    } catch (recordingError) {
      setError(recordingError.message || 'Microphone permission was denied')
      setRecording(false)
      setVoiceStage('idle')
    }
  }

  const stopRecording = () => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }

  const reset = () => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    voiceService.clearPlayback()
    setSessionId(newSessionId())
    setMessages([])
    setTyping(false)
    setVoiceStage('idle')
    streamingId.current = null
  }

  return (
    <div className="app">
      <header className="app-header">
        <button className="new-session-button" onClick={reset}>New chat</button>
        <h1 className="app-title">SmartStay AI</h1>
        <div className="connection-status">
          <span className={`status-indicator ${isConnected && isVoiceConnected ? 'connected' : 'disconnected'}`} />
          {isConnected && isVoiceConnected ? 'Chat + voice' : 'Connecting'}
        </div>
      </header>
      <ChatInterface
        messages={messages}
        onSendMessage={sendMessage}
        onReconnect={connect}
        isConnected={isConnected}
        isTyping={isTyping}
        connectionError={error}
        isRecording={isRecording}
        voiceStage={voiceStage}
        isVoiceConnected={isVoiceConnected}
        onStartRecording={startRecording}
        onStopRecording={stopRecording}
      />
    </div>
  )
}

export default App
