import React, { useState } from 'react'
import axios from 'axios'

const API_URL = 'http://localhost:8000'

function Upload({ onUploadSuccess }) {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  
  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file) return
    
    const formData = new FormData()
    formData.append('file', file)
    formData.append('workspace_id', 'default')
    
    setUploading(true)
    setMessage('')
    
    try {
      const res = await axios.post(`${API_URL}/api/documents/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setMessage(`Subido: ${res.data.filename} - Estado: ${res.data.status}`)
      setFile(null)
      e.target.reset()
      onUploadSuccess()
    } catch (err) {
      setMessage(`Error: ${err.response?.data?.detail || err.message}`)
    } finally {
      setUploading(false)
    }
  }
  
  return (
    <div className="card" style={{marginBottom: '20px'}}>
      <h2>Subir Documento (PDF/DOCX)</h2>
      <form onSubmit={handleSubmit}>
        <div className="upload-area">
          <input 
            type="file" 
            accept=".pdf,.docx"
            onChange={(e) => setFile(e.target.files[0])}
          />
          <p style={{marginTop: '10px', color: '#718096'}}>
            {file ? file.name : 'Selecciona un archivo'}
          </p>
        </div>
        <button type="submit" disabled={!file || uploading} style={{marginTop: '15px'}}>
          {uploading ? 'Subiendo...' : 'Subir e Ingestar'}
        </button>
      </form>
      {message && <p style={{marginTop: '10px'}}>{message}</p>}
    </div>
  )
}

export default Upload
