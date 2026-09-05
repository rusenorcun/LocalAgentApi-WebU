import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

export default function AuditTab() {
  const [action, setAction] = useState('')
  const [username, setUsername] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'audit', action, username],
    queryFn: () => api.get('/api/v2/admin/audit', {
      params: { ...(action && { action }), ...(username && { username }), limit: 100 }
    }).then(r => r.data),
  })

  const logs: any[] = data?.logs ?? []

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Audit Log</h1>
        <div className="flex flex-col sm:flex-row gap-2">
          <input value={action} onChange={e => setAction(e.target.value)} placeholder="Eylem filtrele…"
            className="px-3 py-1.5 rounded-xl text-sm outline-none w-full sm:w-[180px]"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }} />
          <input value={username} onChange={e => setUsername(e.target.value)} placeholder="Kullanıcı filtrele…"
            className="px-3 py-1.5 rounded-xl text-sm outline-none w-full sm:w-[180px]"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)' }} />
        </div>
      </div>

      {isLoading ? <Spinner /> : (
        <div className="rounded-2xl overflow-x-auto" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full text-xs" style={{ minWidth: 560 }}>
            <thead>
              <tr style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }}>
                {['Zaman', 'Kullanıcı', 'IP', 'Eylem', 'Detay'].map(h => (
                  <th key={h} className="text-left px-4 py-3 font-semibold" style={{ color: 'var(--text-2)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map((l, i) => (
                <tr key={l.id} style={{ borderTop: i > 0 ? '1px solid var(--border)' : undefined, background: 'var(--surface)' }}>
                  <td className="px-4 py-2.5 whitespace-nowrap" style={{ color: 'var(--text-3)' }}>
                    {l.ts ? new Date(l.ts).toLocaleString('tr') : '—'}
                  </td>
                  <td className="px-4 py-2.5 font-medium" style={{ color: 'var(--text)' }}>{l.username || '—'}</td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--text-3)' }}>{l.ip || '—'}</td>
                  <td className="px-4 py-2.5">
                    <span className="px-1.5 py-0.5 rounded-full font-mono"
                      style={{ background: 'var(--surface-2)', color: actionColor(l.action) }}>
                      {l.action}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 max-w-xs truncate" style={{ color: 'var(--text-2)' }}>{l.detail || '—'}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr><td colSpan={5} className="text-center py-8" style={{ color: 'var(--text-3)' }}>Kayıt yok</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function actionColor(action: string): string {
  if (action?.includes('fail') || action?.includes('error') || action?.includes('delete')) return 'var(--error)'
  if (action?.includes('login') || action?.includes('register')) return 'var(--success)'
  if (action?.includes('admin')) return 'var(--warning)'
  return 'var(--text-2)'
}

function Spinner() {
  return <div className="flex items-center justify-center h-32" style={{ color: 'var(--text-3)' }}>Yükleniyor…</div>
}
