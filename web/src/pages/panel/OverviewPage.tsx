import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MessageSquare, Cpu, Server, KeyRound, FileText } from 'lucide-react'
import { api } from '../../api/client'
import { useAuthStore } from '../../store/authStore'

// "Genel Bakış" — NewDesing dashboard ekranının 1:1 karşılığı, gerçek backend verisiyle.
// Admin: KPI + yüklü modeller + son etkinlik (gerçek /admin/stats, /models/admin/status, /admin/audit).
// Üye: admin-only uçlara istek atmadan basit kısayol kartları.
export default function OverviewPage() {
  const navigate = useNavigate()
  const role = useAuthStore((s) => s.role)
  const isAdmin = role === 'admin'

  const statsQ = useQuery({
    queryKey: ['admin', 'stats'],
    queryFn: () => api.get('/api/v2/admin/stats').then((r) => r.data),
    enabled: isAdmin,
    refetchInterval: 30000,
  })
  const statusQ = useQuery({
    queryKey: ['admin', 'ollama-status'],
    queryFn: () => api.get('/api/v2/models/admin/status').then((r) => r.data),
    enabled: isAdmin,
    refetchInterval: 10000,
  })
  const auditQ = useQuery({
    queryKey: ['admin', 'audit', 'overview'],
    queryFn: () => api.get('/api/v2/admin/audit', { params: { limit: 5 } }).then((r) => r.data),
    enabled: isAdmin,
  })

  if (!isAdmin) return <MemberOverview navigate={navigate} />

  const { totals, activity } = statsQ.data ?? {}
  const installed: any[] = statusQ.data?.installed ?? []
  const running: any[] = statusQ.data?.running ?? []
  const runningNames = new Set(running.map((m: any) => m.name))
  const logs: any[] = auditQ.data?.logs ?? []

  const kpis = [
    { label: 'Toplam kullanıcı', value: totals?.users ?? '—' },
    { label: 'Toplam sohbet', value: totals?.chats ?? '—' },
    { label: 'Toplam mesaj', value: totals?.messages ?? '—' },
    { label: 'Son 24 saat mesaj', value: activity?.messages_24h ?? '—' },
  ]

  return (
    <div className="flex flex-col gap-5" style={{ animation: 'fadeUp .4s both' }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpis.map((s) => (
          <Card key={s.label}>
            <div className="text-[12.5px] font-medium" style={{ color: 'var(--text-3)' }}>{s.label}</div>
            <div className="text-2xl font-bold my-2" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>{s.value}</div>
          </Card>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <div className="flex justify-between items-center mb-3.5">
            <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>Yüklü modeller</div>
            <button onClick={() => navigate('/admin/models')}
              className="text-[13px]" style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
              Tümü →
            </button>
          </div>
          <div className="flex flex-col gap-1">
            {installed.length === 0 && <p className="text-sm" style={{ color: 'var(--text-3)' }}>Henüz model indirilmemiş.</p>}
            {installed.slice(0, 5).map((m: any) => (
              <div key={m.name} className="flex items-center gap-3 px-2 py-2.5 rounded-[9px]">
                <span data-dot={runningNames.has(m.name) ? 'active' : 'idle'} />
                <div className="flex-1 min-w-0 text-[13.5px] font-medium truncate" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{m.name}</div>
                <div className="text-xs" style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                  {(m.size / 1e9).toFixed(1)} GB
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="flex justify-between items-center mb-3.5">
            <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>Son etkinlik</div>
            <button onClick={() => navigate('/admin/audit')}
              className="text-[13px]" style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
              Loglar →
            </button>
          </div>
          <div className="flex flex-col gap-2.5">
            {logs.length === 0 && <p className="text-sm" style={{ color: 'var(--text-3)' }}>Henüz kayıt yok.</p>}
            {logs.map((l: any) => (
              <div key={l.id} className="flex gap-2.5 items-baseline text-[13px]">
                <span className="shrink-0 text-[11.5px]" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>
                  {l.ts ? new Date(l.ts).toLocaleTimeString('tr-TR') : '—'}
                </span>
                <span style={{ color: 'var(--text-2)', lineHeight: 1.4 }}>{l.action}{l.username ? ` · ${l.username}` : ''}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[14px] p-5" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
      {children}
    </div>
  )
}

function MemberOverview({ navigate }: { navigate: (p: string) => void }) {
  const shortcuts = [
    { icon: MessageSquare, label: 'Sohbet', desc: 'Yerel modelinle konuş', path: '/chat' },
    { icon: Cpu, label: 'Modeller', desc: 'Kullanılabilir modelleri gör', path: '/admin/models' },
    { icon: Server, label: 'MCP Server', desc: 'Bağlantı ve araçlar', path: '/mcp' },
    { icon: KeyRound, label: 'API Anahtarları', desc: 'Programatik erişim', path: '/apikeys' },
    { icon: FileText, label: 'Dokümantasyon', desc: 'Kurulum ve kullanım', path: '/docs' },
  ]
  return (
    <div style={{ animation: 'fadeUp .4s both' }}>
      <p className="text-sm mb-5" style={{ color: 'var(--text-2)' }}>
        Hoş geldin. Aşağıdan hızlıca başla.
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {shortcuts.map((s) => (
          <button key={s.label} onClick={() => navigate(s.path)}
            className="text-left rounded-[14px] p-5 transition-colors hover:bg-[var(--surface-2)]"
            style={{ border: '1px solid var(--border)', background: 'var(--surface)', cursor: 'pointer' }}>
            <s.icon size={20} style={{ color: 'var(--accent)' }} />
            <div className="text-[15px] font-semibold mt-3" style={{ color: 'var(--text)' }}>{s.label}</div>
            <div className="text-[13px] mt-1" style={{ color: 'var(--text-3)' }}>{s.desc}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
