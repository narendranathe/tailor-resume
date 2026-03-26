import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import App from './App.jsx'
import './App.css'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
  console.warn(
    'VITE_CLERK_PUBLISHABLE_KEY is not set. Authentication will not work. ' +
    'Copy .env.example to .env.local and fill in your Clerk publishable key.'
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY || 'pk_test_placeholder'}>
      <App />
    </ClerkProvider>
  </React.StrictMode>
)
