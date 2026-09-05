import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutGrid, MessageSquare, Cpu, Server, KeyRound, ScrollText, Users, FileText, Settings, LogOut, ChevronDown,
  Menu, X,
} from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { useUIStore } from '../store/uiStore'
import { useTheme } from '../hooks/useTheme'
import { logout as apiLogout } from '../api/auth'
import { lockBodyScroll } from '../lib/scrollLock'
import Sidebar from '../components/chat/Sidebar'

interface NavItem {
  id: string
  label: string
  icon: typeof LayoutGrid
  path: string
  match: (p: string) => boolean
  adminOnly?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Genel Bakış', icon: LayoutGrid, path: '/panel', match: (p) => p === '/panel' },
  { id: 'chat', label: 'Sohbet', icon: MessageSquare, path: '/chat', match: (p) => p.startsWith('/chat') },
  { id: 'models', label: 'Modeller', icon: Cpu, path: '/admin/models', match: (p) => p.startsWith('/admin/models'), adminOnly: true },
  { id: 'mcp', label: 'MCP Server', icon: Server, path: '/mcp', match: (p) => p === '/mcp' },
  { id: 'apikeys', label: 'API Bağlantıları', icon: KeyRound, path: '/apikeys', match: (p) => p === '/apikeys' },
  { id: 'logs', label: 'Loglar', icon: ScrollText, path: '/admin/audit', match: (p) => p.startsWith('/admin/audit'), adminOnly: true },
  { id: 'users', label: 'Kullanıcılar', icon: Users, path: '/admin/users', match: (p) => p.startsWith('/admin/users'), adminOnly: true },
  { id: 'docs', label: 'Dokümantasyon', icon: FileText, path: '/docs', match: (p) => p.startsWith('/docs') },
  { id: 'settings', label: 'Ayarlar', icon: Settings, path: '/settings/persona', match: (p) => p.startsWith('/settings') || p.startsWith('/admin/settings') },
]

const TITLES: Record<string, [string, string]> = {
  dashboard: ['Genel Bakış', 'Sisteminin anlık durumu'],
  chat: ['Sohbet', 'Yerel modelinle konuş — MCP araçları etkin'],
  models: ['Modeller', "Yerel LLM'lerini indir, yükle ve yönet"],
  mcp: ['MCP Server', 'Model Context Protocol sunucusu kurulumu ve araçlar'],
  apikeys: ['API Bağlantıları', 'Ollama endpoint bağlantıları ve kişisel API anahtarları'],
  logs: ['Loglar', 'Sistem ve yönetim olayları'],
  users: ['Kullanıcılar', 'Erişimi olan kişileri yönet'],
  docs: ['Dokümantasyon', "LocalAgent nasıl kurulur ve kullanılır"],
  settings: ['Ayarlar', 'Sistem ve tercih ayarları'],
}

