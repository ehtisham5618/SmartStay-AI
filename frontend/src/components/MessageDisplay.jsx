import { useEffect, useRef } from 'react'
import './MessageDisplay.css'

export default function MessageDisplay({ messages, isTyping }) {
  const messagesEndRef = useRef(null)
  const hasStreamingMessage = messages.some((message) => message.streaming)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  return (
    <div className="message-display">
      {messages.length === 0 ? (
        <div className="welcome-message">
          <h2>Welcome to SmartStay AI</h2>
          <p>Type a hotel question or press the microphone to speak.</p>
          <ul>
            <li>Room and reservation guidance</li>
            <li>Hotel amenities and services</li>
            <li>Check-in and check-out information</li>
          </ul>
        </div>
      ) : (
        <div className="messages-list">
          {messages.map((message) => (
            <div key={message.id} className={`message ${message.role}-message`}>
              <div className="message-avatar">{message.role === 'user' ? 'U' : 'S'}</div>
              <div className="message-content">
                <div className="message-text">
                  {message.content || (message.streaming ? 'Thinking' : '')}
                  {message.streaming && <span className="streaming-cursor" />}
                </div>
                <div className="message-timestamp">
                  {message.source === 'voice' ? 'Voice · ' : ''}{message.timestamp}
                </div>
                {(message.sources?.length > 0 || message.tools?.length > 0) && (
                  <div className="message-evidence">
                    {message.sources?.map((source) => (
                      <span key={source.source} title={`Similarity ${source.score}`}>
                        Source: {source.title || source.source}
                      </span>
                    ))}
                    {message.tools?.map((tool) => (
                      <span key={tool.name} className={tool.ok ? 'tool-ok' : 'tool-error'}>
                        Tool: {tool.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {isTyping && !hasStreamingMessage && (
            <div className="message assistant-message typing-indicator-message">
              <div className="message-avatar">S</div>
              <div className="message-content"><div className="typing-indicator"><span /><span /><span /></div></div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  )
}
