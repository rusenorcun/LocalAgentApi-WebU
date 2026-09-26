import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Loader2, Settings, Cpu, HardDrive, Heart } from 'lucide-react'
import { api } from '../../api/client'
import { useAuthStore } from '../../store/authStore'

export default function SystemMonitorPage() {
  const role = useAuthStore((s) => s.role)
  const isAdmin = role === 'admin'
  const qc = useQueryClient()

  const [showLoading, setShowLoading] = useState(false)
  const [loadingNotice, setLoadingNotice] = useState<{ ok: boolean; text: string } | null>(null)

  const statsQ = useQuery({
    queryKey: ['admin', 'system', 'stats'],
    queryFn: () => api.get('/api/v2/admin/system/stats').then((r) => r.data),
    enabled: isAdmin,
    refetchInterval: 3000,
  })

  const modelsQ = useQuery({
    queryKey: ['admin', 'system', 'models'],
    queryFn: () => api.get('/api/v2/admin/system/models').then((r) => r.data),
    enabled: isAdmin,
    refetchInterval: 5000,
  })

  const unloadModel = async (modelName: string) => {
    setShowLoading(true)
    setLoadingNotice(null)
    try {
      const r = await api.post<{ ok: boolean; text?: string }>(
        '/api/v2/admin/system/unload',
        { model: modelName }
      ).then((r) => r.data)
      if (r.ok) {
        setLoadingNotice({ ok: true, text: 'Model bellekten başarıyla boşaltıldı.' })
        qc.invalidateQueries({ queryKey: ['admin', 'system', 'stats'] })
        qc.invalidateQueries({ queryKey: ['admin', 'system', 'models'] })
      } else {
        setLoadingNotice({ ok: false, text: r.text || 'Bilinmeyen hata.' })
      }
    } catch (e: any) {
      setLoadingNotice({ ok: false, text: e?.response?.data?.detail || 'İşlem başarısız oldu.' })
    } finally {
      setShowLoading(false)
      setTimeout(() => setLoadingNotice(null), 5000)
    }
  }

  const reloadModel = async (modelName: string) => {
    setShowLoading(true)
    setLoadingNotice(null)
    try {
      const r = await api.post<{ ok: boolean; text?: string }>(
        '/api/v2/admin/system/reload',
        { model: modelName }
      ).then((r) => r.data)
      if (r.ok) {
        setLoadingNotice({ ok: true, text: 'Model yeniden yüklendi.' })
        qc.invalidateQueries({ queryKey: ['admin', 'system', 'stats'] })
        qc.invalidateQueries({ queryKey: ['admin', 'system', 'models'] })
      } else {
        setLoadingNotice({ ok: false, text: r.text || 'Bilinmeyen hata.' })
      }
    } catch (e: any) {
      setLoadingNotice({ ok: false, text: e?.response?.data?.detail || 'İşlem başarısız oldu.' })
    } finally {
      setShowLoading(false)
      setTimeout(() => setLoadingNotice(null), 5000)
    }
  }

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center py-12">
        <Badge tone="warn">Yönetici girişi gerekli</Badge>
      </div>
    )
  }

  if (statsQ.isLoading || modelsQ.isLoading) {
    return (
      <div className="flex flex-col items-center py-12">
        <Loader2 className="spinner-auto mr-2" size={40} />
        <span>Yükleniyor...</span>
      </div>
    )
  }

  const stats = statsQ.data ?? {}
  const models = modelsQ.data ?? []

  const gaugeColor = (usage: number) => {
    if (usage > 80) return 'var(--danger, #e5484d)'
    if (usage > 60) return 'var(--warning, #f5a623)'
    return 'var(--success, #22c55e)'
  }

  return (
    <div className="flex flex-col gap-5 max-w-[1000px]">
      {/* ── Genel Sistem İstatistikleri ───────────────────────────────── */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>Sistem İstatistikleri</div>
          <Heart size={14} className="text-[var(--accent)]" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <div className="text-[12px] font-medium" style={{ color: 'var(--text-3)' }}>CPU%</div>
            <div className="text-2xl font-bold my-2" style={{ color: 'var(--text)' }}>{stats.cpu_usage ?? '—'}%</div>
            <div className="text-[10px]" style={{ color: 'var(--text-2)' }}>
              <div className="w-full bg-[var(--surface-2)] rounded-[9px] h-2">
                <div
                  className="h-full rounded-[9px]"
                  style={{ width: stats.cpu_usage ?? 0 + '%', background: gaugeColor(stats.cpu_usage ?? 0) }}
                ></div>
              </div>
            </div>
          </div>

          <div>
            <div className="text-[12px] font-medium" style={{ color: 'var(--text-3)' }}>Memory %</div>
            <div className="text-2xl font-bold my-2" style={{ color: 'var(--text)' }}>{stats.memory_usage ?? '—'}%</div>
            <div className="text-[10px]" style={{ color: 'var(--text-2)' }}>
              <div className="w-full bg-[var(--surface-2)] rounded-[9px] h-2">
                <div
                  className="h-full rounded-[9px]"
                  style={{ width: stats.memory_usage ?? 0 + '%', background: gaugeColor(stats.memory_usage ?? 0) }}
                ></div>
              </div>
            </div>
          </div>

          <div>
            <div className="text-[12px] font-medium" style={{ color: 'var(--text-3)' }}>Disk Kullanım</div>
            <div className="text-2xl font-bold my-2" style={{ color: 'var(--text)' }}>{stats.disk_usage ?? '—'}%</div>
            <div className="text-[10px]" style={{ color: 'var(--text-2)' }}>
              <div className="w-full bg-[var(--surface-2)] rounded-[9px] h-2">
                <div
                  className="h-full rounded-[9px]"
                  style={{ width: stats.disk_usage ?? 0 + '%', background: gaugeColor(stats.disk_usage ?? 0) }}
                ></div>
              </div>
            </div>
          </div>

          <div>
            <div className="text-[12px] font-medium" style={{ color: 'var(--text-3)' }}>Aktif Process</div>
            <div className="text-2xl font-bold my-2" style={{ color: 'var(--text)' }}>{stats.active_processes ?? '—'}</div>
          </div>
        </div>
      </Card>

      {/* ── Yüklü Modeller ve Bellek Yönetimi ──────────────────────────── */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>Yüklü Modeller & Bellek</div>
          <Settings size={14} className="text-[var(--accent)] cursor-pointer" onClick={() => qc.invalidateQueries({ queryKey: ['admin', 'system', 'models'] })} />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left p-2 text-[11px] font-medium text-[var(--text-2)]">Model</th>
                <th className="text-left p-2 text-[11px] font-medium text-[var(--text-2)]">VRAM</th>
                <th className="text-left p-2 text-[11px] font-medium text-[var(--text-2)]">Durum</th>
                <th className="text-left p-2 text-[11px] font-medium text-[var(--text-2)]">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m: any, i: number) => {
                const isRunning = m.is_loading || m.name === (stats.running_model || '')
                const size_gb = (m.size / 1e9).toFixed(1)
                const vram_used = m.vram_used || 0
                const vram_total = m.vram_total || 0
                const pct = vram_total > 0 ? Math.round((vram_used / vram_total) * 100) : 0
                const isBig = (m.size || 0) >= 10 * 1e9

                return (
                  <tr key={i} className="border-b border-border">
                    <td className="p-2">
                      <div className="font-medium" style={{ fontFamily: 'var(--font-mono)' }}>{m.name}</div>
                      <div className="text-[10px] text-[var(--text-3)]">({size_gb} GB)</div>
                    </td>
                    <td className="p-2">
                      <div className="text-[12px] font-medium" style={{ fontFamily: 'var(--font-mono)' }}>
                        {vram_used > 0 ? `${(vram_used / 1e6).toFixed(1)} MB` : '—'}
                      </div>
                      {vram_total > 0 && (
                        <div className="text-[10px] text-[var(--text-3)]">Toplam: {(vram_total / 1e6).toFixed(1)} MB</div>
                      )}
                    </td>
                    <td className="p-2">
                      <span className={`text-[10px] font-medium px-2 rounded`} style={{
                        background: pct > 80 ? 'var(--surface-2)' : pct > 50 ? 'var(--warning-color)' : 'var(--surface-1)',
                        color: pct > 80 ? 'var(--danger)' : pct > 50 ? 'var(--warning)' : 'var(--success)'
                      }}>
                        {isRunning && 'ÇALIŞIYOR'}{!isRunning && 'DURDAKI'}
                      </span>
                    </td>
                    <td className="p-2">
                      {isRunning ? (
                        <Button
                          size="icon"
                          onClick={() => unloadModel(m.name)}
                          disabled={showLoading}
                        >
                          <Loader2 className="size-4" />
                        </Button>
                      ) : (
                        <Button
                          size="icon"
                          onClick={() => reloadModel(m.name)}
                          disabled={showLoading}
                        >
                          <Loader2 className="size-4" />
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {models.length === 0 && (
                <tr>
                  <td colSpan={4} className="p-4 text-center text-[var(--text-3)]">
                    Yüklü model bulunamadı. Modeller panelden çekilebilir.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {loadingNotice && (
          <p className="mt-3 text-[12px]" style={{ color: loadingNotice.ok ? 'var(--success)' : 'var(--danger, #e5484d)' }}>
            {loadingNotice.text}
          </p>
        )}
      </Card>
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

function Badge({ children, tone }: { children: React.ReactNode; tone?: 'warn' | 'info' | 'success' | 'danger' }) {
  const colors = {
    warn: { bg: 'var(--warning-color)', color: 'var(--warning)' },
    info: { bg: 'var(--info-color)', color: 'var(--info)' },
    success: { bg: 'var(--success-color)', color: 'var(--success)' },
    danger: { bg: 'var(--danger-color)', color: 'var(--danger)' },
  }
  const c = colors[tone || 'info']
  return (
    <span className="px-2 py-0.5 rounded text-[11px] font-medium" style={{ background: c.bg, color: c.color }}>
      {children}
    </span>
  )
}

function Button({ size, onClick, children, disabled }: { size?: 'sm' | 'lg' | 'icon'; onClick?: () => void; children: React.ReactNode; disabled?: boolean }) {
  const s = size === 'icon' ? 'rounded-[9px] px-2 py-1.5 text-[11px]' : 'rounded-full px-4 py-2 text-[13px] font-medium'
  const base = 'transition-colors hover:bg-[var(--surface-2)] disabled:opacity-40'
  const color = disabled ? 'var(--text-2)' : 'var(--accent)'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-2 ${s} ${base}`}
      style={{ border: 'none', background: 'transparent', color }}
    >
      {children}
    </button>
  )
}