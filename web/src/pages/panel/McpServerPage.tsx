import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Square, Copy, Check, RefreshCw } from 'lucide-react'
import {
  getMcpStatus, getMcpTools, getMcpToken, startMcp, stopMcp,
  type McpStatus, type ToolInfo,
} from '../../api/mcp'
import { useAuthStore } from '../../store/authStore'

// "MCP Server" — relay (mcp/ollama_mcp.py) HTTP modu Caddy üzerinden (/mcp ->
// 127.0.0.1:8765) HTTPS + Bearer token ile yayın yapar. Bu sayfa artık CANLI:
// admin; süreci başlatır/durdurur, sağlığı izler ve araç listelerini backend'den
// (REGISTRY + relay tools/list) dinamik alır. Üyeler salt-okunur özeti görür.

// Relay KAPALIYKEN gösterilecek yedek liste (mcp/ollama_mcp.py ile uyumlu).
const FALLBACK_RELAY_TOOLS: ToolInfo[] = [
  { name: 'genel_sohbet', description: 'Genel sohbet, soru-cevap, yazım, özet' },
  { name: 'derin_analiz', description: 'Derin muhakeme, çok adımlı analiz (yavaş)' },
  { name: 'kod_yaz', description: 'Kod üretimi / refactor' },
  { name: 'web_ara', description: 'DuckDuckGo ile güncel web araması' },
  { name: 'yerel_sohbet', description: 'Herhangi bir modelle tek atımlık üretim' },
  { name: 'modelleri_listele', description: 'Disk + bellek model durumu' },
  { name: 'uzaktan_sohbet', description: 'Kaydedilmiş uzak Ollama bağlantısından model çalıştırma' },
  { name: 'uzaktan_modelleri_listele', description: 'Kaydedilmiş uzak Ollama bağlantısının modelleri' },
]

