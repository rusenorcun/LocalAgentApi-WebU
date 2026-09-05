import { Routes, Route } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import UsersTab from './UsersTab'
import ModelsTab from './ModelsTab'
import AuditTab from './AuditTab'
import SettingsTab from './SettingsTab'

// Admin içeriği artık kendi kenar çubuğunu çizmiyor — PanelLayout'un tek
// birleşik gezinme rayı (Modeller / Loglar / Kullanıcılar / Ayarlar→Sunucu)
// bu sayfalara doğrudan yönlendirir. Rol kontrolü burada korunuyor.
export default function AdminPage() {
  const { role } = useAuthStore()

  if (role !== 'admin') {
    return (
      <div className="flex items-center justify-center py-24">
        <p style={{ color: 'var(--error)' }}>Erişim reddedildi.</p>
      </div>
    )
  }

  return (
    <Routes>
      <Route path="users" element={<UsersTab />} />
      <Route path="models" element={<ModelsTab />} />
      <Route path="audit" element={<AuditTab />} />
      <Route path="settings" element={<SettingsTab />} />
      <Route path="*" element={<UsersTab />} />
    </Routes>
  )
}
