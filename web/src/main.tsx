import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from '@/app/App'
import { ensureTheme } from '@/design/theme'

import './index.css'

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Bisect dashboard: #root element is missing from index.html')
}

ensureTheme()
createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
