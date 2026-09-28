import { Component, lazy, Suspense, useEffect, useState, type ComponentType, type ReactNode } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import axios from 'axios'
import { useAuthStore } from './store/authStore'
import { useTheme } from './hooks/useTheme'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'

// Yeniden derlemeden (deploy) sonra acik kalan sekme eski chunk adlarini ister
// ve 404 alir ("Failed to fetch dynamically imported module"). Boyle bir hatada
// sayfa bir kez yenilenir; yeni index.html guncel chunk adlarini getirir.
// Dongu olmasin diye son 10 sn icinde zaten yenilendiyse (veya sessionStorage
// kullanilamiyorsa) hata ErrorBoundary'e birakilir.
const CHUNK_RELOAD_KEY = 'chunk-reload-at'

function reloadOnceForStaleChunk(): boolean {
  try {
    const last = Number(sessionStorage.getItem(CHUNK_RELOAD_KEY)) || 0
    if (Date.now() - last < 10_000) return false
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()))
  } catch {
    return false
  }
  window.location.reload()
  return true
}

function lazyPage<T extends ComponentType<any>>(load: () => Promise<{ default: T }>) {
  return lazy(() => load().catch((err) => {
    // Yenileme surerken Suspense yedegi ekranda kalsin (hata sayfasi yanip sonmesin)
    if (reloadOnceForStaleChunk()) return new Promise<never>(() => {})
    throw err
  }))
}

// Route-level code splitting: her sayfa kendi chunk'inda yuklenir. Ana paket
// kuculur (KaTeX/highlight gibi agir bagimliliklar yalnizca ilgili sayfada
// indirilir). Landing/Login ilk boyama icin eager kalir.
const ChatPage = lazyPage(() => import('./pages/ChatPage'))
const OnboardingPage = lazyPage(() => import('./pages/OnboardingPage'))
const AdminPage = lazyPage(() => import('./pages/admin/AdminPage'))
const SettingsPage = lazyPage(() => import('./pages/SettingsPage'))
const DocsPage = lazyPage(() => import('./pages/DocsPage'))
const PanelLayout = lazyPage(() => import('./layouts/PanelLayout'))
const OverviewPage = lazyPage(() => import('./pages/panel/OverviewPage'))
const McpServerPage = lazyPage(() => import('./pages/panel/McpServerPage'))
const ApiKeysPage = lazyPage(() => import('./pages/panel/ApiKeysPage'))

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
