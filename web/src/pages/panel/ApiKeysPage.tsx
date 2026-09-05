import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Copy, Check, Trash2, RotateCcw, Plus, Edit2, Globe, RefreshCw, Server } from 'lucide-react'
import {
  listApiKeys, createApiKey, updateApiKey, deleteApiKey,
  type ApiKey,
} from '../../api/apiKeys'
import {
  listOllamaConnections, createOllamaConnection, updateOllamaConnection,
  deleteOllamaConnection, testOllamaConnection,
  type OllamaConnection, type OllamaConnectionCreate,
} from '../../api/ollamaConnections'
import { useAuthStore } from '../../store/authStore'

export default function ApiKeysPage() {
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const [newScopes, setNewScopes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [justCreated, setJustCreated] = useState<ApiKey | null>(null)
  const [copiedId, setCopiedId] = useState<number | null>(null)

  const q = useQuery({ queryKey: ['api-keys'], queryFn: listApiKeys })
  const keys = q.data ?? []

  const invalidate = () => qc.invalidateQueries({ queryKey: ['api-keys'] })

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!newName.trim()) {
      setError('Anahtar adı gerekli.')
      return
    }
    try {
      const created = await createApiKey({ name: newName.trim(), scopes: newScopes.trim() })
      setNewName('')
      setNewScopes('')
      if (created.key) {
        setJustCreated(created)
      }
      invalidate()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Anahtar oluşturulamadı.')
    }
  }

  const revoke = async (id: number, revoked: boolean) => {
    try {
      await updateApiKey(id, { revoked })
      invalidate()
    } catch {
      /* sessiz */
    }
  }

  const remove = async (id: number) => {
    if (!confirm('Bu anahtarı silmek istediğinize emin misiniz?')) return
    try {
      await deleteApiKey(id)
      invalidate()
    } catch {
      /* sessiz */
    }
  }

  const copyKey = async (text: string, id: number) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1600)
    } catch { /* sessiz */ }
  }

  return (
    <div className="max-w-[820px]" style={{ animation: 'fadeUp .4s both' }}>
      <OllamaConnectionsCard />

      <Card className="mt-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl grid place-items-center" style={{ background: 'var(--accent-soft)' }}>
            <KeyRound size={20} style={{ color: 'var(--accent)' }} />
          </div>
          <div>
            <div className="text-[16px] font-semibold" style={{ color: 'var(--text)' }}>API anahtarları</div>
            <div className="text-xs" style={{ color: 'var(--text-3)' }}>
              Programatik erişim için kişisel anahtarlarını yönet. Aider, MCP istemcileri veya özel betiklerde kullanılabilir.
            </div>
          </div>
        </div>

        <form onSubmit={create} className="p-3 rounded-[10px] mb-4" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 mb-2.5">
            <input value={newName} onChange={(e) => setNewName(e.target.value)}
              placeholder="Anahtar adı (örn. linux-mint-aider)"
              className="sm:col-span-1 rounded-lg px-3 py-2 text-[13px] bg-transparent outline-none"
              style={{ border: '1px solid var(--border)', color: 'var(--text)' }} />
            <input value={newScopes} onChange={(e) => setNewScopes(e.target.value)}
              placeholder="Kapsam: boş=tam, read, write (virgülle)"
              className="sm:col-span-2 rounded-lg px-3 py-2 text-[13px] bg-transparent outline-none"
              style={{ border: '1px solid var(--border)', color: 'var(--text)' }} />
          </div>
          {error && <p className="text-[12px] mb-2" style={{ color: 'var(--danger, #e5484d)' }}>{error}</p>}
          <button type="submit"
            className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[12.5px] font-medium"
            style={{ border: '1px solid var(--accent)', color: 'var(--accent)', background: 'transparent', cursor: 'pointer' }}>
            <Plus size={14} /> Yeni anahtar oluştur
          </button>
        </form>

        <div className="flex flex-col">
          {keys.map((k, i) => (
            <div key={k.id} className="py-3" style={{ borderTop: i > 0 ? '1px solid var(--border-2)' : undefined }}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <div className="text-[13.5px] font-medium" style={{ color: 'var(--text)' }}>{k.name}</div>
                  {k.revoked ? <Badge tone="warn">askıya alındı</Badge> : <Badge tone="good">aktif</Badge>}
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => revoke(k.id, !k.revoked)} title={k.revoked ? 'Aktif et' : 'Askıya al'}
                    className="p-1.5 rounded-lg" style={{ border: 'none', background: 'var(--bg)', color: 'var(--text-2)', cursor: 'pointer' }}>
                    <RotateCcw size={14} />
                  </button>
                  <button onClick={() => remove(k.id)} title="Sil"
                    className="p-1.5 rounded-lg" style={{ border: 'none', background: 'var(--bg)', color: 'var(--danger, #e5484d)', cursor: 'pointer' }}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <div className="text-[11px] mb-2" style={{ color: 'var(--text-3)' }}>
                Kapsam: <span style={{ color: 'var(--text-2)' }}>{k.scopes || 'tam erişim'}</span> · Oluşturulma: {new Date(k.created_at).toLocaleString()}
                {k.last_used_at && <> · Son kullanım: {new Date(k.last_used_at).toLocaleString()}</>}
              </div>
              {justCreated && justCreated.id === k.id && justCreated.key && (
                <div className="p-2.5 rounded-lg mb-2" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-medium" style={{ color: 'var(--success)' }}>Anahtarı şimdi kopyala — bir daha gösterilmeyecek</span>
                    <button onClick={() => copyKey(justCreated.key!, k.id)}
                      style={{ border: 'none', background: 'none', color: copiedId === k.id ? 'var(--success)' : 'var(--text-3)', cursor: 'pointer' }}>
                      {copiedId === k.id ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                  <code className="block text-[11px] break-all" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{justCreated.key}</code>
                  <button onClick={() => setJustCreated(null)} className="text-[11px] mt-1.5"
                    style={{ border: 'none', background: 'none', color: 'var(--text-3)', cursor: 'pointer' }}>
                    Gizle
                  </button>
                </div>
              )}
            </div>
          ))}
          {keys.length === 0 && !q.isLoading && (
            <div className="text-[12.5px] py-6 text-center" style={{ color: 'var(--text-3)' }}>
              Henüz bir API anahtarın yok.
            </div>
          )}
        </div>
      </Card>

      <Card className="mt-4">
        <div className="text-[14px] font-semibold mb-2" style={{ color: 'var(--text)' }}>Aider ile kullanım</div>
        <p className="text-xs mb-2" style={{ color: 'var(--text-3)' }}>
          Yukarıda oluşturduğun kişisel anahtarı Aider'da şu şekilde kullanabilirsin:
        </p>
        <code className="block p-3 rounded-[10px] text-[12px] break-all"
              style={{ fontFamily: 'var(--font-mono)', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-2)' }}>
          aider --model openai/qwen3-coder:30b --openai-api-base https://api.rorcun.com/v1 --openai-api-key {'<ANAHTAR>'}
        </code>
      </Card>
    </div>
  )
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-[14px] p-5 ${className}`} style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
      {children}
    </div>
  )
}

function Badge({ children, tone }: { children: React.ReactNode; tone?: 'good' | 'warn' }) {
  const color = tone === 'good' ? 'var(--success)' : tone === 'warn' ? 'var(--warning, #f5a623)' : 'var(--text-2)'
  return (
    <span className="text-[11px] font-medium px-2 py-0.5 rounded-full"
          style={{ border: '1px solid var(--border)', background: 'var(--surface-2)', color }}>
      {children}
    </span>
  )
}

function OllamaConnectionsCard() {
  const isAdmin = useAuthStore((s) => s.role) === 'admin'
  const qc = useQueryClient()
  const [form, setForm] = useState<Partial<OllamaConnectionCreate>>({ enabled: true })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ['ollama-connections'],
    queryFn: listOllamaConnections,
    refetchInterval: 30000,
  })

  const conns = q.data ?? []
  const invalidate = () => qc.invalidateQueries({ queryKey: ['ollama-connections'] })

  const startEdit = (c: OllamaConnection) => {
    setEditingId(c.id)
    setForm({
      name: c.name,
      base_url: c.base_url,
      api_key: '',
      is_default: c.is_default,
      enabled: c.enabled,
      notes: c.notes ?? '',
    })
    setFormError(null)
  }

  const resetForm = () => {
    setEditingId(null)
    setForm({ enabled: true })
    setFormError(null)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (!form.name?.trim() || !form.base_url?.trim()) {
      setFormError('İsim ve URL gerekli.')
      return
    }
    if (!form.api_key?.trim()) {
      setFormError('API anahtarı zorunludur; anahtar olmadan Ollama bağlantısı başlamaz.')
      return
    }
    try {
      const body: OllamaConnectionCreate = {
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        api_key: form.api_key.trim(),
        is_default: !!form.is_default,
        enabled: form.enabled !== false,
        notes: form.notes?.trim() || undefined,
      }
      if (editingId) {
        await updateOllamaConnection(editingId, body)
      } else {
        await createOllamaConnection(body)
      }
      resetForm()
      invalidate()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setFormError(typeof detail === 'string' ? detail : 'Kaydedilemedi.')
    }
  }

  const remove = async (id: string) => {
    if (!confirm('Bu bağlantıyı silmek istediğinize emin misiniz?')) return
    try {
      await deleteOllamaConnection(id)
      invalidate()
    } catch {
      /* sessizce yut */
    }
  }

  const test = async (id: string) => {
    setTestingId(id)
    try {
      const r = await testOllamaConnection(id)
      alert(r.ok ? `${r.count} model bulundu.` : `Bağlantı hatası: ${r.error}`)
      invalidate()
    } catch {
      alert('Test isteği başarısız oldu.')
    } finally {
      setTestingId(null)
    }
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-3.5">
        <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>Ollama API bağlantıları</div>
        <Badge>{conns.length}</Badge>
      </div>
      <p className="text-xs mb-3" style={{ color: 'var(--text-3)' }}>
        MCP relay hem yerel hem kaydedilmiş uzak Ollama endpoint'lerine bağlanabilir.
        Uzak bağlantılar api.rorcun.com/ollama/&lt;id&gt; güvenli proxy'sinden geçer.
        Her uzak bağlantı için bir API anahtarı zorunludur; anahtar olmadan Ollama'ya bağlantı hiç başlamaz.
        Aider ile vibe coding için <code>https://api.rorcun.com/v1</code> OpenAI-compatible endpoint'ini kullanın.
      </p>

      {isAdmin && (
        <form onSubmit={submit} className="mb-4 p-3 rounded-[10px]" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-2.5">
            <input value={form.name ?? ''} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Bağlantı adı" disabled={!isAdmin}
              className="rounded-lg px-3 py-2 text-[13px] bg-transparent outline-none"
              style={{ border: '1px solid var(--border)', color: 'var(--text)' }} />
            <input value={form.base_url ?? ''} onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              placeholder="https://ollama.ornek.com" disabled={!isAdmin}
              className="rounded-lg px-3 py-2 text-[13px] bg-transparent outline-none"
              style={{ border: '1px solid var(--border)', color: 'var(--text)' }} />
            <input value={form.api_key ?? ''} onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              type="password" placeholder="API anahtarı *" disabled={!isAdmin} required
              className="rounded-lg px-3 py-2 text-[13px] bg-transparent outline-none"
              style={{ border: '1px solid var(--border)', color: 'var(--text)' }} />
            <input value={form.notes ?? ''} onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Not" disabled={!isAdmin}
              className="rounded-lg px-3 py-2 text-[13px] bg-transparent outline-none"
              style={{ border: '1px solid var(--border)', color: 'var(--text)' }} />
          </div>
          <div className="flex items-center gap-4 mb-2.5">
            <label className="flex items-center gap-2 text-[12.5px]" style={{ color: 'var(--text-2)' }}>
              <input type="checkbox" checked={!!form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                disabled={!isAdmin} />
              Varsayılan
            </label>
            <label className="flex items-center gap-2 text-[12.5px]" style={{ color: 'var(--text-2)' }}>
              <input type="checkbox" checked={form.enabled !== false}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                disabled={!isAdmin} />
              Aktif
            </label>
          </div>
          {formError && <p className="text-[12px] mb-2" style={{ color: 'var(--danger, #e5484d)' }}>{formError}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={!isAdmin}
              className="rounded-full px-4 py-1.5 text-[12.5px] font-medium"
              style={{ border: '1px solid var(--accent)', color: 'var(--accent)', background: 'transparent', cursor: 'pointer' }}>
              {editingId ? 'Güncelle' : 'Ekle'}
            </button>
            {editingId && (
              <button type="button" onClick={resetForm}
                className="rounded-full px-4 py-1.5 text-[12.5px] font-medium"
                style={{ border: '1px solid var(--border)', color: 'var(--text-2)', background: 'transparent', cursor: 'pointer' }}>
                İptal
              </button>
            )}
          </div>
        </form>
      )}

      <div className="flex flex-col">
        {conns.map((c, i) => (
          <div key={c.id} className="flex items-start gap-3 py-3"
               style={{ borderTop: i > 0 ? '1px solid var(--border-2)' : undefined }}>
            {c.is_local ? <Server size={15} style={{ color: 'var(--text-3)', marginTop: 2 }} />
                         : <Globe size={15} style={{ color: c.is_https ? 'var(--success)' : 'var(--warning, #f5a623)', marginTop: 2 }} />}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <div className="text-[13.5px] font-medium" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{c.name}</div>
                {c.is_default && <Badge tone="good">varsayılan</Badge>}
                {!c.enabled && <Badge tone="warn">kapalı</Badge>}
                {!c.is_local && !c.is_https && <Badge tone="warn">http</Badge>}
              </div>
              <div className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-3)' }}>{c.base_url}</div>
              {!c.is_local && (
                <div className="text-[11px] mt-0.5 truncate" style={{ color: 'var(--text-3)' }}>
                  proxy: <code style={{ fontFamily: 'var(--font-mono)' }}>{c.proxy_url}</code>
                </div>
              )}
              {c.last_seen_ok && (
                <div className="text-[11px] mt-0.5" style={{ color: 'var(--success)' }}>Son başarılı bağlantı: {new Date(c.last_seen_ok).toLocaleString()}</div>
              )}
              {c.models.length > 0 && (
                <div className="text-[11px] mt-1 truncate" style={{ color: 'var(--text-3)' }}>{c.models.length} model: {c.models.slice(0, 4).join(', ')}{c.models.length > 4 ? ' …' : ''}</div>
              )}
              {!c.is_local && c.models.length > 0 && (
                <AiderHint connection={c} />
              )}
            </div>
            {isAdmin && (
              <div className="flex items-center gap-1">
                <button onClick={() => test(c.id)} disabled={testingId === c.id || c.is_local}
                  title={c.is_local ? 'Yerel bağlantıyı test etmek için MCP sağlık durumunu kullanın' : 'Test et'}
                  className="p-1.5 rounded-lg transition-opacity disabled:opacity-40"
                  style={{ border: 'none', background: 'var(--bg)', color: 'var(--text-2)', cursor: 'pointer' }}>
                  {testingId === c.id ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                </button>
                {!c.is_local && (
                  <>
                    <button onClick={() => startEdit(c)}
                      className="p-1.5 rounded-lg" style={{ border: 'none', background: 'var(--bg)', color: 'var(--text-2)', cursor: 'pointer' }}>
                      <Edit2 size={14} />
                    </button>
                    <button onClick={() => remove(c.id)}
                      className="p-1.5 rounded-lg" style={{ border: 'none', background: 'var(--bg)', color: 'var(--danger, #e5484d)', cursor: 'pointer' }}>
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
        {conns.length === 0 && !q.isLoading && (
          <div className="text-[12.5px] py-3" style={{ color: 'var(--text-3)' }}>Henüz bağlantı yok.</div>
        )}
      </div>
    </Card>
  )
}

function AiderHint({ connection }: { connection: OllamaConnection }) {
  const [copied, setCopied] = useState(false)
  const firstModel = connection.models[0] || 'qwen3-coder:30b'
  const cmd = `aider --model openai/${firstModel} --api-base https://api.rorcun.com/v1 --api-key ${connection.api_key_masked || '<API_ANAHTARI>'}`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch { /* sessiz */ }
  }

  return (
    <div className="mt-2 p-2.5 rounded-lg" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between mb-1">
        <div className="text-[11px] font-medium" style={{ color: 'var(--text-2)' }}>Aider örneği</div>
        <button onClick={copy} title="Kopyala" style={{ border: 'none', background: 'none', color: copied ? 'var(--success)' : 'var(--text-3)', cursor: 'pointer' }}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
      </div>
      <code className="block text-[10.5px] break-all" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>{cmd}</code>
    </div>
  )
}
