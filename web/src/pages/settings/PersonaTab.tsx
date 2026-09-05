import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Save, Check } from 'lucide-react'
import { getMe, updatePreferences } from '../../api/auth'

// Global persona (tüm sohbetler). /settings/persona
export default function PersonaTab() {
  const { t } = useTranslation()
  const [persona, setPersona] = useState('')
  const [saved, setSaved] = useState(false)
  useEffect(() => { getMe().then((r) => setPersona(r.data?.persona || '')).catch(() => {}) }, [])
  const save = async () => {
    try { await updatePreferences({ persona }); setSaved(true); setTimeout(() => setSaved(false), 2000) } catch { /* sessiz */ }
  }
  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-bold mb-1" style={{ color: 'var(--text)' }}>{t('settings.persona')}</h1>
      <p className="text-xs mb-4" style={{ color: 'var(--text-3)' }}>{t('settings.personaHint')}</p>
      <textarea
        value={persona}
        onChange={(e) => setPersona(e.target.value)}
        rows={10}
        placeholder={t('settings.personaPlaceholder')}
        className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y leading-relaxed"
        style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
      />
      <div className="flex items-center gap-2 mt-3">
        <button onClick={save}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-90"
          style={{ background: 'var(--grad)', color: '#fff' }}>
          <Save size={15} /> {t('settings.save')}
        </button>
        {saved && <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--success, #10b981)' }}><Check size={14} /> {t('settings.saved')}</span>}
      </div>
    </div>
  )
}
