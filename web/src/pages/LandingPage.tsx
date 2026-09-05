import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTheme } from '../hooks/useTheme'

// Web sitesinin ana sayfası: doğrudan sohbet penceresi DEĞİL — tanıtım + Panel/Dokümantasyon
// ayrımı yapan bir giriş sayfası (NewDesing "landing" ekranı, 1:1).
export default function LandingPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { theme, setTheme } = useTheme()
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)

  return (
    <div className="relative min-h-[100dvh] flex flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      {/* Arka plan efektleri */}
      <div className="absolute inset-0 pointer-events-none"
           style={{ background: 'radial-gradient(circle at 50% 0%, rgba(99,102,241,.14), transparent 60%)' }} />
      <div className="absolute inset-0 pointer-events-none opacity-40 grid-bg" />
      <div className="absolute pointer-events-none"
           style={{ top: -120, left: -80, width: 420, height: 420, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(167,139,250,.35), transparent 70%)',
                    filter: 'blur(20px)', animation: 'floatA 14s ease-in-out infinite' }} />
      <div className="absolute pointer-events-none"
           style={{ bottom: -160, right: -60, width: 480, height: 480, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(99,102,241,.3), transparent 70%)',
                    filter: 'blur(20px)', animation: 'floatB 18s ease-in-out infinite' }} />

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-6 md:px-10 py-6">
        <div className="flex items-center gap-3" style={{ animation: 'fadeUp .6s both' }}>
          <span className="logo-tile" style={{ width: 34, height: 34, fontSize: 15 }}>›_</span>
          <span className="font-bold text-[19px]" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>
            {t('app.appName')}
          </span>
        </div>
        <div className="flex items-center gap-2.5" style={{ animation: 'fadeUp .6s .1s both' }}>
          <button
            onClick={() => setTheme(isDark ? 'light' : 'dark')}
            title="Tema"
            className="w-[38px] h-[38px] grid place-items-center rounded-[10px] transition-opacity hover:opacity-80"
            style={{ border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-2)', cursor: 'pointer' }}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
              <path d="M20 14a8 8 0 1 1-9-9 6 6 0 0 0 9 9z" />
            </svg>
          </button>
          <button
            onClick={() => navigate('/login')}
            className="px-[18px] py-[9px] rounded-[10px] font-medium text-sm transition-opacity hover:opacity-90"
            style={{ border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer' }}>
            {t('auth.login')}
          </button>
        </div>
      </header>

      {/* Hero */}
      <main className="relative z-10 flex-1 grid md:grid-cols-2 gap-14 items-center max-w-[1180px] mx-auto px-6 md:px-10 py-5 md:py-14 w-full">
        <div>
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[12.5px] font-medium mb-6"
               style={{ border: '1px solid var(--border)', background: 'var(--accent-soft)', color: 'var(--accent)', animation: 'fadeUp .6s .1s both' }}>
            <span data-dot="active" /> {t('chat.welcome.badge')}
          </div>
          <h1 className="font-bold mb-5 text-[38px] md:text-[56px]"
              style={{ color: 'var(--text)', lineHeight: 1.04, letterSpacing: '-.03em', animation: 'fadeUp .6s .2s both' }}>
            Yerel LLM'lerin ve<br /><span className="grad-text">MCP sunucun</span> için<br />tek kontrol paneli.
          </h1>
          <p className="text-[17px] mb-8 max-w-[440px]" style={{ color: 'var(--text-2)', lineHeight: 1.6, animation: 'fadeUp .6s .3s both' }}>
            Modelleri yönet, MCP araçlarını bağla, arkadaşlarınla paylaş ve her isteği izle — hepsi kendi makinende çalışırken.
          </p>
          <div className="flex flex-wrap gap-3 mb-11" style={{ animation: 'fadeUp .6s .4s both' }}>
            <button onClick={() => navigate('/panel')}
              className="px-[26px] py-[13px] rounded-xl font-semibold text-[15px] transition-all hover:brightness-110 hover:-translate-y-px"
              style={{ border: 'none', background: 'var(--grad)', color: '#fff', cursor: 'pointer', boxShadow: '0 10px 30px -10px var(--glow)' }}>
              Panele gir →
            </button>
            <button onClick={() => navigate('/docs')}
              className="px-6 py-[13px] rounded-xl font-medium text-[15px] transition-opacity hover:opacity-90"
              style={{ border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer' }}>
              Dokümantasyon
            </button>
          </div>
          <div className="flex gap-7" style={{ animation: 'fadeUp .6s .5s both' }}>
            <Stat value="6" label="MCP aracı" />
            <div className="w-px" style={{ background: 'var(--border)' }} />
            <Stat value="4" label="yerel model" />
            <div className="w-px" style={{ background: 'var(--border)' }} />
            <Stat value="100%" label="senin verinde" />
          </div>
        </div>

        <div style={{ animation: 'fadeUp .7s .35s both' }}>
          <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--border)', background: 'linear-gradient(180deg, var(--surface), var(--bg))', boxShadow: 'var(--shadow-lg)' }}>
            <div className="flex items-center gap-2 px-4 py-3.5" style={{ borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
              <span className="w-[11px] h-[11px] rounded-full" style={{ background: '#f87171' }} />
              <span className="w-[11px] h-[11px] rounded-full" style={{ background: '#fbbf24' }} />
              <span className="w-[11px] h-[11px] rounded-full" style={{ background: '#34d399' }} />
              <span className="ml-2 text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>localagent — mcp</span>
            </div>
            <div className="p-5 text-[13px]" style={{ fontFamily: 'var(--font-mono)', lineHeight: 2, color: 'var(--text-2)' }}>
              <div style={{ animation: 'fadeIn .3s .8s both' }}><span style={{ color: 'var(--accent)' }}>›</span> localagent serve --mcp</div>
              <div style={{ animation: 'fadeIn .3s 1.3s both' }}><span style={{ color: 'var(--success)' }}>✓</span> MCP sunucusu ayakta</div>
              <div style={{ animation: 'fadeIn .3s 1.8s both' }}><span style={{ color: 'var(--success)' }}>✓</span> yerel model yüklendi</div>
              <div style={{ animation: 'fadeIn .3s 2.3s both' }}><span style={{ color: 'var(--info)' }}>→</span> araçlar kayıtlı: genel_sohbet, kod_yaz…</div>
              <div style={{ animation: 'fadeIn .3s 2.8s both' }}>
                <span style={{ color: 'var(--accent)' }}>›</span> hazır
                <span className="inline-block w-[9px] h-4 ml-1 align-[-3px]" style={{ background: 'var(--accent)', animation: 'blink 1s step-end infinite' }} />
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer className="relative z-10 text-center py-5 text-[13px]" style={{ color: 'var(--text-3)', borderTop: '1px solid var(--border-2)' }}>
        {t('app.appName')} · yalnızca davetli erişim
      </footer>
    </div>
  )
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="font-bold text-2xl" style={{ color: 'var(--text)' }}>{value}</div>
      <div className="text-[13px]" style={{ color: 'var(--text-3)' }}>{label}</div>
    </div>
  )
}
