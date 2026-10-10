import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { FeedbackProvider } from './components/feedback/FeedbackProvider'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FeedbackProvider>
      <App />
    </FeedbackProvider>
  </StrictMode>,
)
