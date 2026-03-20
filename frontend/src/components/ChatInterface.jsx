import MessageDisplay from './MessageDisplay'
import InputBox from './InputBox'
import './ChatInterface.css'

export default function ChatInterface(props) {
  return (
    <main className="chat-interface">
      {props.connectionError && (
        <div className="connection-error">
          <span>{props.connectionError}</span>
          <button className="reconnect-button" onClick={props.onReconnect}>Reconnect</button>
        </div>
      )}
      <div className="chat-container">
        <MessageDisplay messages={props.messages} isTyping={props.isTyping} />
        <InputBox {...props} />
      </div>
    </main>
  )
}

