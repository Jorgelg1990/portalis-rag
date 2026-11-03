import React, { useState } from 'react'
import axios from 'axios'

const API_URL = 'http://localhost:8000'

function Chat() {
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedCitation, setSelectedCitation] = useState(null)
  
  const askQuestion = async (e) => {
    e.preventDefault()
    if (!question.trim()) return
    
    const userMsg = { role: 'user', content: question }
    setMessages(prev => [...prev, userMsg])
    setQuestion('')
    setLoading(true)
    
    try {
      const res = await axios.post(`${API_URL}/api/query`, {
        question: question,
        workspace_id: 'default',
        top_k: 4
      })
      
      const assistantMsg = {
        role: 'assistant',
        content: res.data.answer,
        citations: res.data.citations,
        meta: {
          confidence: res.data.confidence,
          insufficient: res.data.insufficient_evidence,
          action: res.data.action,
          model: res.data.model_used,
          latency: res.data.latency_ms,
          fragments: res.data.fragments_retrieved
        }
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div className="card">
      <h2>Chat con el Asistente</h2>
      <div className="chat-box">
        {messages.length === 0 && (
          <p style={{color: '#718096', textAlign: 'center', marginTop: '50px'}}>
            Sube documentos y haz preguntas...
          </p>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="bubble">
              <div>{msg.content}</div>
              {msg.citations && msg.citations.length > 0 && (
                <div className="citations">
                  <strong>Citas:</strong>
                  {msg.citations.map((c, i) => (
                    <div key={i} className="citation">
                      <button 
                        className="citation-btn"
                        onClick={() => setSelectedCitation(c)}
                      >
                        [{i+1}] {c.document_name} {c.page_number ? `(p.${c.page_number})` : ''}
                      </button>
                      <div style={{marginTop: '3px'}}>{c.snippet}</div>
                    </div>
                  ))}
                </div>
              )}
              {msg.meta && (
                <div style={{marginTop: '8px', fontSize: '11px', opacity: 0.7}}>
                  Confianza: {msg.meta.confidence.toFixed(2)} | Acción: {msg.meta.action} | 
                  Frags: {msg.meta.fragments} | Latencia: {msg.meta.latency}ms | Modelo: {msg.meta.model}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="message assistant"><div className="bubble">Pensando...</div></div>}
      </div>
      <form onSubmit={askQuestion}>
        <div className="input-row">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Pregunta sobre los documentos..."
            disabled={loading}
          />
          <button type="submit" disabled={loading || !question.trim()}>Enviar</button>
        </div>
      </form>
      
      {selectedCitation && (
        <div className="modal" onClick={() => setSelectedCitation(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <span className="close" onClick={() => setSelectedCitation(null)}>&times;</span>
            <h3>Fragmento Fuente</h3>
            <p style={{marginTop: '10px'}}><strong>Documento:</strong> {selectedCitation.document_name}</p>
            {selectedCitation.page_number && <p><strong>Página:</strong> {selectedCitation.page_number}</p>}
            <div style={{marginTop: '15px', padding: '15px', background: '#f7fafc', borderRadius: '4px', whiteSpace: 'pre-wrap'}}>
              {selectedCitation.snippet}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Chat
