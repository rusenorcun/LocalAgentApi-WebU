import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import axios from 'axios'
import { useAuthStore } from './store/authStore'
import { useTheme } from './hooks/useTheme'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'

// Route-level code splitting: her sayfa kendi chunk'inda yuklenir. Ana paket
// kuculur (KaTeX/highlight gibi agir bagimliliklar yalnizca ilgili sayfada
// indirilir). Landing/Login ilk boyama icin eager kalir.
const ChatPage = lazy(() => import('./pages/ChatPage'))
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'))
const AdminPage = lazy(() => import('./pages/admin/AdminPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const DocsPage = lazy(() => import('./pages/DocsPage'))
const PanelLayout = lazy(() => import('./layouts/PanelLayout'))
const OverviewPage = lazy(() => import('./pages/panel/OverviewPage'))
const McpServerPage = lazy(() => import('./pages/panel/McpServerPage'))
const ApiKeysPage = lazy(() => import('./pages/panel/ApiKeysPage'))

function PageFallback() {
  return (
    <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span className="text-sm" style={{ color: 'var(--text-3)' }}>Yükleniyor…</span>
    </div>
  )
}

// Render hatalarında beyaz ekran yerine anlaşılır mesaj + geri dönüş.
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
                      justifyContent: 'center', background: 'var(--bg)', padding: 16 }}>
          <div style={{ maxWidth: 480, textAlign: 'center', background: 'var(--surface)',
                        border: '1px solid var(--border)', borderRadius: 20, padding: 32 }}>
            <h2 style={{ color: 'var(--text)', fontSize: 18, marginBottom: 8 }}>Bir şeyler ters gitti</h2>
            <p style={{ color: 'var(--text-3)', fontSize: 12, fontFamily: 'monospace',
                        wordBreak: 'break-word', marginBottom: 16 }}>
              {this.state.error.message}
            </p>
            <button
              onClick={() => { this.setState({ error: null }); window.location.href = '/' }}
              style={{ background: 'var(--grad)', color: '#fff', border: 'none',
                       borderRadius: 12, padding: '10px 20px', fontWeight: 600, cursor: 'pointer' }}>
              Ana sayfaya dön
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.accessToken)
  // G2: token artık localStorage'da tutulmadığı için sayfa yenilenince boştur.
  // Login'e atmadan önce httpOnly refresh cookie ile sessizce yeni token dene.
  const [checking, setChecking] = useState(!token)
  useEffect(() => {
    if (token) return
    let cancelled = false
    axios.post('/api/v2/auth/refresh', {}, { withCredentials: true })
      .then((r) => {
        if (!cancelled) {
          useAuthStore.getState().setTokens(r.data.access_token, r.data.username, r.data.role)
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setChecking(false) })
    return () => { cancelled = true }
  }, [token])
  if (token) return <>{children}</>
  if (checking) return null // sessiz yenileme sürüyor — kısa boş ekran
  return <Navigate to="/login" replace />
}

// Panel (giriş gerektiren) rotalarını tek bir PanelLayout kabuğuyla sarar;
// onboarding tamamlanmadıysa oraya yönlendirir. Ayrı bir bileşen olarak
// tanımlanır ki her alt rota geçişinde localStorage kontrolü yeniden çalışsın.
function RequirePanel({ children }: { children: ReactNode }) {
  const onboarded = localStorage.getItem('onboarded')
  return (
    <RequireAuth>
      {!onboarded ? <Navigate to="/onboarding" replace /> : <>{children}</>}
    </RequireAuth>
  )
}

export default function App() {
  useTheme()

  return (
    <ErrorBoundary>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          {/* Herkese açık: ana sayfa artık sohbet DEĞİL, Panel/Dokümantasyon ayrımı yapan tanıtım sayfası */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/docs" element={<DocsPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />

          {/* Panel: tek gezinme rayı + üst başlık kabuğu, giriş şart */}
          <Route element={<RequirePanel><PanelLayout /></RequirePanel>}>
            <Route path="/panel" element={<OverviewPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:chatId" element={<ChatPage />} />
            <Route path="/admin/*" element={<AdminPage />} />
            <Route path="/settings/*" element={<SettingsPage />} />
            <Route path="/mcp" element={<McpServerPage />} />
            <Route path="/apikeys" element={<ApiKeysPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  )
}
