import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API_URL = 'http://localhost:8000'

function DocumentList({ refresh }) {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  
  const fetchDocs = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/documents/list?workspace_id=default`)
      setDocs(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }
  
  useEffect(() => {
    fetchDocs()
    const interval = setInterval(fetchDocs, 3000) // polling
    return () => clearInterval(interval)
  }, [refresh])
  
  return (
    <div className="card">
      <h2>Documentos</h2>
      {loading ? <p>Cargando...</p> : (
        <div className="doc-list">
          {docs.length === 0 ? <p>No hay documentos</p> : docs.map(doc => (
            <div key={doc.document_id} className="doc-item">
              <div>
                <strong>{doc.filename}</strong>
                <br />
                <small style={{color: '#718096'}}>{doc.file_type.toUpperCase()}</small>
              </div>
              <span className={`status ${doc.status}`}>{doc.status}</span>
            </div>
          ))}
        </div>
      )}
      <p style={{marginTop: '10px', fontSize: '12px', color: '#718096'}}>
        Actualización automática cada 3s
      </p>
    </div>
  )
}

export default DocumentList