export default function PanelLayout() {
  const { t } = useTranslation()
  const loc = useLocation()
  const navigate = useNavigate()
  const { username, role, logout } = useAuthStore()
  const { theme, setTheme } = useTheme()
  const [menuOpen, setMenuOpen] = useState(false)
  // Paylaşılan store'da: sohbet rotasındayken ChatPage'in kendi üst çubuğu da
  // bu çekmeceyi açabilsin diye (bkz. ChatPage.tsx).
  const mobileNavOpen = useUIStore((s) => s.mainNavOpen)
  const setMobileNavOpen = useUIStore((s) => s.setMainNavOpen)
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)

  // Rota değişince mobilde açık kalan gezinme çekmecesini otomatik kapat.
  useEffect(() => { setMobileNavOpen(false) }, [loc.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  // Çekmece açıkken: arka plan kaymasın + Esc ile kapansın.
  useEffect(() => {
    if (!mobileNavOpen) return
    const release = lockBodyScroll()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobileNavOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => {
      release()
      window.removeEventListener('keydown', onKey)
    }
  }, [mobileNavOpen, setMobileNavOpen])

  const visibleItems = NAV_ITEMS.filter((it) => !it.adminOnly || role === 'admin')
  const active = NAV_ITEMS.find((it) => it.match(loc.pathname))
  const [pageTitle, pageSubtitle] = (active && TITLES[active.id]) || ['', '']

  // Sohbet kendi tam ekran düzenini (mesajlar + composer) yönetir; header/main padding'i olmadan tam yer kaplasın.
  const isChatRoute = loc.pathname.startsWith('/chat')

  // Sohbet listesi artık AYRI bir kolon değil — bu tek gezinme rayının kendi
  // içinde, "Sohbet" düğmesinin altında açılıp kapanan bir bölüm (NewDesing'deki
  // chatListOpen davranışının birebir karşılığı). Paylaşılan uiStore bayrağı
  // kullanılıyor ki ChatPage'in üst çubuğundaki menü ikonu da aynı bölümü
  // aç/kapat edebilsin.
  const chatListOpen = useUIStore((s) => s.sidebarOpen)
  const toggleChatList = useUIStore((s) => s.toggleSidebar)
  const setChatListOpen = useUIStore((s) => s.setSidebarOpen)

  const handleLogout = async () => {
    await apiLogout().catch(() => {})
    logout()
    navigate('/login')
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-[250px_1fr] min-h-[100dvh]" style={{ background: 'var(--bg)' }}>
      {/* Mobil üst çubuk: yalnızca sohbet DIŞI rotalarda — sohbet kendi tam
          yükseklikli (100dvh) üst çubuğunu kullanıyor, ikisi aynı anda akışta
          olursa toplam yükseklik viewport'u aşar. Sohbette mobil menüye
          erişim ChatPage'in kendi üst çubuğundaki menü ikonuyla sağlanıyor
          (bkz. ChatPage.tsx, paylaşılan mainNavOpen bayrağı). */}
      {!isChatRoute && (
        <div className="md:hidden flex items-center justify-between px-4 py-3 sticky top-0 z-30 pt-safe"
             style={{ borderBottom: '1px solid var(--border-2)', background: 'color-mix(in srgb, var(--surface) 85%, transparent)', backdropFilter: 'blur(10px)' }}>
          <button onClick={() => setMobileNavOpen(true)}
            className="p-2 -ml-2 rounded-lg" style={{ background: 'none', border: 'none', color: 'var(--text)', cursor: 'pointer' }}>
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <span className="logo-tile" style={{ width: 26, height: 26, fontSize: 11 }}>›_</span>
            <span className="font-bold text-[14px]" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>{t('app.appName')}</span>
          </div>
          <button onClick={() => setTheme(isDark ? 'light' : 'dark')}
            className="p-2 -mr-2 rounded-lg" style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer' }}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
              <path d="M20 14a8 8 0 1 1-9-9 6 6 0 0 0 9 9z" />
            </svg>
          </button>
        </div>
      )}

      {/* Mobilde çekmece açıkken arkaya karartma */}
      {mobileNavOpen && (
        <div className="drawer-scrim is-nav md:hidden" onClick={() => setMobileNavOpen(false)} />
      )}

      {/* SIDEBAR — md+ ekranlarda sabit sütun, mobilde soldan açılan çekmece
          (konumlandırma .nav-drawer içinde; bkz. index.css) */}
      <aside
        className={`nav-drawer flex flex-col ${mobileNavOpen ? 'is-open' : ''}`}
        style={{ background: 'var(--surface)' }}>
        <div className="flex items-center justify-between px-5 pt-5 pb-4 md:block">
          <button onClick={() => navigate('/panel')}
            className="flex items-center gap-2.5 text-left"
            style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <span className="logo-tile" style={{ width: 32, height: 32, fontSize: 14 }}>›_</span>
            <div>
              <div className="font-bold text-[16px] leading-none" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>
                {t('app.appName')}
              </div>
              <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>panel</div>
            </div>
          </button>
          <button onClick={() => setMobileNavOpen(false)}
            className="p-1.5 rounded-lg md:hidden" style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <div className="px-3 pt-2 pb-1 text-[11px] uppercase font-semibold" style={{ letterSpacing: '.08em', color: 'var(--text-3)' }}>
          Çalışma alanı
        </div>

        <nav className="px-3 flex flex-col gap-0.5 flex-1 overflow-y-auto">
          {visibleItems.map((it) => {
            const isActive = active?.id === it.id
            const isChatItem = it.id === 'chat'
            const Icon = it.icon
            return (
              <div key={it.id}>
                <button
                  onClick={() => {
                    // Masaüstünde "Sohbet" bu rayın içinde açılan bir akordiyon.
                    // Mobilde ray zaten bir çekmece; liste ChatPage'in kendi
                    // "Sohbetler" düğmesinden alttan açılıyor — burada yalnızca
                    // sohbete gidip çekmeceyi kapatıyoruz.
                    const isDesktop = window.matchMedia('(min-width: 768px)').matches
                    if (isChatItem && isDesktop) {
                      if (isChatRoute) toggleChatList()
                      else { navigate(it.path); setChatListOpen(true) }
                    } else {
                      navigate(it.path)
                    }
                    setMobileNavOpen(false)
                  }}
                  className="relative flex items-center gap-3 w-full px-3 py-2.5 rounded-[10px] text-sm font-medium text-left transition-colors hover:bg-[var(--surface-2)]"
                  style={{
                    border: 'none', cursor: 'pointer',
                    background: isActive ? 'var(--accent-soft)' : 'transparent',
                    color: isActive ? 'var(--text)' : 'var(--text-2)',
                  }}>
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 rounded-[3px]"
                        style={{ width: 3, height: 18, background: 'var(--grad)', opacity: isActive ? 1 : 0 }} />
                  <Icon size={18} className="shrink-0" />
                  <span className="flex-1">{it.label}</span>
                  {isChatItem && (
                    <ChevronDown size={14} className="hidden md:block shrink-0" style={{
                      color: 'var(--text-3)',
                      transform: chatListOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform .2s',
                    }} />
                  )}
                </button>

                {/* Sohbet listesi: masaüstünde tam burada, düğmenin altında açılır.
                    Mobilde gizli — orada liste ChatPage'in alttan açılan sayfası. */}
                {isChatItem && chatListOpen && (
                  <div className="hidden md:block mt-0.5 mb-1 pl-1">
                    <Sidebar />
                  </div>
                )}
              </div>
            )
          })}
        </nav>

        {/* Hesap */}
        <div className="p-3.5 relative">
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
              <div className="absolute bottom-full left-3.5 right-3.5 mb-2 py-1.5 rounded-xl z-50"
                   style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-lg)' }}>
                <button onClick={() => { setMenuOpen(false); navigate('/settings/persona') }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left hover:bg-[var(--surface-2)] transition-colors"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text)' }}>
                  <Settings size={15} /> Ayarlar
                </button>
                <button onClick={handleLogout}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left hover:bg-[var(--surface-2)] transition-colors"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--error)' }}>
                  <LogOut size={15} /> {t('auth.logout')}
                </button>
              </div>
            </>
          )}
          <button onClick={() => setMenuOpen((v) => !v)}
            className="w-full flex items-center gap-2.5 p-3 rounded-xl transition-colors hover:bg-[var(--surface-3)]"
            style={{ border: '1px solid var(--border)', background: 'var(--surface-2)', cursor: 'pointer' }}>
            <div className="w-[34px] h-[34px] rounded-[9px] grid place-items-center font-bold text-sm shrink-0"
                 style={{ background: 'var(--grad)', color: '#fff' }}>
              {username?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0 text-left">
              <div className="text-[13px] font-semibold truncate" style={{ color: 'var(--text)' }}>{username}</div>
              <div className="text-[11px]" style={{ color: 'var(--text-3)' }}>{role === 'admin' ? 'Admin' : 'Üye'}</div>
            </div>
          </button>
        </div>
      </aside>

      {/* MAIN */}
      <div className="flex flex-col min-w-0">
        {!isChatRoute && (
          <header className="flex items-center justify-between px-4 md:px-7 py-4 sticky top-0 z-[5]"
                  style={{ borderBottom: '1px solid var(--border)', background: 'color-mix(in srgb, var(--surface) 70%, transparent)', backdropFilter: 'blur(10px)' }}>
            <div className="min-w-0">
              <h1 className="text-[17px] md:text-[19px] font-bold m-0 truncate" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>{pageTitle}</h1>
              <div className="text-[13px] mt-0.5 hidden sm:block" style={{ color: 'var(--text-3)' }}>{pageSubtitle}</div>
            </div>
            {/* "Oturum aktif" rozeti + tema butonu mobilde üst çubukta zaten var — burada yalnızca md+ ekranlarda tekrar gösteriliyor. */}
            <div className="hidden md:flex items-center gap-3 shrink-0">
              <div className="flex items-center gap-2 px-3 py-[7px] rounded-[9px] text-[12.5px]"
                   style={{ border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-2)' }}>
                <span data-dot="active" /> Oturum aktif
              </div>
              <button onClick={() => setTheme(isDark ? 'light' : 'dark')}
                className="w-[38px] h-[38px] grid place-items-center rounded-[10px] transition-opacity hover:opacity-80"
                style={{ border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-2)', cursor: 'pointer' }}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                  <path d="M20 14a8 8 0 1 1-9-9 6 6 0 0 0 9 9z" />
                </svg>
              </button>
            </div>
          </header>
        )}

        <main className={isChatRoute ? 'flex-1 min-h-0' : 'flex-1 p-4 md:p-7 overflow-y-auto overflow-x-hidden'}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
