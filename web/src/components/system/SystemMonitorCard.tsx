import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Activity } from 'lucide-react'
import { fetchSystemStats } from '../../api/system'

// Sistem izleci kartı: canlı kaynak kullanımı + performans.
// SystemTab'in en üstünde, /api/v2/system/stats ucundan 3 sn'de bir yenilenir.
export default function SystemMonitorCard() {
  const { t } = useTranslation()

  const q = useQuery({
    queryKey: ['system', 'stats'],
    queryFn: fetchSystemStats,
    refetchInterval: 3000,
  })

  const s = q.data
  const cpu = s?.cpu_usage
  const mem = s?.memory_usage
  const disk = s?.disk_usage

  const gaugeColor = (v?: number | null) => {
    const u = v ?? 0
    if (u > 80) return 'var(--error)'
    if (u > 60) return 'var(--warning)'
    return 'var(--success)'
  }

  const health = (() => {
    const peak = Math.max(cpu ?? 0, mem ?? 0, disk ?? 0)
    if (peak > 80) return { key: 'critical', color: 'var(--error)' }
    if (peak > 60) return { key: 'elevated', color: 'var(--warning)' }
    return { key: 'good', color: 'var(--success)' }
  })()

  const fmtUptime = (sec?: number | null) => {
    if (sec == null || sec < 0) return '—'
    const d = Math.floor(sec / 86400)
    const h = Math.floor((sec % 86400) / 3600)
    const m = Math.floor((sec % 3600) / 60)
    const sn = Math.floor(sec % 60)
    const u = (k: string) => t(`settings.monitor.up.${k}`)
    if (d > 0) return `${d}${u('day')} ${h}${u('hour')}`
    if (h > 0) return `${h}${u('hour')} ${m}${u('minute')}`
    if (m > 0) return `${m}${u('minute')}`
    return `${sn}${u('second')}`
  }

  const fmtGb = (used?: number | null, total?: number | null) =>
    used != null && total != null ? `${used.toFixed(1)} / ${total.toFixed(0)} GB` : '—'

  return (
    <div
      className="rounded-[14px] p-4 mb-6"
      style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}
    >
      {/* Başlık + durum */}
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <Activity size={16} className="flex-none text-[var(--accent)]" />
          <div className="min-w-0">
            <div className="text-[14px] font-semibold leading-tight" style={{ color: 'var(--text)' }}>
              {t('settings.monitor.title')}
            </div>
            <div className="text-[10px] truncate" style={{ color: 'var(--text-3)' }}>
              {t('settings.monitor.subtitle')}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-none">
          <span
            className="px-2 py-0.5 rounded text-[10px] font-medium whitespace-nowrap"
            style={{ background: 'var(--surface-2)', color: health.color }}
          >
            {t(`settings.monitor.status.${health.key}`)}
          </span>
          <span className="flex items-center gap-1 text-[10px] whitespace-nowrap" style={{ color: 'var(--text-3)' }}>
            <span
              className={`inline-block size-1.5 rounded-full ${q.isError ? '' : 'animate-pulse'}`}
              style={{ background: q.isError ? 'var(--error)' : 'var(--success)' }}
            />
            {t('settings.monitor.live')}
          </span>
        </div>
      </div>

      {/* Kaynak göstergeleri */}
      <div className="grid grid-cols-3 gap-3">
        <Gauge
          label={t('settings.monitor.cpu')}
          value={cpu}
          color={gaugeColor(cpu)}
          detail={s?.cpu_count ? t('settings.monitor.cores', { n: s.cpu_count }) : undefined}
        />
        <Gauge
          label={t('settings.monitor.memory')}
          value={mem}
          color={gaugeColor(mem)}
          detail={fmtGb(s?.memory_used_gb, s?.memory_total_gb)}
        />
        <Gauge
          label={t('settings.monitor.disk')}
          value={disk}
          color={gaugeColor(disk)}
          detail={fmtGb(s?.disk_used_gb, s?.disk_total_gb)}
        />
      </div>

      {/* Performans istatistikleri */}
      <div className="grid grid-cols-4 gap-2 mt-4 pt-3" style={{ borderTop: '1px solid var(--border)' }}>
        <MiniStat label={t('settings.monitor.uptime')} value={fmtUptime(s?.uptime_seconds)} />
        <MiniStat
          label={t('settings.monitor.processes')}
          value={s?.active_processes != null ? String(s.active_processes) : '—'}
        />
        <MiniStat label={t('settings.monitor.load')} value={s?.load_avg ? s.load_avg[0].toFixed(2) : '—'} />
        <MiniStat
          label={t('settings.monitor.model')}
          value={s?.running_model || t('settings.monitor.none')}
          mono
        />
      </div>

      {/* Hata durumu (son veri gösterilmeye devam eder) */}
      {q.isError && (
        <div
          className="flex items-center justify-between mt-3 pt-2 text-[11px]"
          style={{ borderTop: '1px solid var(--border)', color: 'var(--error)' }}
        >
          <span>{t('settings.monitor.error')}</span>
          <button
            onClick={() => q.refetch()}
            className="text-[11px] font-medium hover:underline"
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--error)', padding: 0 }}
          >
            {t('settings.monitor.retry')}
          </button>
        </div>
      )}
    </div>
  )
}

function Gauge({ label, value, color, detail }: {
  label: string
  value?: number | null
  color: string
  detail?: string
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>
        {label}
      </div>
      <div className="text-lg font-bold mt-1" style={{ color: 'var(--text)' }}>
        {value != null ? `${value}%` : '—'}
      </div>
      <div className="w-full h-1.5 rounded-full mt-1.5 overflow-hidden" style={{ background: 'var(--surface-2)' }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(value ?? 0, 100)}%`, background: color }}
        />
      </div>
      {detail && (
        <div className="text-[10px] mt-1 truncate" style={{ color: 'var(--text-3)' }}>
          {detail}
        </div>
      )}
    </div>
  )
}

function MiniStat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[9px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>
        {label}
      </div>
      <div
        className="text-[12px] font-medium mt-0.5 truncate"
        title={value}
        style={{ color: 'var(--text)', fontFamily: mono ? 'var(--font-mono)' : undefined }}
      >
        {value}
      </div>
    </div>
  )
}
