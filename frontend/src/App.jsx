import React, { useState } from 'react'
import Upload from './components/Upload'
import DocumentList from './components/DocumentList'
import Chat from './components/Chat'

function App() {
  const [refresh, setRefresh] = useState(0)
  
  const triggerRefresh = () => setRefresh(r => r + 1)
  
  return (
    <div>
      <header>
        <div className="container">
          <h1>Portalis Logística - Asistente RAG Documental</h1>
          <p style={{marginTop: '5px', opacity: 0.9}}>Modo sin llaves (mock/determinista)</p>
        </div>
      </header>
      <div className="container">
        <div className="grid">
          <div>
            <Upload onUploadSuccess={triggerRefresh} />
            <DocumentList refresh={refresh} />
          </div>
          <div>
            <Chat />
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
