import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff } from 'lucide-react'
import { changePassword } from '../../api/auth'

// Şifre değiştir. /settings/password
export default function PasswordTab() {
  const { t } = useTranslation()
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showCurrent, setShowCurrent] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [err, setErr] = useState('')
  const [ok, setOk] = useState(false)
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr('')
    if (newPw !== confirmPw) { setErr(t('settings.passwordMismatch')); return }
    if (newPw.length < 8) { setErr(t('settings.passwordTooShort')); return }
    setLoading(true)
    try {
      await changePassword(currentPw, newPw)
      setOk(true); setCurrentPw(''); setNewPw(''); setConfirmPw('')
      setTimeout(() => setOk(false), 2500)
    } catch (e: any) {
      setErr(e.response?.data?.detail || t('errors.unknown'))
    } finally { setLoading(false) }
  }

  const inputCls = 'w-full text-sm px-3 py-2 rounded-lg outline-none'
  const inputStyle = { background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' } as const

  return (
    <div className="max-w-md">
      <h1 className="text-xl font-bold mb-4" style={{ color: 'var(--text)' }}>{t('settings.changePassword')}</h1>
      <form onSubmit={submit} className="space-y-2.5">
        <div className="relative">
          <input type={showCurrent ? 'text' : 'password'} value={currentPw} onChange={(e) => setCurrentPw(e.target.value)}
            placeholder={t('settings.currentPassword')} required className={inputCls + ' pr-9'} style={inputStyle} />
          <button type="button" onClick={() => setShowCurrent(v => !v)} className="absolute right-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-3)' }}>
            {showCurrent ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        <div className="relative">
          <input type={showNew ? 'text' : 'password'} value={newPw} onChange={(e) => setNewPw(e.target.value)}
            placeholder={t('settings.newPassword')} required className={inputCls + ' pr-9'} style={inputStyle} />
          <button type="button" onClick={() => setShowNew(v => !v)} className="absolute right-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-3)' }}>
            {showNew ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        <input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)}
          placeholder={t('settings.confirmPassword')} required className={inputCls} style={inputStyle} />
        {err && <p className="text-xs" style={{ color: 'var(--error)' }}>{err}</p>}
        {ok && <p className="text-xs" style={{ color: 'var(--success, #10b981)' }}>{t('settings.passwordChanged')}</p>}
        <button type="submit" disabled={loading}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-opacity disabled:opacity-60 hover:opacity-90"
          style={{ background: 'var(--grad)', color: '#fff' }}>
          {loading ? '…' : t('settings.save')}
        </button>
      </form>
    </div>
  )
}
