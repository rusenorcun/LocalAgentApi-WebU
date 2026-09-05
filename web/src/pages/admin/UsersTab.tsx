import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Unlock, Shield, ShieldOff, Trash2, LogOut } from 'lucide-react'
import { api } from '../../api/client'

export default function UsersTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => api.get('/api/v2/admin/users').then(r => r.data),
  })

  const unlock = useMutation({
    mutationFn: (id: number) => api.post(`/api/v2/admin/users/${id}/unlock`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })
  const setRole = useMutation({
    mutationFn: ({ id, role }: { id: number, role: string }) =>
      api.patch(`/api/v2/admin/users/${id}/role`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })
  const revokeSessions = useMutation({
    mutationFn: (id: number) => api.delete(`/api/v2/admin/users/${id}/sessions`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })
  const deleteUser = useMutation({
    mutationFn: (id: number) => api.delete(`/api/v2/admin/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })

  if (isLoading) return <Spinner />

  const users: any[] = data?.users ?? []

  return (
    <div>
      <h1 className="text-xl font-bold mb-6" style={{ color: 'var(--text)' }}>Kullanıcılar</h1>
      {/* Mobilde tablo geniş — yalnızca bu kutu içinde yatay kaydırılsın, sayfanın tamamı değil. */}
      <div className="rounded-2xl overflow-x-auto" style={{ border: '1px solid var(--border)' }}>
        <table className="w-full text-sm" style={{ minWidth: 640 }}>
          <thead>
            <tr style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }}>
              {['Kullanıcı', 'Rol', 'Oturumlar', 'Son giriş', 'Durum', 'İşlemler'].map(h => (
                <th key={h} className="text-left px-4 py-3 font-semibold" style={{ color: 'var(--text-2)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={u.id} style={{
                borderTop: i > 0 ? '1px solid var(--border)' : undefined,
                background: 'var(--surface)',
              }}>
                <td className="px-4 py-3 font-medium" style={{ color: 'var(--text)' }}>{u.username}</td>
                <td className="px-4 py-3">
                  <RoleBadge role={u.role} />
                </td>
                <td className="px-4 py-3" style={{ color: 'var(--text-2)' }}>{u.active_sessions}</td>
                <td className="px-4 py-3 text-xs" style={{ color: 'var(--text-3)' }}>
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString('tr') : '—'}
                </td>
                <td className="px-4 py-3">
                  {u.locked_until && new Date(u.locked_until) > new Date()
                    ? <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'color-mix(in srgb, var(--error) 15%, transparent)', color: 'var(--error)' }}>Kilitli</span>
                    : <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'color-mix(in srgb, var(--success) 15%, transparent)', color: 'var(--success)' }}>Aktif</span>
                  }
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    {u.locked_until && new Date(u.locked_until) > new Date() ? (
                      <ActionBtn icon={<Unlock size={14} />} title="Kilidi Aç" onClick={() => unlock.mutate(u.id)} />
                    ) : null}
                    {u.role === 'admin'
                      ? <ActionBtn icon={<ShieldOff size={14} />} title="Admin'den Al" onClick={() => setRole.mutate({ id: u.id, role: 'user' })} />
                      : <ActionBtn icon={<Shield size={14} />} title="Admin Yap" onClick={() => setRole.mutate({ id: u.id, role: 'admin' })} />
                    }
                    <ActionBtn icon={<LogOut size={14} />} title="Oturumları Kapat" onClick={() => revokeSessions.mutate(u.id)} />
                    <ActionBtn icon={<Trash2 size={14} />} title="Sil" danger onClick={() => {
                      if (confirm(`"${u.username}" silinsin mi?`)) deleteUser.mutate(u.id)
                    }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span className="text-xs px-2 py-0.5 rounded-full font-medium"
      style={{
        background: role === 'admin' ? 'color-mix(in srgb, var(--accent) 15%, transparent)' : 'var(--surface-2)',
        color: role === 'admin' ? 'var(--accent)' : 'var(--text-2)',
      }}>
      {role === 'admin' ? 'Admin' : 'Kullanıcı'}
    </span>
  )
}

function ActionBtn({ icon, title, onClick, danger }: { icon: React.ReactNode, title: string, onClick: () => void, danger?: boolean }) {
  return (
    <button onClick={onClick} title={title}
      className="p-1.5 rounded-lg transition-colors hover:bg-[var(--surface-2)]"
      style={{ color: danger ? 'var(--error)' : 'var(--text-3)' }}>
      {icon}
    </button>
  )
}

function Spinner() {
  return <div className="flex items-center justify-center h-32" style={{ color: 'var(--text-3)' }}>Yükleniyor…</div>
}
