import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import PublicQuote from './public/PublicQuote.jsx'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      {window.location.pathname.startsWith('/quote') ? <PublicQuote /> : <App />}
    </BrowserRouter>
  </React.StrictMode>
)
