import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, X, Check, Download, Star, PowerOff, Gauge, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAuthStore } from '../../store/authStore'

export default function ModelsTab() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<any | null>(null)
  const [adding, setAdding] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'models'],
    queryFn: () => api.get('/api/v2/models/admin').then(r => r.data),
  })

  const updateModel = useMutation({
    mutationFn: ({ id, body }: { id: number, body: any }) =>
      api.patch(`/api/v2/models/admin/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'models'] })
      qc.invalidateQueries({ queryKey: ['models'] })
      setEditing(null)
    },
  })
  const createModel = useMutation({
    mutationFn: (body: any) => api.post('/api/v2/models/admin', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'models'] })
      qc.invalidateQueries({ queryKey: ['models'] })
      setAdding(false)
    },
  })
  const deleteModel = useMutation({
    mutationFn: (id: number) => api.delete(`/api/v2/models/admin/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'models'] })
      qc.invalidateQueries({ queryKey: ['models'] })
    },
  })


  // ── Sistem / Ollama: çalışan (VRAM) + diskte yüklü + indir/sil ──
  const [pullName, setPullName] = useState('')
  const [pullStatus, setPullStatus] = useState<string | null>(null)
  const statusQ = useQuery({
    queryKey: ['admin', 'ollama-status'],
    queryFn: () => api.get('/api/v2/models/admin/status').then(r => r.data),
    refetchInterval: 5000,
  })
  const uninstall = useMutation({
    mutationFn: (name: string) => api.post('/api/v2/models/admin/uninstall', { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'ollama-status'] })
      qc.invalidateQueries({ queryKey: ['admin', 'models'] })
    },
  })
  // ── Bellekten çıkar ──
  const [unloading, setUnloading] = useState<string | null>(null)
  const [unloadNote, setUnloadNote] = useState<string | null>(null)
  const unloadModel = async (name: string) => {
    setUnloading(name)
    setUnloadNote(null)
    try {
      const r = await api.post('/api/v2/admin/system/unload', { model: name }).then(r => r.data)
      if (!r.ok) setUnloadNote(`${name}: ${r.note || 'boşaltılamadı'}`)
    } catch (e: any) {
      setUnloadNote(`${name}: ${e?.response?.data?.detail || 'istek başarısız'}`)
    } finally {
      setUnloading(null)
      qc.invalidateQueries({ queryKey: ['admin', 'ollama-status'] })
    }
  }

  // ── Hız testi (token/s) ──
  const [bench, setBench] = useState<Record<string, any>>({})
  const [benchRunning, setBenchRunning] = useState<string | null>(null)
  const runBench = async (name: string) => {
    setBenchRunning(name)
    setBench(b => ({ ...b, [name]: { pending: true } }))
    try {
      const r = await api.post('/api/v2/models/admin/benchmark', { model: name }, { timeout: 0 }).then(r => r.data)
      setBench(b => ({ ...b, [name]: r }))
    } catch (e: any) {
      setBench(b => ({ ...b, [name]: { ok: false, note: e?.response?.data?.detail || 'istek başarısız' } }))
    } finally {
      setBenchRunning(null)
      qc.invalidateQueries({ queryKey: ['admin', 'ollama-status'] })
    }
  }
  const runBenchAll = async () => {
    // Sırayla: aynı anda iki büyük model yüklenirse ölçüm bozulur.
    for (const m of (statusQ.data?.installed || [])) await runBench(m.name)
  }

  const fmtBytes = (b: number) =>
    b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b >= 1e6 ? (b / 1e6).toFixed(0) + ' MB' : (b / 1e3).toFixed(0) + ' KB'
  // accessToken artık localStorage'da değil, yalnızca store belleğinde (bkz. authStore.ts G2) —
  // canlı store'dan okunmalı, aksi halde istek daima boş token ile 401 alır.
  const _token = () => useAuthStore.getState().accessToken || ''
  const pullModel = async () => {
    const name = pullName.trim()
    if (!name) return
    setPullStatus('başlatılıyor…')
    try {
      const resp = await fetch('/api/v2/models/admin/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${_token()}` },
        body: JSON.stringify({ name }),
      })
      const reader = resp.body!.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.error) setPullStatus('Hata: ' + ev.error)
            else if (ev.total) setPullStatus(`${ev.status || 'indiriliyor'} %${Math.round((ev.completed || 0) / ev.total * 100)}`)
            else if (ev.status) setPullStatus(ev.status)
          } catch { /* yoksay */ }
        }
      }
      setPullStatus('tamamlandı ✓')
      setPullName('')
      qc.invalidateQueries({ queryKey: ['admin', 'ollama-status'] })
      setTimeout(() => setPullStatus(null), 3000)
    } catch {
      setPullStatus('Hata')
    }
  }

  if (isLoading) return <Spinner />
  const catalog: any[] = data?.catalog ?? []
  const unnamed: any[] = data?.unnamed_ollama_models ?? []

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Modeller</h1>
        <button onClick={() => setAdding(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-opacity hover:opacity-90"
          style={{ background: 'var(--grad)', color: '#fff' }}>
          <Plus size={16} /> Ekle
        </button>
      </div>

      {/* Sistem / Ollama paneli */}
      <div className="mb-6 p-4 rounded-xl border" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text)' }}>Sistem / Ollama</h2>

        <p className="text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-3)' }}>Bellekte yüklü (VRAM)</p>
        {((statusQ.data?.running) || []).length === 0 ? (
          <p className="text-xs" style={{ color: 'var(--text-3)' }}>Şu an bellekte yüklü model yok</p>
        ) : (
          (statusQ.data?.running || []).map((m: any) => (
            <div key={m.name} className="flex items-center justify-between text-xs mb-1">
              <span style={{ color: 'var(--text)' }}>{m.name}</span>
              <div className="flex items-center gap-2">
                <span style={{ color: 'var(--text-3)' }}>
                  {fmtBytes(m.size_vram)} VRAM · {fmtBytes(m.size)}
                  {m.size > 0 && m.size_vram < m.size && ` · %${Math.round(m.size_vram / m.size * 100)} GPU`}
                </span>
                <button onClick={() => unloadModel(m.name)} disabled={unloading === m.name}
                  className="flex items-center gap-1 px-2 py-0.5 rounded-md hover:bg-[var(--surface-2)] disabled:opacity-50"
                  style={{ color: 'var(--error)', border: '1px solid var(--border)' }} title="Modeli bellekten çıkar">
                  {unloading === m.name ? <Loader2 size={12} className="animate-spin" /> : <PowerOff size={12} />}
                  Bellekten çıkar
                </button>
              </div>
            </div>
          ))
        )}
        {unloadNote && <p className="text-xs mt-1" style={{ color: 'var(--error)' }}>{unloadNote}</p>}

        <p className="text-[11px] font-medium uppercase tracking-wider mt-3 mb-1" style={{ color: 'var(--text-3)' }}>Diskte yüklü</p>
        <div className="space-y-1">
          {(statusQ.data?.installed || []).map((m: any) => (
            <div key={m.name} className="flex items-center justify-between text-xs">
              <span style={{ color: 'var(--text)' }}>{m.name}</span>
              <div className="flex items-center gap-2">
                <span style={{ color: 'var(--text-3)' }}>{fmtBytes(m.size)}</span>
                <button onClick={() => runBench(m.name)} disabled={!!benchRunning}
                  className="p-1 rounded hover:bg-[var(--surface-2)] disabled:opacity-40" style={{ color: 'var(--accent)' }} title="Hız testi (token/s)">
                  {benchRunning === m.name ? <Loader2 size={12} className="animate-spin" /> : <Gauge size={12} />}
                </button>
                <button onClick={() => { if (confirm(`${m.name} diskten silinsin mi?`)) uninstall.mutate(m.name) }}
                  className="p-1 rounded hover:bg-[var(--surface-2)]" style={{ color: 'var(--error)' }} title="Sil">
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2 mt-3">
          <input value={pullName} onChange={(e) => setPullName(e.target.value)}
            placeholder="örn. qwen2.5:7b-instruct"
            className="flex-1 text-xs px-2 py-1.5 rounded-lg outline-none"
            style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }} />
          <button onClick={pullModel}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{ background: 'var(--grad)', color: '#fff' }}>
            <Download size={12} /> İndir
          </button>
        </div>
        {pullStatus && <p className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>{pullStatus}</p>}

        {/* Hız testi */}
        <div className="flex items-center justify-between mt-4 mb-1">
          <p className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>Hız testi (token/s)</p>
          <button onClick={runBenchAll} disabled={!!benchRunning}
            className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-medium disabled:opacity-50"
            style={{ border: '1px solid var(--accent)', color: 'var(--accent)' }}>
            {benchRunning ? <Loader2 size={12} className="animate-spin" /> : <Gauge size={12} />}
            {benchRunning ? `Test ediliyor: ${benchRunning}` : 'Tüm modelleri test et'}
          </button>
        </div>
        <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)' }}>
          Sabit bir istemle 256 token üretilir; hız Ollama'nın kendi sayaçlarından (eval_count / eval_duration) hesaplanır.
          Sohbetteki num_ctx ayarı kullanılır, GPU katman dağılımını Ollama yapar, model test sonrası bellekten çıkarılır. Modeller sırayla test edilir.
        </p>
        {Object.keys(bench).length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: 'var(--text-3)' }} className="text-left">
                  <th className="py-1 pr-3 font-medium">Model</th>
                  <th className="py-1 pr-3 font-medium">Üretim</th>
                  <th className="py-1 pr-3 font-medium">Prompt</th>
                  <th className="py-1 pr-3 font-medium">Yükleme</th>
                  <th className="py-1 pr-3 font-medium">Toplam</th>
                  <th className="py-1 pr-3 font-medium">GPU</th>
                  <th className="py-1 font-medium">ctx</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(bench).map(([name, r]) => (
                  <tr key={name} style={{ borderTop: '1px solid var(--border)', color: 'var(--text)' }}>
                    <td className="py-1 pr-3">{name}</td>
                    {r.pending ? (
                      <td colSpan={6} className="py-1" style={{ color: 'var(--text-3)' }}>çalışıyor…</td>
                    ) : !r.ok ? (
                      <td colSpan={6} className="py-1" style={{ color: r.skipped ? 'var(--text-3)' : 'var(--error)' }}>{r.note}</td>
                    ) : (
                      <>
                        <td className="py-1 pr-3 font-semibold">{r.gen_tps ?? '—'} t/s</td>
                        <td className="py-1 pr-3">{r.prompt_tps ?? '—'} t/s</td>
                        <td className="py-1 pr-3">{r.load_s} sn</td>
                        <td className="py-1 pr-3">{r.total_s} sn</td>
                        <td className="py-1 pr-3" style={{ color: r.gpu_pct != null && r.gpu_pct < 100 ? 'var(--warning, #f5a623)' : undefined }}>
                          {r.gpu_pct != null ? `%${r.gpu_pct}` : '—'}
                        </td>
                        <td className="py-1">{r.num_ctx}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Katalog */}
      <div className="flex flex-col gap-2 mb-8">
        {catalog.map(m => (
          editing?.id === m.id
            ? <ModelEditRow key={m.id} model={m} onSave={(body) => updateModel.mutate({ id: m.id, body })} onCancel={() => setEditing(null)} />
            : <ModelRow
                key={m.id}
                model={m}
                onSetDefault={() => updateModel.mutate({ id: m.id, body: { is_default: true } })}
                onEdit={() => setEditing(m)}
                onDelete={() => {
                  if (confirm(`${m.name_i18n?.tr || m.ollama_name} silinsin mi?`)) deleteModel.mutate(m.id)
                }}
              />
        ))}
        {adding && (
          <ModelEditRow model={null} onSave={(body) => createModel.mutate(body)} onCancel={() => setAdding(false)} />
        )}
      </div>

      {/* Ollama'da katalogda olmayan (kullanılmayanlar dahil) */}
      {unnamed.length > 0 && (
        <div>
          <p className="text-sm font-semibold mb-1" style={{ color: 'var(--text-2)' }}>
            Katalogda Olmayan Ollama Modelleri
          </p>
          <p className="text-xs mb-3" style={{ color: 'var(--text-3)' }}>
            Sohbet modeli olarak seçilemezler. "Yardımcı" işaretliler sistem tarafından
            kullanılır (özetleme/görsel betimleme/kod) — silmeyin. Diğerleri güvenle kaldırılabilir.
          </p>
          <div className="flex flex-col gap-1">
            {unnamed.map((m: any) => (
              <div key={m.ollama_name} className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl"
                style={{ border: '1px solid var(--border)' }}>
                <div className="flex items-center gap-2 min-w-0">
                  <code className="text-sm truncate" style={{ color: m.helper ? 'var(--text)' : 'var(--text-2)' }}>
                    {m.ollama_name}
                  </code>
                  {m.helper && (
                    <span className="text-[10.5px] px-1.5 py-0.5 rounded-full shrink-0"
                      style={{ background: 'color-mix(in srgb, var(--warning) 15%, transparent)', color: 'var(--warning)' }}>
                      yardımcı
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {!!m.size && <span className="text-xs" style={{ color: 'var(--text-3)' }}>{fmtBytes(m.size)}</span>}
                  <button onClick={() => setAdding(true)}
                    className="text-xs px-3 py-1 rounded-lg"
                    style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}>
                    Kataloğa Ekle
                  </button>
                  <button onClick={() => {
                      const msg = m.helper
                        ? `${m.ollama_name} bir SİSTEM YARDIMCISI — silinirse ilgili özellikler bozulur. Yine de diskten silinsin mi?`
                        : `${m.ollama_name} diskten silinsin mi?`
                      if (confirm(msg)) uninstall.mutate(m.ollama_name)
                    }}
                    className="p-1 rounded hover:bg-[var(--surface-2)]"
                    style={{ color: 'var(--error)' }} title="Diskten sil">
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ModelRow({
  model: m,
  onSetDefault,
  onEdit,
  onDelete,
}: {
  model: any
  onSetDefault: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="flex items-center gap-4 px-4 py-3 rounded-2xl"
      style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm" style={{ color: 'var(--text)' }}>
            {m.name_i18n?.tr || m.ollama_name}
          </span>
          {!m.enabled && <span className="text-xs px-1.5 py-0.5 rounded-full" style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>Kapalı</span>}
          {m.internal && <span className="text-xs px-1.5 py-0.5 rounded-full" style={{ background: 'color-mix(in srgb, var(--warning) 15%, transparent)', color: 'var(--warning)' }}>Dahili</span>}
          {m.is_default ? (
            <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium"
              style={{ background: 'color-mix(in srgb, var(--accent) 15%, transparent)', color: 'var(--accent)' }}>
              <Star size={11} fill="currentColor" /> Varsayılan
            </span>
          ) : (
            <button
              onClick={onSetDefault}
              className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border border-dashed hover:border-solid hover:bg-[var(--surface-2)] transition-all cursor-pointer opacity-70 hover:opacity-100"
              style={{ borderColor: 'var(--border)', color: 'var(--text-3)' }}
              title="Bu modeli varsayılan yap"
            >
              <Star size={10} /> Varsayılan Yap
            </button>
          )}
        </div>
        <code className="text-xs" style={{ color: 'var(--text-3)' }}>{m.ollama_name}</code>
      </div>
      <div className="flex items-center gap-1">
        {!m.is_default && (
          <button
            onClick={onSetDefault}
            className="p-1.5 rounded-lg hover:bg-[var(--surface-2)] transition-colors text-[var(--text-3)] hover:text-amber-500"
            title="Varsayılan Yap"
          >
            <Star size={14} />
          </button>
        )}
        <button onClick={onEdit} className="p-1.5 rounded-lg hover:bg-[var(--surface-2)]" style={{ color: 'var(--text-3)' }} title="Düzenle">
          <Pencil size={14} />
        </button>
        <button onClick={onDelete} className="p-1.5 rounded-lg hover:bg-[var(--surface-2)]" style={{ color: 'var(--error)' }} title="Sil">
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}

function ModelEditRow({ model, onSave, onCancel }: { model: any, onSave: (b: any) => void, onCancel: () => void }) {
  const [form, setForm] = useState({
    ollama_name: model?.ollama_name ?? '',
    name_tr: model?.name_i18n?.tr ?? '',
    name_en: model?.name_i18n?.en ?? '',
    desc_tr: model?.desc_i18n?.tr ?? '',
    speed: model?.speed ?? 3,
    enabled: model?.enabled ?? true,
    internal: model?.internal ?? false,
    is_default: model?.is_default ?? false,
  })
  const f = (k: string) => (e: any) => setForm(s => ({ ...s, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  return (
    <div className="p-4 rounded-2xl" style={{ border: '1px solid var(--accent)', background: 'var(--surface)' }}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        {!model && <Input label="Ollama adı" value={form.ollama_name} onChange={f('ollama_name')} />}
        <Input label="Ad (TR)" value={form.name_tr} onChange={f('name_tr')} />
        <Input label="Ad (EN)" value={form.name_en} onChange={f('name_en')} />
        <Input label="Açıklama (TR)" value={form.desc_tr} onChange={f('desc_tr')} />
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none font-medium" style={{ color: form.is_default ? 'var(--accent)' : 'var(--text-2)' }}>
            <input type="checkbox" checked={form.is_default} onChange={f('is_default')} className="w-4 h-4 accent-[var(--accent)]" /> Varsayılan Model
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none" style={{ color: 'var(--text-2)' }}>
            <input type="checkbox" checked={form.enabled} onChange={f('enabled')} className="w-4 h-4 accent-[var(--accent)]" /> Aktif
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none" style={{ color: 'var(--text-2)' }}>
            <input type="checkbox" checked={form.internal} onChange={f('internal')} className="w-4 h-4 accent-[var(--accent)]" /> Dahili
          </label>
          <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-2)' }}>
            Hız:
            <select value={form.speed} onChange={f('speed')} className="px-2 py-1 rounded-lg text-sm"
              style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}>
              {[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="p-2 rounded-xl hover:bg-[var(--surface-2)]" style={{ color: 'var(--text-3)' }} title="İptal"><X size={16} /></button>
        <button onClick={() => onSave(form)} className="p-2 rounded-xl" style={{ background: 'var(--grad)', color: '#fff' }} title="Kaydet"><Check size={16} /></button>
      </div>
    </div>
  )
}


function Input({ label, value, onChange }: { label: string, value: string, onChange: any }) {
  return (
    <div>
      <label className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>{label}</label>
      <input value={value} onChange={onChange}
        className="w-full px-3 py-1.5 rounded-xl text-sm outline-none"
        style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }} />
    </div>
  )
}

function Spinner() {
  return <div className="flex items-center justify-center h-32" style={{ color: 'var(--text-3)' }}>Yükleniyor…</div>
}
