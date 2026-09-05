import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { Sun, Moon, Monitor, Globe } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { useTheme } from '../hooks/useTheme'
import i18n from '../i18n/index'

const themes = [
  { id: 'light', icon: Sun, labelKey: 'theme.light' },
  { id: 'dark', icon: Moon, labelKey: 'theme.dark' },
  { id: 'system', icon: Monitor, labelKey: 'theme.system' },
]

const langs = [
  { id: 'tr', flag: '🇹🇷', label: 'Türkçe' },
  { id: 'en', flag: '🇬🇧', label: 'English' },
]

export default function OnboardingPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { setTheme } = useTheme()
  const { setPreferences } = useAuthStore()
  const [step, setStep] = useState(0)
  const [selTheme, setSelTheme] = useState('system')
  const [selLang, setSelLang] = useState('tr')

  const finish = async () => {
    setTheme(selTheme)
    setPreferences(selTheme, selLang)
    i18n.changeLanguage(selLang)
    localStorage.setItem('onboarded', '1')
    // Tercihi profile de yaz (cihazlar arası taşınır); hata olursa yerel tercih yeter
    try {
      const { updatePreferences } = await import('../api/auth')
      await updatePreferences({ theme: selTheme, lang: selLang })
    } catch { /* yerel tercih yeterli */ }
    navigate('/panel')
  }

  return (
    <div className="relative min-h-[100dvh] flex items-center justify-center p-4 overflow-hidden"
         style={{ background: 'var(--bg)' }}>
      <div className="absolute inset-0 pointer-events-none"
           style={{ background: 'radial-gradient(circle at 50% 30%, rgba(99,102,241,.16), transparent 60%)' }} />
      <div className="absolute inset-0 pointer-events-none opacity-40 grid-bg" />
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative z-10 w-full max-w-md p-8 text-center"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)',
                 borderRadius: 18, boxShadow: 'var(--shadow-lg)' }}
      >
        <div className="logo-tile mx-auto mb-5"
             style={{ width: 46, height: 46, borderRadius: 12, fontSize: 19,
                      boxShadow: '0 10px 30px -8px var(--glow)' }}>›_</div>
        <AnimatePresence mode="wait">
          {step === 0 && (
            <motion.div key="step0"
              initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}>
              <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text)' }}>
                {t('onboarding.welcome')}
              </h1>
              <p className="mb-8" style={{ color: 'var(--text-2)' }}>{t('onboarding.step1')}</p>
              <div className="grid grid-cols-3 gap-3 mb-8">
                {themes.map(({ id, icon: Icon, labelKey }) => (
                  <button key={id}
                    onClick={() => setSelTheme(id)}
                    className="flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all"
                    style={{
                      borderColor: selTheme === id ? 'var(--accent)' : 'var(--border)',
                      background: selTheme === id ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--surface-2)',
                      color: 'var(--text)',
                    }}>
                    <Icon size={24} style={{ color: selTheme === id ? 'var(--accent)' : 'var(--text-2)' }} />
                    <span className="text-sm font-medium">{t(labelKey)}</span>
                  </button>
                ))}
              </div>
              <button onClick={() => setStep(1)}
                className="w-full py-3 rounded-xl font-semibold text-base transition-all hover:brightness-110"
                style={{ background: 'var(--grad)', color: '#fff', border: 'none', cursor: 'pointer',
                         boxShadow: '0 10px 28px -10px var(--glow)' }}>
                {t('onboarding.continue')}
              </button>
            </motion.div>
          )}
          {step === 1 && (
            <motion.div key="step1"
              initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}>
              <Globe size={40} className="mx-auto mb-4" style={{ color: 'var(--accent)' }} />
              <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text)' }}>
                {t('onboarding.step2')}
              </h2>
              <div className="grid grid-cols-2 gap-3 my-8">
                {langs.map(({ id, flag, label }) => (
                  <button key={id}
                    onClick={() => setSelLang(id)}
                    className="flex flex-col items-center gap-2 p-5 rounded-xl border-2 transition-all"
                    style={{
                      borderColor: selLang === id ? 'var(--accent)' : 'var(--border)',
                      background: selLang === id ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--surface-2)',
                    }}>
                    <span className="text-3xl">{flag}</span>
                    <span className="font-medium" style={{ color: 'var(--text)' }}>{label}</span>
                  </button>
                ))}
              </div>
              <div className="flex gap-3">
                <button onClick={() => setStep(0)}
                  className="flex-1 py-3 rounded-xl font-semibold transition-opacity hover:opacity-80"
                  style={{ background: 'var(--surface-2)', color: 'var(--text)' }}>
                  ← Geri
                </button>
                <button onClick={finish}
                  className="flex-2 flex-grow py-3 rounded-xl font-semibold transition-all hover:brightness-110"
                  style={{ background: 'var(--grad)', color: '#fff', border: 'none', cursor: 'pointer',
                           boxShadow: '0 10px 28px -10px var(--glow)' }}>
                  {t('onboarding.finish')} →
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
