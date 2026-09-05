import { useEffect, useRef, useState, useCallback, memo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { Copy, Check, RotateCcw, Pencil, ChevronDown, Link2, Wrench, ChevronLeft, ChevronRight, Brain } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import { getChat, getChatLive } from '../../api/chats'
import type { Message } from '../../api/chats'
import StatusMessage, { StatusType } from './StatusMessage'
import { selectBranch } from '../../api/chats'

interface StreamState {
  streaming: boolean
  content: string
  thinking?: string
  queued?: number
  thinkStart?: number   // ilk thinking_delta anı (canlı sayaç için)
  thinkMs?: number      // düşünme bitince donmuş süre
}

// Üretim sırasında olan biteni (durum + araç olayları) canlı listeleyen kayıt
interface ActivityItem { kind: 'status' | 'tool'; status?: string; label: string }

const TOOL_LABELS: Record<string, string> = {
  web_search: 'Web araması', calculator: 'Hesap makinesi', run_python: 'Python',
}

// Tamponlu markdown renderer — yarım açık kod bloğunu kapatır
function bufferedMarkdown(raw: string): string {
  const codeBlockCount = (raw.match(/```/g) || []).length
  if (codeBlockCount % 2 !== 0) return raw + '\n```'
  return raw
}

// Kod bloğu içeriğinin ham metnini hast düğümünden çıkarır (kopyala için).
function hastText(node: any): string {
  if (!node) return ''
  if (node.type === 'text') return node.value || ''
  return (node.children || []).map(hastText).join('')
}

// Kod bloğu: üstte dil etiketi + kopyala; gövdede rehype-highlight ile renklendirilmiş
// children korunur (koyu zemin, her temada okunaklı).
function CodeBlock({ className, raw, children }: { className?: string; raw: string; children: any }) {
  const [copied, setCopied] = useState(false)
  const lang = /language-(\w+)/.exec(className || '')?.[1]
  const copy = () => {
    navigator.clipboard.writeText(raw)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="my-2 rounded-lg overflow-hidden" style={{ border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between px-3 py-1 text-[11px]"
           style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>
        <span className="font-mono uppercase tracking-wide">{lang || 'kod'}</span>
        <button onClick={copy}
          className="flex items-center gap-1 transition-colors hover:text-[var(--text)]"
          style={{ color: 'var(--text-3)' }}>
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Kopyalandı' : 'Kopyala'}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed" style={{ background: '#0d1117' }}>
        <code className={`${className || ''} hljs`} style={{ background: 'transparent' }}>{children}</code>
      </pre>
    </div>
  )
}

// ReactMarkdown için kod/inline-kod renderer'ları.
const MD_COMPONENTS = {
  pre: ({ children }: any) => <>{children}</>,
  code(props: any) {
    const { className, children, node } = props
    const isBlock = /language-(\w+)/.test(className || '') || hastText(node).includes('\n')
    if (!isBlock) {
      return (
        <code className="px-1 py-0.5 rounded text-[0.85em] font-mono"
          style={{ background: 'var(--surface-2)', color: 'var(--accent)' }}>
          {children}
        </code>
      )
    }
    return <CodeBlock className={className} raw={hastText(node)}>{children}</CodeBlock>
  },
}

// PERF: memo şart — streaming sırasında her token'da MessageList yeniden render
// olur; memo olmadan TÜM geçmiş mesajlar her token'da ReactMarkdown +
// rehype-highlight + KaTeX ile baştan parse edilir (uzun sohbetlerde akış donar).
const MessageBubble = memo(function MessageBubble({
  msg, isStreaming, isOptimistic, isFailed, onCopy, onEdit, onRegenerate, onSelectBranch,
}: {
  msg: Message
  isStreaming?: boolean
  isOptimistic?: boolean
  isFailed?: boolean
  onCopy: (text: string) => void
  onEdit?: (text: string, messageId?: number) => void
  onRegenerate?: () => void
  onSelectBranch?: (messageId: number) => void
}) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [showSources, setShowSources] = useState(false)
  const isUser = msg.role === 'user'
  const isSystem = msg.role === 'system'

  const copy = () => {
    navigator.clipboard.writeText(msg.content)
    setCopied(true)
    onCopy(msg.content)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="group flex gap-3 max-w-3xl mx-auto w-full"
    >
      {/* Avatar — her zaman solda (NewDesing: kullanıcı = baş harf, asistan = ›) */}
      <div className="shrink-0 mt-1">
        <div className="w-8 h-8 flex items-center justify-center text-sm font-bold"
             style={{
               borderRadius: 9,
               background: isUser ? 'var(--surface-2)' : isSystem ? 'var(--warning)' : 'var(--grad)',
               border: isUser ? '1px solid var(--border)' : 'none',
               color: isUser ? 'var(--text)' : isSystem ? '#000' : '#fff',
               fontFamily: isUser ? 'inherit' : 'var(--font-mono)',
             }}>
          {isUser ? 'S' : isSystem ? '!' : '›'}
        </div>
      </div>

      {/* İçerik — tam genişlik, alt alta */}
      <div className="flex-1 min-w-0 flex flex-col gap-1 items-start">
        {/* Dosya ekleri */}
        {msg.attachments && msg.attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-1">
            {msg.attachments.map((att, i) => (
              <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
                style={{ background: 'var(--surface-2)', color: 'var(--text-2)', border: '1px solid var(--border)' }}>
                📎 {att.name}
                {att.num_images ? ` (${att.num_images} görsel)` : ''}
              </span>
            ))}
          </div>
        )}

        {/* Kaydedilmiş düşünme süreci — katlanmış panel (asistan mesajları) */}
        {!isUser && !isSystem && msg.thinking && (
          <ThinkingPanel text={msg.thinking} live={false} defaultOpen={false}
                         className="w-full mb-1" />
        )}

        {/* Mesaj bloğu — satırın tamamını kullanır */}
        <div className={`w-full px-4 py-3 overflow-hidden ${isOptimistic ? 'opacity-60' : ''}`}
             style={{
               borderRadius: 13,
               background: isUser
                 ? 'var(--accent-soft)'
                 : isSystem ? 'color-mix(in srgb, var(--warning) 10%, var(--surface))' : 'var(--surface)',
               color: 'var(--text)',
               border: isFailed ? '1px solid var(--error)' : '1px solid var(--border)',
               overflowWrap: 'anywhere',
             }}>
          {isUser ? (
            <div className="flex justify-between items-start gap-4">
              <p className="text-sm whitespace-pre-wrap leading-relaxed break-words flex-1">{msg.content}</p>
              {isFailed && (
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-xs font-medium" style={{ color: 'var(--error)' }}>Gönderilemedi</span>
                {onEdit && (
                  <button
                    onClick={() => onEdit(msg.content, msg.id)}
                    className="p-1 rounded-lg hover:bg-[var(--surface-2)] transition-colors"
                    style={{ color: 'var(--error)' }}
                    title="Yeniden gönder"
                  >
                    <RotateCcw size={12} />
                  </button>
                )}
              </div>
            )}
            </div>
          ) : (
            <div className={`prose text-sm leading-relaxed ${isStreaming ? 'streaming-cursor' : ''}`}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[[rehypeHighlight, { ignoreMissing: true }], rehypeKatex]}
                components={MD_COMPONENTS}
              >
                {bufferedMarkdown(msg.content)}
              </ReactMarkdown>
            </div>
          )}
          {!isUser && showSources && msg.sources && msg.sources.length > 0 && (
            <div className="mt-3 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
              <p className="text-[11px] font-semibold mb-1.5" style={{ color: 'var(--text-3)' }}>Kaynaklar</p>
              <div className="space-y-1">
                {msg.sources.map((src, i) => src.url ? (
                  <a key={i} href={src.url} target="_blank" rel="noopener noreferrer"
                     className="block text-xs hover:underline break-all" style={{ color: 'var(--accent)' }}
                     title={src.snippet || src.url}>
                    [{i + 1}] {src.title || src.url}
                  </a>
                ) : (
                  <div key={i} className="text-xs" style={{ color: 'var(--text-2)' }}>
                    📄 [{i + 1}] {src.title}{src.snippet ? ` — ${src.snippet}` : ''}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Aksiyonlar */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {!!msg.branch_count && msg.branch_count > 1 && msg.siblings && onSelectBranch && (
            <div className="flex items-center gap-0.5 mr-1">
              <button
                disabled={(msg.branch_index || 1) <= 1}
                onClick={() => { const cur = (msg.branch_index || 1) - 1; const tgt = msg.siblings![cur - 1]; if (tgt != null) onSelectBranch(tgt) }}
                className="p-0.5 rounded hover:bg-[var(--surface-2)] disabled:opacity-30 transition-colors"
                style={{ color: 'var(--text-3)' }} title="Önceki dal">
                <ChevronLeft size={13} />
              </button>
              <span className="text-[10px] tabular-nums" style={{ color: 'var(--text-3)' }}>{msg.branch_index}/{msg.branch_count}</span>
              <button
                disabled={(msg.branch_index || 1) >= msg.branch_count}
                onClick={() => { const cur = (msg.branch_index || 1) - 1; const tgt = msg.siblings![cur + 1]; if (tgt != null) onSelectBranch(tgt) }}
                className="p-0.5 rounded hover:bg-[var(--surface-2)] disabled:opacity-30 transition-colors"
                style={{ color: 'var(--text-3)' }} title="Sonraki dal">
                <ChevronRight size={13} />
              </button>
            </div>
          )}
          <button onClick={copy} className="p-1.5 rounded-lg hover:bg-[var(--surface-2)] transition-colors"
            style={{ color: 'var(--text-3)' }} title={copied ? t('chat.copied') : t('chat.copy')}>
            {copied ? <Check size={13} style={{ color: 'var(--success)' }} /> : <Copy size={13} />}
          </button>
          {!isUser && msg.sources && msg.sources.length > 0 && (
            <button onClick={() => setShowSources(v => !v)}
              className="p-1.5 rounded-lg hover:bg-[var(--surface-2)] flex items-center gap-1 transition-colors"
              style={{ color: showSources ? 'var(--accent)' : 'var(--text-3)' }} title="Kaynakları göster">
              <Link2 size={13} /><span className="text-[11px] font-medium">{msg.sources.length}</span>
            </button>
          )}
          {isUser && onEdit && (
            <button onClick={() => onEdit(msg.content, msg.id)} className="p-1.5 rounded-lg hover:bg-[var(--surface-2)]"
              style={{ color: 'var(--text-3)' }} title={t('chat.edit')}>
              <Pencil size={13} />
            </button>
          )}
          {!isUser && onRegenerate && (
            <button onClick={onRegenerate} className="p-1.5 rounded-lg hover:bg-[var(--surface-2)]"
              style={{ color: 'var(--text-3)' }} title={t('chat.regenerate')}>
              <RotateCcw size={13} />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  )
})

/** Modelin dusunme surecini canli (streaming) gosteren, acilir-kapanir panel.
 *  Canliyken saniye sayaci isler; bittikten sonra sure donmus gosterilir.
 *  Kayitli mesajlarda (live=false, defaultOpen=false) katlanmis olarak durur. */
function ThinkingPanel({ text, live, startedAt, durationMs, defaultOpen = true, className = '' }: {
  text: string; live: boolean; startedAt?: number; durationMs?: number
  defaultOpen?: boolean; className?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(defaultOpen)
  const [, setTick] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  // Canlı sayaç — saniyede bir yeniden çiz
  useEffect(() => {
    if (!live || !startedAt) return
    const id = setInterval(() => setTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [live, startedAt])

  useEffect(() => {
    if (live && open) boxRef.current?.scrollTo({ top: boxRef.current.scrollHeight })
  }, [text, live, open])

  if (!text) return null

  const secs = live && startedAt
    ? Math.max(0, Math.round((Date.now() - startedAt) / 1000))
    : durationMs != null ? Math.max(1, Math.round(durationMs / 1000)) : null
  const label = live
    ? (secs != null ? t('chat.thinkingLive', { s: secs }) : t('chat.thinking'))
    : (secs != null ? t('chat.thinkingDuration', { s: secs }) : t('chat.thinkingProcess'))

  return (
    <div className={`overflow-hidden ${className}`}
         style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 11 }}>
      <button onClick={() => setOpen((o) => !o)}
              className="flex items-center gap-2 text-[12.5px] font-medium w-full cursor-pointer select-none"
              style={{ color: 'var(--text-2)', padding: '9px 13px', background: 'transparent', border: 'none' }}>
        <Brain size={14} style={{ color: 'var(--accent)',
                                  animation: live ? 'pulse-soft 1.2s ease-in-out infinite' : 'none' }} />
        <span>{label}</span>
        {live && (
          <span className="inline-flex gap-[3px] ml-0.5">
            {[0, 0.15, 0.3].map((d) => (
              <span key={d} className="w-1 h-1 rounded-full"
                    style={{ background: 'var(--accent)', animation: `bounce-dot 1s infinite ${d}s` }} />
            ))}
          </span>
        )}
        <ChevronDown size={14} className="ml-auto transition-transform"
                     style={{ color: 'var(--text-3)', transform: open ? 'rotate(180deg)' : 'none' }} />
      </button>
      {open && (
        <div ref={boxRef}
             className="text-[12.5px] leading-relaxed whitespace-pre-wrap"
             style={{ color: 'var(--text-3)', maxHeight: 220, overflowY: 'auto',
                      padding: '4px 13px 12px', borderTop: '1px solid var(--border-2)',
                      fontFamily: 'var(--font-mono)' }}>
          {text}
        </div>
      )}
    </div>
  )
}

/** Üretim sırasında sunucuda olan biteni (özetleme, web araması, RAG, araç
 *  çağrıları...) adım adım canlı gösteren zaman çizelgesi. */
function ActivityTimeline({ items, busy }: { items: ActivityItem[]; busy: boolean }) {
  const { t } = useTranslation()
  if (!items.length) return null
  return (
    <div className="px-4 py-2.5 max-w-3xl mx-auto w-full"
         style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 11 }}>
      <div className="flex items-center gap-2 text-xs font-medium mb-1.5" style={{ color: 'var(--text-2)' }}>
        <Wrench size={13} className={busy ? 'animate-pulse' : ''} style={{ color: 'var(--accent)' }} />
        <span>{t('chat.activityTitle')}</span>
      </div>
      <div className="space-y-1">
        {items.map((it, i) => {
          const isLast = i === items.length - 1
          const active = isLast && busy
          return (
            <div key={i} className="flex items-center gap-2 text-xs" style={{ color: active ? 'var(--text-2)' : 'var(--text-3)' }}>
              {active ? (
                <span className="w-3.5 h-3.5 flex items-center justify-center shrink-0">
                  <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--accent)' }} />
                </span>
              ) : (
                <Check size={14} className="shrink-0" style={{ color: 'var(--success)' }} />
              )}
              {it.kind === 'tool' && <Wrench size={11} className="shrink-0" />}
              <span className="truncate">{it.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function MessageList({ chatId }: { chatId: string }) {
  const { t } = useTranslation()
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [stream, setStream] = useState<StreamState>({ streaming: false, content: '' })
  const [optimisticMsg, setOptimisticMsg] = useState<{ id: string, content: string, failed: boolean } | null>(null)
  const [statusMsg, setStatusMsg] = useState<{ type: StatusType, message: string, progress?: number } | null>(null)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [editText, setEditText] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: chat, refetch } = useQuery({
    queryKey: ['chat', chatId],
    queryFn: () => getChat(chatId).then((r) => r.data),
    staleTime: 0,
  })

  // SSE stream dinle (global event bus'tan). Composer'ın yayınladığı `chat-stream`
  // olaylarını tek noktada işler:
  //   optimistic-user → geçici kullanıcı balonu | status/status-clear → durum bildirimi
  //   start → düşünme | delta → akan içerik | done → bitti+refetch | error → hata
  useEffect(() => {
    // PERF: delta'lar token token gelir (saniyede onlarca). Her birinde setState
    // yapmak, her token'da tam render + markdown parse demek. Delta'ları biriktirip
    // kare başına (requestAnimationFrame) TEK setState ile akıtıyoruz.
    let raf = 0
    const pend = { content: '', thinking: '' }
    const flush = () => {
      raf = 0
      const c = pend.content, th = pend.thinking
      pend.content = ''; pend.thinking = ''
      if (!c && !th) return
      setStream((s) => ({
        ...s,
        content: c ? s.content + c : s.content,
        thinking: th ? (s.thinking || '') + th : s.thinking,
        thinkStart: th ? (s.thinkStart ?? Date.now()) : s.thinkStart,
        // İlk içerik gelince düşünme süresini dondur
        thinkMs: c ? (s.thinkMs ?? (s.thinkStart ? Date.now() - s.thinkStart : undefined)) : s.thinkMs,
      }))
    }
    const schedule = () => { if (!raf) raf = requestAnimationFrame(flush) }
    const clearPending = () => {
      pend.content = ''; pend.thinking = ''
      if (raf) { cancelAnimationFrame(raf); raf = 0 }
    }

    const handler = (e: Event) => {
      const ev = (e as CustomEvent).detail
      if (ev.chatId !== chatId) return
      if (ev.type === 'optimistic-user') {
        setOptimisticMsg({ id: ev.tempId, content: ev.content, failed: false })
      }
      else if (ev.type === 'status') {
        setStatusMsg({ type: ev.status, message: ev.message, progress: ev.progress })
        // Aynı mesajın peş peşe tekrarını ekleme (ilerleme güncellemeleri)
        setActivity((prev) => prev.length && prev[prev.length - 1].label === ev.message
          ? prev : [...prev, { kind: 'status', status: ev.status, label: ev.message }])
      }
      else if (ev.type === 'status-clear') {
        setStatusMsg(null)
      }
      else if (ev.type === 'tool') {
        const label = TOOL_LABELS[ev.name] || ev.name
        setActivity((prev) => prev.length && prev[prev.length - 1].label === label
          ? prev : [...prev, { kind: 'tool', label }])
      }
      else if (ev.type === 'start') {
        clearPending()
        setStream({ streaming: true, content: '', thinking: '' })
        setActivity([])
      }
      else if (ev.type === 'thinking_delta') {
        setStatusMsg(null)
        pend.thinking += ev.text
        schedule()
      }
      else if (ev.type === 'delta') {
        setStatusMsg(null)
        pend.content += ev.text
        schedule()
      }
      else if (ev.type === 'done') {
        clearPending()
        setStream({ streaming: false, content: '', thinking: '' })
        setStatusMsg(null)
        setActivity([])
        setOptimisticMsg(null)
        refetch()
        // Otomatik başlık değişmiş olabilir → sidebar listesi tazelensin
        queryClient.invalidateQueries({ queryKey: ['chats'] })
      }
      else if (ev.type === 'error') {
        clearPending()
        setStream({ streaming: false, content: '' })
        setStatusMsg(null)
        setActivity([])
        setOptimisticMsg(prev => prev ? { ...prev, failed: true } : null)
        refetch()
      }
      else if (ev.type === 'queue') setStream((s) => ({ ...s, queued: ev.position }))
    }
    window.addEventListener('chat-stream', handler)
    return () => {
      window.removeEventListener('chat-stream', handler)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [chatId, refetch, queryClient])

  // Yeniden giriş: bu sohbette DEVAM EDEN bir üretim varsa canlı duruma katıl.
  // Arka plan görevi bağlantı kopsa da çalıştığından, sohbete geri dönüldüğünde
  // /live anlık görüntüsü mevcut akış arayüzüne sentetik chat-stream olayları
  // olarak beslenir (durum + düşünme bloğu + akan metin + araç etkinlikleri).
  // Yerel bir gönderim başlarsa ('start' bizden gelmemişse) poll bırakılır —
  // o zaman akışı Composer'ın kendi SSE'si taşır (çift besleme önlenir).
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const prev = { textLen: 0, thinkLen: 0, toolsEmitted: 0, started: false }

    const emit = (detail: Record<string, unknown>) =>
      window.dispatchEvent(new CustomEvent('chat-stream', {
        detail: { chatId, __live: true, ...detail },
      }))

    const stopPoll = () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }

    // Kullanıcı bu sekmeden yeni mesaj gönderdi → akışı SSE'ye devret
    const onLocal = (e: Event) => {
      const ev = (e as CustomEvent).detail
      if (ev.chatId === chatId && ev.type === 'start' && !ev.__live) stopPoll()
    }
    window.addEventListener('chat-stream', onLocal)

    const poll = async () => {
      try {
        const s = await getChatLive(chatId)
        if (stopped) return
        if (!s.active && !s.finished) return   // üretim yok — tek seferlik kontrol

        const hasAny = !!((s.text?.length) || (s.thinking?.length) || s.tools?.length)
        if (!prev.started && hasAny) {
          prev.started = true
          emit({ type: 'start' })
        }

        if (s.status?.message) {
          emit({ type: 'status', status: s.status.status || 'processing', message: s.status.message })
        }

        const th = s.thinking || ''
        const tx = s.text || ''
        if (th.length > prev.thinkLen) emit({ type: 'thinking_delta', text: th.slice(prev.thinkLen) })
        if (tx.length > prev.textLen) emit({ type: 'delta', text: tx.slice(prev.textLen) })
        prev.thinkLen = th.length
        prev.textLen = tx.length

        for (; prev.toolsEmitted < (s.tools?.length ?? 0); prev.toolsEmitted++) {
          emit({ type: 'tool', name: s.tools![prev.toolsEmitted] })
        }

        if (s.error) {
          emit({ type: 'error', message: s.error })
          stopPoll()
          return
        }
        if (s.finished) {
          // Kalan parçaları basitçe boşver — done refetch ile DB'den tam metin gelir
          emit({ type: 'done' })
          stopPoll()
          return
        }
      } catch {
        /* ağ hatası — sessizce yeniden dene */
      }
      if (!stopped) timer = setTimeout(poll, 1000)
    }
    poll()

    return () => {
      stopPoll()
      window.removeEventListener('chat-stream', onLocal)
    }
  }, [chatId])

  // Otomatik kaydırma — streaming sırasında 'auto' (smooth animasyon her karede
  // yeniden tetiklenip ana thread'i meşgul eder), diğer durumlarda 'smooth'.
  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: stream.streaming ? 'auto' : 'smooth' })
  }, [chat?.messages?.length, stream.content, autoScroll, stream.streaming])

  // memo'lu MessageBubble için SABİT callback'ler (inline arrow = her render'da
  // yeni referans = memo işlevsiz kalır).
  const handleEdit = useCallback((text: string, messageId?: number) => {
    window.dispatchEvent(new CustomEvent('edit-message', { detail: { chatId, text, messageId } }))
  }, [chatId])
  const handleRegenerate = useCallback(() => {
    window.dispatchEvent(new CustomEvent('regenerate', { detail: { chatId } }))
  }, [chatId])
  const handleSelectBranch = useCallback((mid: number) => {
    selectBranch(chatId, mid).then(() => refetch())
  }, [chatId, refetch])
  const handleCopy = useCallback(() => {}, [])

  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    setAutoScroll(nearBottom)
    setShowScrollBtn(!nearBottom)
  }, [])

  const messages = chat?.messages || []

  return (
    <div ref={containerRef} onScroll={handleScroll}
         className="flex-1 overflow-y-auto px-2 md:px-4 py-4 md:py-6 space-y-4 relative"
         style={{ scrollBehavior: stream.streaming ? 'auto' : 'smooth' }}>

      <AnimatePresence initial={false}>
        {messages.filter((m) => m.role !== 'system' || m.content.includes('Sistem Özeti')).map((msg, i) => (
          <MessageBubble
            key={msg.id || i}
            msg={msg}
            onCopy={handleCopy}
            onEdit={handleEdit}
            onRegenerate={handleRegenerate}
            onSelectBranch={handleSelectBranch}
          />
        ))}
        {optimisticMsg && (
          <MessageBubble
            key={optimisticMsg.id}
            msg={{ id: parseInt(optimisticMsg.id) || 0, role: 'user', content: optimisticMsg.content, tokens: 0 }}
            isOptimistic={!optimisticMsg.failed}
            isFailed={optimisticMsg.failed}
            onCopy={handleCopy}
            onEdit={optimisticMsg.failed ? (text) => {
              setOptimisticMsg(null)
              window.dispatchEvent(new CustomEvent('edit-message', { detail: { chatId, text } }))
            } : undefined}
          />
        )}
      </AnimatePresence>

      {/* Üretim sırasında olan bitenin canlı zaman çizelgesi (durum + araçlar) */}
      {stream.streaming && activity.length > 0 && (
        <ActivityTimeline items={activity} busy={stream.content === ''} />
      )}

      {/* Durum / İşlem Bildirimi (yükleme vb. — üretim dışı akışlar) */}
      {!stream.streaming && statusMsg && (
        <StatusMessage
          type={statusMsg.type}
          message={statusMsg.message}
          progress={statusMsg.progress}
        />
      )}

      {/* Modelin canlı düşünme süreci (varsa) — saniye sayaçlı */}
      {stream.streaming && stream.thinking && (
        <ThinkingPanel text={stream.thinking} live={stream.content === ''}
                       startedAt={stream.thinkStart} durationMs={stream.thinkMs}
                       className="mb-2 max-w-3xl mx-auto w-full" />
      )}

      {/* "Düşünüyor" göstergesi — henüz hiçbir olay akmadıysa genel bekleme */}
      {stream.streaming && stream.content === '' && !stream.thinking && activity.length === 0 && (
        <StatusMessage
          type="thinking"
          message={stream.queued ? t('chat.queuePosition', { count: stream.queued }) : t('chat.thinking')}
        />
      )}

      {/* Streaming mesaj */}
      {stream.streaming && stream.content && (
        <MessageBubble
          msg={{ role: 'assistant', content: stream.content, tokens: 0 }}
          isStreaming
          onCopy={handleCopy}
        />
      )}

      <div ref={bottomRef} />

      {/* Aşağı kaydır butonu */}
      <AnimatePresence>
        {showScrollBtn && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
            onClick={() => { setAutoScroll(true); bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }}
            className="fixed bottom-24 right-8 p-2.5 rounded-full shadow-lg"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-2)' }}>
            <ChevronDown size={18} />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}
