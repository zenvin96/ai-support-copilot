import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Chat from './pages/Chat'
import Knowledge from './pages/Knowledge'
import Login from './pages/Login'
import Runs from './pages/Runs'
import Usage from './pages/Usage'
import { auth } from './lib/api'

function Private({ children }: { children: React.ReactNode }) {
  return auth.token ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Private><Layout /></Private>}>
          <Route path="/chat" element={<Chat />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/admin/runs" element={<Runs />} />
          <Route path="/admin/usage" element={<Usage />} />
        </Route>
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