export default function McpServerPage() {
  const role = useAuthStore((s) => s.role)
  const isAdmin = role === 'admin'

  const qc = useQueryClient()
  const [busy, setBusy] = useState<'' | 'start' | 'stop' | 'force'>('')
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)
  const [showToken, setShowToken] = useState(false)
  const [fullToken, setFullToken] = useState('')
  const [copied, setCopied] = useState(false)

  const statusQ = useQuery({
    queryKey: ['mcp', 'status'],
    queryFn: getMcpStatus,
    enabled: isAdmin,
    refetchInterval: 10000,
  })
  const toolsQ = useQuery({
    queryKey: ['mcp', 'tools'],
    queryFn: getMcpTools,
    enabled: isAdmin,
    refetchInterval: 30000,
  })

  const st: McpStatus | undefined = statusQ.data
  const chatTools: ToolInfo[] = toolsQ.data?.chat_tools ?? []
  const relayTools: ToolInfo[] = toolsQ.data?.relay_tools ?? FALLBACK_RELAY_TOOLS
  const relayLive = toolsQ.data ? toolsQ.data.relay_tools != null : false

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['mcp'] })
  }

  const runAction = async (kind: 'start' | 'stop' | 'force') => {
    setBusy(kind)
    setNotice(null)
    try {
      if (kind === 'start') {
        const r = await startMcp()
        setNotice({
          ok: true,
          text: r.already
            ? 'Relay zaten çalışıyor.'
            : `Relay başlatıldı${r.pid ? ` (pid ${r.pid})` : ''}.${r.warning ? ' ' + r.warning : ''}`,
        })
      } else {
        const r = await stopMcp(kind === 'force')
        setNotice({ ok: true, text: `Durduruldu${r.stopped ? ` (pid ${r.stopped})` : ''}.` })
        setShowToken(false)
      }
      invalidate()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      setNotice({ ok: false, text: typeof detail === 'string' ? detail : 'İşlem başarısız oldu.' })
    } finally {
      setBusy('')
    }
  }

  const revealToken = async () => {
    if (!fullToken) {
      try {
        const r = await getMcpToken()
        setFullToken(r.token)
      } catch {
        return
      }
    }
    setShowToken(true)
  }

  const copyToken = async () => {
    try {
      await navigator.clipboard.writeText(fullToken || st?.token_masked || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      /* pano erişimi yoksa sessiz geç */
    }
  }

  const stateBadge = () => {
    if (statusQ.isLoading) return <Badge>yükleniyor…</Badge>
    if (statusQ.isError) return <Badge tone="warn">durum alınamadı</Badge>
    if (!st?.running) return <Badge tone="warn">durdu</Badge>
    if (st.external) return <Badge tone="warn">çalışıyor (.bat ile)</Badge>
    return <Badge tone="good">çalışıyor</Badge>
  }

  if (!isAdmin) {
    return (
      <div className="flex flex-col gap-5 max-w-[860px]" style={{ animation: 'fadeUp .4s both' }}>
        <Card>
          <div className="flex items-center justify-between mb-1">
            <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>Claude Desktop / Cowork relay</div>
            <Badge>stdio · http</Badge>
          </div>
          <p className="text-sm mb-2" style={{ color: 'var(--text-2)' }}>
            Yerel modellerine <code style={{ fontFamily: 'var(--font-mono)' }}>mcp/ollama_mcp.py</code> üzerinden
            Claude Desktop / Cowork'ten delegasyon yapılır — konuşmayı Claude yönetir, ağır işi yerel modeller yapar.
          </p>
          <p className="text-xs" style={{ color: 'var(--text-3)' }}>
            Süreç yönetimi ve bağlantı anahtarı için admin girişi gerekir.
          </p>
        </Card>
        <ToolsCard title="Relay araçları" subtitle={null} tools={FALLBACK_RELAY_TOOLS} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5 max-w-[860px]" style={{ animation: 'fadeUp .4s both' }}>
      {/* ── Durum + yönetim ─────────────────────────────────────────── */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>MCP relay (HTTP modu)</div>
          <div className="flex items-center gap-2">
            {stateBadge()}
            {st?.healthy && <span data-dot="active" />}
          </div>
        </div>

        <div className="rounded-[10px] p-4 text-[13px] mb-4"
             style={{ background: 'var(--bg)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)', color: 'var(--text-2)', lineHeight: 1.9 }}>
          <div><span style={{ color: 'var(--text-3)' }}>yerel&nbsp;&nbsp;</span>{st?.url ?? `http://127.0.0.1:8765/mcp`}</div>
          <div><span style={{ color: 'var(--text-3)' }}>genel&nbsp;&nbsp;</span>https://rorcun.com/mcp <span style={{ color: 'var(--text-3)' }}>(Caddy aktifse)</span></div>
          <div><span style={{ color: 'var(--text-3)' }}>pid&nbsp;&nbsp;&nbsp;&nbsp;</span>{st?.managed && st.pid ? st.pid : '—'}
            {st?.external && <span style={{ color: 'var(--text-3)' }}> · .bat penceresinden başlatılmış</span>}
          </div>
        </div>

        <div className="flex flex-wrap gap-2.5">
          <button onClick={() => runAction('start')} disabled={busy !== '' || !!st?.running}
                  className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[13px] font-medium transition-opacity disabled:opacity-40"
                  style={{ border: '1px solid var(--accent)', color: 'var(--accent)', cursor: busy === 'start' ? 'wait' : 'pointer', background: 'transparent' }}>
            {busy === 'start' ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />} Başlat
          </button>
          <button onClick={() => runAction('stop')} disabled={busy !== '' || !st?.running}
                  className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[13px] font-medium transition-opacity disabled:opacity-40"
                  style={{ border: '1px solid var(--border)', color: 'var(--danger, #e5484d)', cursor: busy === 'stop' ? 'wait' : 'pointer', background: 'transparent' }}>
            {busy === 'stop' ? <RefreshCw size={14} className="animate-spin" /> : <Square size={14} />} Durdur
          </button>
          {st?.external && (
            <button onClick={() => runAction('force')} disabled={busy !== ''}
                    className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[13px] font-medium"
                    style={{ border: '1px solid var(--warning, #f5a623)', color: 'var(--warning, #f5a623)', cursor: 'pointer', background: 'transparent' }}>
              {busy === 'force' ? <RefreshCw size={14} className="animate-spin" /> : <Square size={14} />} Zorla Durdur
            </button>
          )}
        </div>

        {notice && (
          <p className="text-[13px] mt-3 mb-0" style={{ color: notice.ok ? 'var(--success)' : 'var(--danger, #e5484d)' }}>
            {notice.text}
          </p>
        )}

        {/* Token */}
        <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="flex items-center justify-between">
            <div className="text-[13px] font-medium" style={{ color: 'var(--text-2)' }}>Bağlantı anahtarı (MCP_TOKEN)</div>
            <button onClick={() => setShowToken((v) => !v)}
                    className="text-[12.5px]" style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
              {showToken ? 'gizle' : 'göster'}
            </button>
          </div>
          <div className="mt-2 flex items-center gap-2 rounded-[9px] px-3 py-2.5"
               style={{ background: 'var(--bg)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)' }}>
            <span className="text-[12.5px] truncate flex-1" style={{ color: 'var(--text-2)' }}>
              {showToken ? (fullToken || st?.token_masked) : (st?.token_masked || '—')}
            </span>
            {showToken && fullToken && (
              <button onClick={copyToken} title="Kopyala"
                      style={{ border: 'none', background: 'none', color: copied ? 'var(--success)' : 'var(--text-3)', cursor: 'pointer' }}>
                {copied ? <Check size={15} /> : <Copy size={15} />}
              </button>
            )}
          </div>
          {!showToken && (
            <button onClick={revealToken} className="text-[12px] mt-2" style={{ border: 'none', background: 'none', color: 'var(--text-3)', cursor: 'pointer' }}>
              Tam anahtarı görüntüle (istemci config'i için)
            </button>
          )}
          {showToken && (
            <p className="text-[11.5px] mt-2 mb-0" style={{ color: 'var(--text-3)' }}>
              Bu anahtarı paylaşma. Değiştirmek için <code style={{ fontFamily: 'var(--font-mono)' }}>mcp/.mcp_token</code> dosyasını silip yeniden başlat.
            </p>
          )}
        </div>
      </Card>

      {/* ── Relay araçları (canlı) ──────────────────────────────────── */}
      <ToolsCard
        title="Relay araçları"
        subtitle={
          toolsQ.isLoading ? null :
            relayLive
              ? { text: `canlı liste (${relayTools?.length ?? 0} araç)`, good: true }
              : { text: 'relay kapalı — varsayılan liste', good: false }
        }
        tools={relayTools ?? []}
      />

      {/* ── Sohbet-içi araçlar (REGISTRY) ───────────────────────────── */}
      <Card>
        <div className="flex items-center justify-between mb-3.5">
          <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>Sohbet içi araçlar</div>
          <Badge tone={chatTools.some((t) => t.enabled) ? 'good' : undefined}>
            {chatTools.filter((t) => t.enabled).length}/{chatTools.length} aktif
          </Badge>
        </div>
        <p className="text-xs mb-3" style={{ color: 'var(--text-3)' }}>
          Backend REGISTRY kayıtları — panel sohbetinde modelin tool-calling döngüsünde kullanılır.
        </p>
        <div className="flex flex-col">
          {(chatTools.length ? chatTools : []).map((tool, i) => (
            <div key={tool.name} className="flex items-center gap-3 py-2.5"
                 style={{ borderTop: i > 0 ? '1px solid var(--border-2)' : undefined }}>
              <span data-dot={tool.enabled ? 'active' : 'idle'} />
              <div className="flex-1 min-w-0">
                <div className="text-[13.5px] font-medium" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{tool.name}</div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--text-3)' }}>{tool.description}</div>
              </div>
              <Badge tone={tool.enabled ? 'good' : 'warn'}>{tool.enabled ? 'aktif' : 'kapalı'}</Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}


function ToolsCard({ title, subtitle, tools }: {
  title: string
  subtitle: { text: string; good: boolean } | null
  tools: ToolInfo[]
}) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-3.5">
        <div className="text-[15px] font-semibold" style={{ color: 'var(--text)' }}>{title}</div>
        {subtitle && <Badge tone={subtitle.good ? 'good' : 'warn'}>{subtitle.text}</Badge>}
      </div>
      <div className="flex flex-col">
        {tools.map((tool, i) => (
          <div key={tool.name} className="flex items-center gap-3 py-3"
               style={{ borderTop: i > 0 ? '1px solid var(--border-2)' : undefined }}>
            <div className="flex-1 min-w-0">
              <div className="text-[13.5px] font-medium" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{tool.name}</div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--text-3)' }}>{tool.description}</div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[14px] p-5" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
      {children}
    </div>
  )
}

function Badge({ children, tone }: { children: React.ReactNode; tone?: 'good' | 'warn' }) {
  const color = tone === 'good' ? 'var(--success)' : tone === 'warn' ? 'var(--warning, #f5a623)' : 'var(--text-2)'
  return (
    <span className="text-[11.5px] font-medium px-2.5 py-1 rounded-full"
          style={{ border: '1px solid var(--border)', background: 'var(--surface-2)', color }}>
      {children}
    </span>
  )
}
