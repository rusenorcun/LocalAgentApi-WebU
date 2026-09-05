import { useNavigate, useLocation, Routes, Route } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SlidersHorizontal, KeyRound, Cog, Server } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import PersonaTab from './settings/PersonaTab'
import PasswordTab from './settings/PasswordTab'
import SystemTab from './settings/SystemTab'

// "Ayarlar" — PanelLayout'un tek gezinme rayı zaten solda olduğundan bu sayfa
// artık kendi kenar çubuğunu çizmiyor; alt gruplar üstte yatay sekme olarak
// gösteriliyor. Kişisel ayarlar (persona/şifre/sistem) herkese açık; "Sunucu"
// (backend genelindeki ayarlar) yalnızca admin rolüne açık ve ayrı bir rotaya
// (/admin/settings) yönlendirir — orada AdminPage kendi SettingsTab'ını render eder.
const TABS = [
  { id: 'persona', icon: SlidersHorizontal, key: 'settings.navPersona', path: '/settings/persona' },
  { id: 'password', icon: KeyRound, key: 'settings.navPassword', path: '/settings/password' },
  { id: 'system', icon: Cog, key: 'settings.navSystem', path: '/settings/system' },
]

export default function SettingsPage() {
  const navigate = useNavigate()
  const loc = useLocation()
  const { t } = useTranslation()
  const { role } = useAuthStore()
  const active = TABS.find((x) => loc.pathname.startsWith(x.path))?.id ?? 'persona'

  return (
    <div className="max-w-[820px]">
      <nav className="flex flex-wrap gap-2 mb-6">
        {TABS.map((tab) => (
          <button key={tab.id} onClick={() => navigate(tab.path)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors hover:bg-[var(--surface-2)]"
            style={{
              border: '1px solid var(--border)',
              background: active === tab.id ? 'var(--accent-soft)' : 'var(--surface)',
              color: active === tab.id ? 'var(--text)' : 'var(--text-2)',
              cursor: 'pointer',
            }}>
            <tab.icon size={15} />
            {t(tab.key)}
          </button>
        ))}
        {role === 'admin' && (
          <button onClick={() => navigate('/admin/settings')}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors hover:bg-[var(--surface-2)]"
            style={{ border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-2)', cursor: 'pointer' }}>
            <Server size={15} />
            Sunucu
          </button>
        )}
      </nav>

      <Routes>
        <Route path="persona" element={<PersonaTab />} />
        <Route path="password" element={<PasswordTab />} />
        <Route path="system" element={<SystemTab />} />
        <Route path="*" element={<PersonaTab />} />
      </Routes>
    </div>
  )
}
