import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../../store/authStore'
import { useTheme } from '../../hooks/useTheme'
import { updatePreferences } from '../../api/auth'

// Sistem ayarları: tema + dil. /settings/system
export default function SystemTab() {
  const { t, i18n } = useTranslation()
  const { lang, setLang } = useAuthStore()
  const { theme, setTheme } = useTheme()
  const changeLang = (l: string) => {
    setLang(l); i18n.changeLanguage(l); updatePreferences({ lang: l }).catch(() => {})
  }
  const label = 'text-[11px] font-semibold uppercase tracking-wider mb-2'
  return (
    <div className="max-w-md">
      <h1 className="text-xl font-bold mb-4" style={{ color: 'var(--text)' }}>{t('settings.system')}</h1>
      <p className={label} style={{ color: 'var(--text-3)' }}>{t('settings.theme')}</p>
      <div className="flex gap-1.5 p-1 rounded-[10px] mb-5"
           style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
        {['system', 'light', 'dark'].map((tVal) => (
          <button key={tVal} onClick={() => setTheme(tVal)}
            className="flex-1 text-[13px] font-medium py-1.5 rounded-lg transition-all"
            style={{ background: theme === tVal ? 'var(--grad)' : 'transparent',
                     color: theme === tVal ? '#fff' : 'var(--text-2)',
                     border: 'none', cursor: 'pointer' }}>
            {t(`settings.${tVal}`)}
          </button>
        ))}
      </div>
      <p className={label} style={{ color: 'var(--text-3)' }}>{t('settings.language')}</p>
      <div className="flex gap-1.5 p-1 rounded-[10px]"
           style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
        {['tr', 'en'].map((l) => (
          <button key={l} onClick={() => changeLang(l)}
            className="flex-1 text-[13px] font-medium py-1.5 rounded-lg transition-all"
            style={{ background: lang === l ? 'var(--grad)' : 'transparent',
                     color: lang === l ? '#fff' : 'var(--text-2)',
                     border: 'none', cursor: 'pointer' }}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
  )
}
