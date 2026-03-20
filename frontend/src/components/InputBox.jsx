import { useState } from 'react'
import './InputBox.css'

export default function InputBox({
  onSendMessage,
  isConnected,
  isTyping,
  isRecording,
  voiceStage,
  isVoiceConnected,
  onStartRecording,
  onStopRecording,
}) {
  const [message, setMessage] = useState('')
  const voiceBusy = voiceStage !== 'idle' && voiceStage !== 'recording'

  const submit = (event) => {
    event.preventDefault()
    const clean = message.trim()
    if (!clean || !isConnected || isTyping || voiceBusy) return
    onSendMessage(clean)
    setMessage('')
  }

  const placeholder = voiceBusy
    ? `${voiceStage[0].toUpperCase()}${voiceStage.slice(1)} voice…`
    : isConnected ? 'Message SmartStay AI…' : 'Waiting for the local server…'

  return (
    <form className="input-container" onSubmit={submit}>
      <textarea
        className="message-input"
        value={message}
        maxLength={2000}
        rows={1}
        placeholder={placeholder}
        disabled={!isConnected || isTyping || isRecording || voiceBusy}
        onChange={(event) => setMessage(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) submit(event)
        }}
      />
      <div className="input-actions">
        <button
          className={`icon-button mic-button ${isRecording ? 'recording' : ''}`}
          type="button"
          title={isRecording ? 'Stop recording' : 'Speak to SmartStay AI'}
          aria-label={isRecording ? 'Stop recording' : 'Start voice recording'}
          disabled={!isVoiceConnected || isTyping || voiceBusy}
          onClick={isRecording ? onStopRecording : onStartRecording}
        >
          {isRecording ? '■' : '●'}
        </button>
        <button
          className="icon-button send-button"
          type="submit"
          title="Send message"
          disabled={!message.trim() || !isConnected || isTyping || voiceBusy}
        >
          ↑
        </button>
      </div>
    </form>
  )
}

