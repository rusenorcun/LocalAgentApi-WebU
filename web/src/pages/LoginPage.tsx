import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { Eye, EyeOff } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { login, register } from '../api/auth'

function passwordScore(p: string): number {
  let s = 0
  if (p.length >= 8) s++
  if (p.length >= 12) s++
  if (/[A-Z]/.test(p)) s++
  if (/[0-9]/.test(p)) s++
  if (/[^A-Za-z0-9]/.test(p)) s++
  return Math.min(s, 4)
}

const strengthColors = ['var(--error)', 'var(--warning)', 'var(--info)', 'var(--success)']
const strengthLabels = ['weakPassword', 'fairPassword', 'strongPassword', 'veryStrongPassword']

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '12px 14px', border: '1px solid var(--border)',
  background: 'var(--bg)', color: 'var(--text)', borderRadius: 11,
  fontSize: 14, outline: 'none', transition: 'border-color .15s',
}

export default function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { setTokens, setPreferences } = useAuthStore()
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [shake, setShake] = useState(false)

  const score = passwordScore(password)

  const triggerShake = () => {
    setShake(true)
    setTimeout(() => setShake(false), 500)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const fn = isRegister ? register : login
      const res = await fn(username, password)
      const { access_token, username: uname, role, theme, lang } = res.data
      setTokens(access_token, uname, role)
      if (theme || lang) setPreferences(theme, lang)
      navigate(localStorage.getItem('onboarded') ? '/panel' : '/onboarding')
    } catch (err: any) {
      const msg = err.response?.data?.detail || t('errors.unknown')
      setError(msg)
      triggerShake()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-[100dvh] grid place-items-center p-6 overflow-hidden"
         style={{ background: 'var(--bg)' }}>
      {/* Arka plan efektleri (NewDesing) */}
      <div className="absolute inset-0 pointer-events-none"
           style={{ background: 'radial-gradient(circle at 50% 30%, rgba(99,102,241,.16), transparent 60%)' }} />
      <div className="absolute inset-0 pointer-events-none opacity-40 grid-bg" />
      <div className="absolute pointer-events-none"
           style={{ top: '10%', left: '12%', width: 360, height: 360, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(167,139,250,.28), transparent 70%)',
                    filter: 'blur(18px)', animation: 'floatC 16s ease-in-out infinite' }} />
      <div className="absolute pointer-events-none"
           style={{ bottom: '6%', right: '14%', width: 340, height: 340, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(99,102,241,.24), transparent 70%)',
                    filter: 'blur(18px)', animation: 'floatB 20s ease-in-out infinite' }} />

      <motion.div
        animate={shake ? { x: [0, -10, 10, -8, 8, -5, 5, 0] } : {}}
        transition={{ duration: 0.5 }}
        className="relative z-10 w-full max-w-[390px]"
        style={{ animation: 'fadeUp .6s both' }}
      >
        {/* Logo + başlık */}
        <div className="flex flex-col items-center gap-3.5 mb-7">
          <div className="logo-tile"
               style={{ width: 52, height: 52, borderRadius: 14, fontSize: 22,
                        boxShadow: '0 10px 30px -8px var(--glow)' }}>›_</div>
          <div className="text-center">
            <div className="text-[22px] font-bold" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>
              {isRegister ? t('auth.registerTitle') : t('auth.loginTitle')}
            </div>
            <div className="text-sm mt-1" style={{ color: 'var(--text-2)' }}>
              {isRegister ? t('auth.subtitleRegister') : t('auth.subtitleLogin')}
            </div>
          </div>
        </div>

        {/* Kart */}
        <div className="rounded-[18px] p-6"
             style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-lg)' }}>
          <form onSubmit={submit}>
            {/* Kullanıcı adı */}
            <label className="block text-[13px] font-medium mb-1.5" style={{ color: 'var(--text-2)' }}>
              {t('auth.username')}
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{ ...inputStyle, marginBottom: 18 }}
              onFocus={(e) => (e.target.style.borderColor = 'var(--accent)')}
              onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
              autoComplete="username"
              spellCheck={false}
              required
            />

            {/* Şifre */}
            <label className="block text-[13px] font-medium mb-1.5" style={{ color: 'var(--text-2)' }}>
              {t('auth.password')}
            </label>
            <div className="relative" style={{ marginBottom: isRegister && password ? 8 : 20 }}>
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ ...inputStyle, paddingRight: 40 }}
                onFocus={(e) => (e.target.style.borderColor = 'var(--accent)')}
                onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                required
              />
              <button type="button" onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2"
                style={{ color: 'var(--text-3)' }}>
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            {/* Şifre güç göstergesi */}
            {isRegister && password.length > 0 && (
              <div className="mb-4">
                <div className="flex gap-1">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="flex-1 h-1 rounded-full transition-colors"
                         style={{ background: i < score ? strengthColors[score - 1] : 'var(--border)' }} />
                  ))}
                </div>
                <p className="text-xs mt-1" style={{ color: strengthColors[score - 1] || 'var(--text-3)' }}>
                  {score > 0 ? t(`auth.${strengthLabels[score - 1]}`) : ''}
                </p>
              </div>
            )}

            {/* Hata */}
            <AnimatePresence>
              {error && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="text-sm px-3 py-2 rounded-lg mb-3"
                  style={{ background: 'color-mix(in srgb, var(--error) 12%, transparent)',
                           color: 'var(--error)' }}>
                  {error}
                </motion.p>
              )}
            </AnimatePresence>

            {/* Submit */}
            <button type="submit" disabled={loading}
              className="w-full font-semibold text-[15px] transition-all hover:brightness-110 disabled:opacity-60"
              style={{ padding: 13, border: 'none', background: 'var(--grad)', color: '#fff',
                       borderRadius: 12, cursor: 'pointer', boxShadow: '0 10px 28px -10px var(--glow)' }}>
              {loading ? (isRegister ? t('auth.registering') : t('auth.loggingIn'))
                       : (isRegister ? t('auth.register') : t('auth.login'))}
            </button>
          </form>
        </div>

        {/* Geçiş linki */}
        <p className="text-center text-[12.5px] mt-5" style={{ color: 'var(--text-3)' }}>
          <button onClick={() => { setIsRegister(!isRegister); setError('') }}
            className="hover:underline" style={{ color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>
            {isRegister ? t('auth.switchToLogin') : t('auth.switchToRegister')}
          </button>
        </p>
      </motion.div>
    </div>
  )
}
