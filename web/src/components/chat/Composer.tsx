import { useRef, useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, Paperclip, Square, X, FileStack, Globe, Plus, Check } from 'lucide-react'
import ModelSelector from './ModelSelector'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useUIStore } from '../../store/uiStore'
import { useAuthStore } from '../../store/authStore'
import { uploadFile, clearUpload } from '../../api/chats'
import { api } from '../../api/client'
import { expandSlash, matchSlash } from '../../lib/slashCommands'

interface Props {
  chatId: string
  model?: string
  tokenCount?: number
  maxTokens?: number
  onModelChange?: (model: string) => void
}

interface UploadedFile {
  name: string
  num_images: number
  text_chars: number
  mode: string
}

export default function Composer({ chatId, model, tokenCount = 0, maxTokens = 250000, onModelChange }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  // Seçili sohbet modeli bir görü modeli mi? (öyleyse caption atlanır, görsel doğrudan gider)
  const { data: _modelsResp } = useQuery({ queryKey: ['models', false], queryFn: () => import('../../api/models').then(m => m.getModels(false)) })
  const chatModelIsVision = (_modelsResp?.data?.models || []).some((m: any) => m.ollama_name === model && m.is_vision)
  // Seçici abonelik: drafts objesine abone OLMA — her tuşta gereksiz render zinciri doğar
  const setDraft = useUIStore((s) => s.setDraft)
  const globalMaxTokens = useUIStore((s) => s.globalMaxTokens)
  const genParams = useUIStore((s) => s.genParams)
  const setGenParams = useUIStore((s) => s.setGenParams)
  const injectedAttachment = useUIStore((s) => s.injectedAttachment)
  const setInjectedAttachment = useUIStore((s) => s.setInjectedAttachment)
  const [text, setText] = useState(() => useUIStore.getState().getDraft(chatId))
  const [streaming, setStreaming] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [webSearch, setWebSearch] = useState(false)
  const [compacting, setCompacting] = useState(false)
  const [showTokenSettings, setShowTokenSettings] = useState(false)
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false)
  const [attachment, setAttachment] = useState<UploadedFile | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const editIdRef = useRef<number | null>(null)  // düzenlenen mesaj id'si (truncate için)
  const stopTimerRef = useRef<number | null>(null)  // durdurma güvenlik ağı zamanlayıcısı

  // Yüksekliği ayarla
  const autoResize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }, [])

  useEffect(() => { autoResize() }, [text, autoResize])

  // Taslak kaydet
  useEffect(() => {
    setDraft(chatId, text)
  }, [chatId, text, setDraft])

  // Edit mesajı gelince doldur
  useEffect(() => {
    const handler = (e: Event) => {
      const { chatId: cid, text: t, messageId } = (e as CustomEvent).detail
      if (cid === chatId) {
        setText(t)
        editIdRef.current = typeof messageId === 'number' ? messageId : null
        textareaRef.current?.focus()
      }
    }
    window.addEventListener('edit-message', handler)
    return () => window.removeEventListener('edit-message', handler)
  }, [chatId])

  // Streaming olaylarını dinle
  useEffect(() => {
    const handler = (e: Event) => {
      const ev = (e as CustomEvent).detail
      if (ev.chatId !== chatId) return
      if (ev.type === 'start') setStreaming(true)
      if (ev.type === 'done' || ev.type === 'error') {
        setStreaming(false)
        // Durdurma güvenlik ağı zamanlayıcısını iptal et — akış düzgün kapandı
        if (stopTimerRef.current != null) {
          window.clearTimeout(stopTimerRef.current)
          stopTimerRef.current = null
        }
      }
    }
    window.addEventListener('chat-stream', handler)
    return () => window.removeEventListener('chat-stream', handler)
  }, [chatId])

  // Injected attachment kontrolü
  useEffect(() => {
    if (injectedAttachment) {
      setAttachment(injectedAttachment)
      setInjectedAttachment(null)
    }
  }, [injectedAttachment, setInjectedAttachment])

  // Token göstergesi
  const currentMaxTokens = genParams.num_ctx || globalMaxTokens || maxTokens
  const tokenPct = currentMaxTokens > 0 ? tokenCount / currentMaxTokens : 0
  const ringColor = tokenPct > 0.95 ? 'var(--error)' : tokenPct > 0.8 ? 'var(--warning)' : 'var(--accent)'

  // Ortak SSE akış yardımcısı — hem gönderme hem yeniden üretme kullanır
  // Ortak SSE akış okuyucu: hem mesaj gönderme hem "yeniden üret" kullanır.
  // Sunucudan gelen her `data: {...}` satırını JSON'a çevirip global `chat-stream`
  // CustomEvent'i olarak yayınlar; MessageList bu olayları dinleyip UI'yı günceller.
  const streamFrom = async (url: string, body?: object) => {
    abortRef.current = new AbortController()
    setStreaming(true)

    window.dispatchEvent(new CustomEvent('chat-stream', {
      detail: { chatId, type: 'start' }
    }))

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${_getToken()}`,
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: abortRef.current.signal,
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Hata' }))
        window.dispatchEvent(new CustomEvent('chat-stream', {
          detail: { chatId, type: 'error', message: err.detail }
        }))
        return
      }

      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.type === 'compacted') {
              window.dispatchEvent(new CustomEvent('chat-stream', {
                detail: { chatId, type: 'status', status: 'summarizing', message: t('chat.status.summarized') }
              }))
            }
            window.dispatchEvent(new CustomEvent('chat-stream', { detail: { ...ev, chatId } }))
          } catch {}
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        window.dispatchEvent(new CustomEvent('chat-stream', {
          detail: { chatId, type: 'error', message: t('chat.status.connectionError') }
        }))
      }
    }
    setStreaming(false)
    setAttachment(null)
  }

  // Mesaj gönderme: önce optimistik kullanıcı balonu gösterilir (anında geri bildirim),
  // sonra payload (içerik + üretim parametreleri + varsa görü modeli) ile SSE başlatılır.
  const sendMessage = async () => {
    let content = expandSlash(text.trim())
    if (!content && !attachment) return
    if (streaming) return
    
    if (!content && attachment) {
      content = `[Dosya eklendi: ${attachment.name}]`
    }

    // Mesaj düzenleme (DALLANMA): eski dal SİLİNMEZ — düzenlenen içerik, o mesajın
    // KARDEŞİ olarak eklenir. Eski dal "‹ i/n ›" ile geri gelebilir (veri kaybı yok).
    const _editId = editIdRef.current
    editIdRef.current = null

    setText('')
    setDraft(chatId, '')
    const tempId = crypto.randomUUID()
    window.dispatchEvent(new CustomEvent('chat-stream', {
      detail: { chatId, type: 'optimistic-user', content, tempId }
    }))
    const { num_predict, temperature, top_p, num_ctx: storeCtx } = useUIStore.getState().genParams
    // Görsel varsa ve sohbet modeli zaten görü modeliyse override gerekmez; görsel
    // doğrudan sohbet modeline gider (caption atlanmıştır).
    const payload: any = {
      content,
      web_search: webSearch,
      num_ctx: storeCtx,
      temperature,
      top_p,
    }
    // num_predict yalnızca açık bir sınır seçildiyse gönderilir; 0 = sınırsız (EOS'a kadar).
    if (num_predict && num_predict > 0) payload.num_predict = num_predict
    if (_editId != null) payload.edit_message_id = _editId

    await streamFrom(`/api/v2/chats/${chatId}/messages`, payload)
  }

  // "Yeniden üret" olayını dinle (MessageList'teki buton tetikler)
  useEffect(() => {
    const handler = (e: Event) => {
      const { chatId: cid } = (e as CustomEvent).detail
      if (cid !== chatId || streaming) return
      streamFrom(`/api/v2/chats/${chatId}/regenerate`)
    }
    window.addEventListener('regenerate', handler)
    return () => window.removeEventListener('regenerate', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatId, streaming])

  // Durdur: sunucuya /stop gönderilir → backend Ollama akışını GERÇEKTEN keser,
  // o ana kadarki kısmi çıktıyı DB'ye kaydeder ve stream'i 'done' ile kapatır
  // (kuyruktaki sıradaki istek hemen başlar). Yerel abort yalnızca güvenlik
  // ağıdır: sunucu makul sürede kapatmazsa bağlantı yerelde kesilir.
  const stopGeneration = async () => {
    const finishLocally = () => {
      abortRef.current?.abort()
      window.dispatchEvent(new CustomEvent('chat-stream', { detail: { chatId, type: 'done' } }))
    }
    try {
      await api.post(`/api/v2/chats/${chatId}/stop`)
      if (stopTimerRef.current != null) window.clearTimeout(stopTimerRef.current)
      stopTimerRef.current = window.setTimeout(() => {
        stopTimerRef.current = null
        finishLocally()
      }, 5000)
    } catch {
      // Sunucuya ulaşılamadı — eski davranışa düş (yerel iptal)
      finishLocally()
    }
  }

  const manualCompact = async () => {
    if (!chatId || compacting) return
    setCompacting(true)
    try {
      await api.post(`/api/v2/chats/${chatId}/compact`)
      qc.invalidateQueries({ queryKey: ['chat', chatId] })
    } catch { /* sessiz */ }
    setCompacting(false)
  }

  // Dosya yükleme: backend SSE stream döndürür (aşama aşama ilerleme). Burada stream
  // okunur, her `progress` olayı durum bildirimine, `done` olayı ek önizlemeye çevrilir.
  // `finally` ile `uploading` bayrağı her durumda kapanır (asılı kalma bug'ı önlenir).
  const handleFile = async (file: File) => {
    if (file.size > 40 * 1024 * 1024) {
      alert(t('chat.composer.fileTooBig', { max: 40 }))
      return
    }
    setUploading(true)
    
    // Yükleme başlıyor bildirimi
    window.dispatchEvent(new CustomEvent('chat-stream', {
      detail: { chatId, type: 'status', status: 'uploading', message: t('chat.status.uploading'), progress: 0 }
    }))
    
    try {
      const form = new FormData()
      form.append('file', file)
      
      const captionModel = useUIStore.getState().captionModel
      const _params = new URLSearchParams()
      // Sohbet modeli görü modeliyse görsel DOĞRUDAN ona gider (caption devre dışı).
      if (chatModelIsVision) _params.set('direct_vision', 'true')
      else if (captionModel) _params.set('caption_model', captionModel)
      const qs = _params.toString() ? `?${_params.toString()}` : ''

      const resp = await fetch(`/api/v2/chats/${chatId}/upload${qs}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${_getToken()}` },
        body: form
      })
      
      if (!resp.ok) throw new Error(t('chat.status.uploadError'))
      
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.type === 'progress') {
              const pct = ev.total > 0 ? Math.round((ev.current / ev.total) * 100) : undefined
              window.dispatchEvent(new CustomEvent('chat-stream', {
                detail: { chatId, type: 'status', status: 'processing', message: ev.message, progress: pct }
              }))
            } else if (ev.type === 'done') {
              setAttachment(ev.result)
              window.dispatchEvent(new CustomEvent('chat-stream', {
                detail: { chatId, type: 'status', status: 'success', message: t('chat.status.fileReady') }
              }))
            } else if (ev.type === 'error') {
              throw new Error(ev.message)
            }
          } catch (e) {
            // parse error
          }
        }
      }
    } catch (err: any) {
      alert(err.message || t('chat.status.uploadFailed'))
      window.dispatchEvent(new CustomEvent('chat-stream', {
        detail: { chatId, type: 'status-clear' }
      }))
    } finally {
      setUploading(false)
    }
  }

  const removeAttachment = async () => {
    await clearUpload(chatId).catch(() => {})
    setAttachment(null)
  }

  const onPaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile()
        if (file) handleFile(file)
      }
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="px-2 md:px-4 pt-2 pb-[max(1.5rem,env(safe-area-inset-bottom))] md:pb-8"
         onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
         onDragLeave={() => setDragOver(false)}
         onDrop={onDrop}>
      <div className="max-w-3xl mx-auto">
        {/* Dosya eki önizleme */}
        <AnimatePresence>
          {attachment && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
              className="flex items-center gap-2 mb-2 px-3 py-2 rounded-xl"
              style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
              <span className="text-sm truncate flex-1" style={{ color: 'var(--text)' }}>
                📎 {attachment.name}
                <span className="ml-2 text-xs" style={{ color: 'var(--text-3)' }}>
                  {attachment.num_images > 0 ? `${attachment.num_images} ${t('chat.attachment.images')} · ` : ''}
                  {attachment.text_chars > 0 ? `${attachment.text_chars} ${t('chat.attachment.chars')}` : ''}
                </span>
                {attachment.num_images > 5 && (
                  <div className="text-[10px] mt-1" style={{ color: 'var(--warning)' }}>
                    {t('chat.attachment.longDocWarn')}
                  </div>
                )}
              </span>
              <button onClick={removeAttachment} className="p-1 rounded" style={{ color: 'var(--text-3)' }}>
                <X size={14} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Sürükle-bırak overlay */}
        <AnimatePresence>
          {dragOver && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 flex items-center justify-center rounded-2xl z-10 pointer-events-none"
              style={{ background: 'color-mix(in srgb, var(--accent) 15%, transparent)',
                       border: '2px dashed var(--accent)' }}>
              <p className="text-sm font-medium" style={{ color: 'var(--accent)' }}>
                {t('chat.composer.dropFile')}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Slash komut önerileri */}
        {matchSlash(text).length > 0 && !streaming && (
          <div className="mb-2 rounded-xl border overflow-hidden"
               style={{ borderColor: 'var(--border)', background: 'var(--surface)', boxShadow: 'var(--shadow-md)' }}>
            {matchSlash(text).map((cmd) => (
              <button key={cmd.cmd}
                onClick={() => { setText(`/${cmd.cmd} `); textareaRef.current?.focus() }}
                className="w-full flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--surface-2)]">
                <span className="text-sm font-mono" style={{ color: 'var(--accent)' }}>{cmd.label}</span>
                <span className="text-xs" style={{ color: 'var(--text-3)' }}>{cmd.desc}</span>
              </button>
            ))}
          </div>
        )}

        {/* Model seçici ve Mobilde Üste Taşınan Butonlar */}
        <div className="flex items-center justify-between mb-1.5 gap-2">
          {onModelChange ? (
            <ModelSelector
              value={model ?? ''}
              onChange={onModelChange}
              direction="up"
            />
          ) : <div />}

          {/* Mobilde: dosya ekle / web araması / özetle tek "+" menüsünde toplanır —
              önceki sürümde 5 ayrı ikon yan yana ekrana sığmaya çalışıyordu. */}
          <div className="flex items-center gap-1 md:hidden shrink-0">
            <div className="relative">
              <button onClick={() => setMobileToolsOpen((v) => !v)}
                className="flex items-center justify-center rounded-lg shrink-0 transition-colors hover:bg-[var(--surface-2)]"
                style={{ color: mobileToolsOpen ? 'var(--accent)' : 'var(--text-2)', height: '32px', width: '32px' }}>
                <Plus size={18} style={{ transform: mobileToolsOpen ? 'rotate(45deg)' : 'none', transition: 'transform .15s' }} />
                {webSearch && !mobileToolsOpen && (
                  <span className="absolute top-0.5 right-0.5 w-[7px] h-[7px] rounded-full"
                        style={{ background: 'var(--accent)' }} />
                )}
              </button>
              <AnimatePresence>
                {mobileToolsOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setMobileToolsOpen(false)} />
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.96 }}
                      transition={{ duration: 0.13 }}
                      className="absolute bottom-full left-0 mb-2 w-52 py-1.5 rounded-xl z-50 shadow-lg origin-bottom-left"
                      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                      <button onClick={() => { fileInputRef.current?.click(); setMobileToolsOpen(false) }} disabled={uploading}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors hover:bg-[var(--surface-2)] disabled:opacity-50"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text)' }}>
                        <Paperclip size={15} /> {t('chat.composer.attachFile')}
                      </button>
                      <button onClick={() => setWebSearch((v) => !v)}
                        className="w-full flex items-center justify-between gap-2.5 px-3 py-2 text-sm text-left transition-colors hover:bg-[var(--surface-2)]"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: webSearch ? 'var(--accent)' : 'var(--text)' }}>
                        <span className="flex items-center gap-2.5"><Globe size={15} /> {t('chat.webSearch')}</span>
                        {webSearch && <Check size={14} />}
                      </button>
                      <button onClick={() => { manualCompact(); setMobileToolsOpen(false) }} disabled={compacting}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors hover:bg-[var(--surface-2)] disabled:opacity-50"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text)' }}>
                        <FileStack size={15} className={compacting ? 'animate-spin' : ''} /> {t('chat.compactHint')}
                      </button>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>

            {streaming ? (
              <button onClick={stopGeneration} className="flex items-center justify-center transition-colors hover:brightness-110" style={{ color: '#fff', background: 'var(--error)', border: 'none', borderRadius: '50%', height: '32px', width: '32px', cursor: 'pointer' }}>
                <Square size={14} fill="currentColor" />
              </button>
            ) : (
              <button onClick={sendMessage} disabled={uploading} className="flex items-center justify-center transition-opacity disabled:opacity-40 hover:brightness-110" style={{ background: 'var(--grad)', color: '#fff', border: 'none', borderRadius: '50%', height: '32px', width: '32px', cursor: 'pointer' }}>
                <Send size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Ana giriş alanı — items-end: Metin büyüdükçe butonlar altta kalsın */}
        <div className="relative flex items-end gap-1.5 p-2 md:px-2.5"
             style={{ background: 'var(--surface)', border: '1px solid var(--border)',
                      borderRadius: 14, boxShadow: 'var(--shadow-md)' }}>

          {/* Sol Butonlar (Sadece Masaüstü) */}
          <div className="hidden md:flex items-center gap-1 shrink-0">
            <button onClick={() => fileInputRef.current?.click()} disabled={uploading}
              className="flex items-center justify-center p-2 rounded-xl shrink-0 transition-colors hover:bg-[var(--surface-2)]"
              style={{ color: uploading ? 'var(--text-3)' : 'var(--text-2)', height: '36px', width: '36px' }}
              title={t('chat.composer.attachFile')}>
              <Paperclip size={18} />
            </button>

            <button
              onClick={() => setWebSearch(v => !v)}
              onMouseDown={(e) => e.preventDefault()}
              className="flex items-center justify-center p-2 rounded-xl shrink-0 transition-colors hover:bg-[var(--surface-2)]"
              style={{ color: webSearch ? 'var(--accent)' : 'var(--text-2)',
                       background: webSearch ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent', height: '36px', width: '36px' }}
              title={t('chat.webSearch')}>
              <Globe size={18} />
            </button>
          </div>
          <input ref={fileInputRef} type="file" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => { setText(e.target.value); autoResize() }}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            placeholder={t('chat.composer.placeholder')}
            rows={1}
            className="flex-1 resize-none text-sm bg-transparent outline-none leading-relaxed py-1.5"
            style={{ color: 'var(--text)', minHeight: '24px', maxHeight: '200px' }}
            disabled={streaming}
          />

          {/* Sağ Butonlar (Sadece Masaüstü) */}
          <div className="hidden md:flex items-center gap-2 shrink-0">
            {/* Özetle butonu */}
            <button onClick={manualCompact} disabled={compacting}
              className="flex items-center justify-center p-1.5 md:p-2 rounded-xl transition-colors hover:bg-[var(--surface-2)] disabled:opacity-50"
              style={{ height: '36px', width: '36px', color: compacting ? 'var(--accent)' : 'var(--text-3)' }}
              title={t('chat.compactHint')}>
              <FileStack size={16} className={compacting ? 'animate-spin' : ''} />
            </button>

            {/* Token göstergesi */}
            {tokenCount > 0 && (
              <div 
                className="relative flex items-center" 
                onMouseEnter={() => setShowTokenSettings(true)}
                onMouseLeave={() => setShowTokenSettings(false)}
              >
                <svg width="28" height="28" viewBox="0 0 28 28" className="shrink-0 cursor-pointer">
                  <circle cx="14" cy="14" r="11" fill="none" stroke="var(--border)" strokeWidth="2" />
                  <circle cx="14" cy="14" r="11" fill="none" stroke={ringColor} strokeWidth="2"
                    strokeDasharray={`${2 * Math.PI * 11}`}
                    strokeDashoffset={`${2 * Math.PI * 11 * (1 - tokenPct)}`}
                    strokeLinecap="round"
                    transform="rotate(-90 14 14)"
                    style={{ transition: 'stroke-dashoffset 0.5s, stroke 0.3s' }} />
                </svg>

                <AnimatePresence>
                  {showTokenSettings && (
                    <motion.div
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 5 }}
                      className="absolute bottom-full right-0 mb-3 p-3 rounded-xl shadow-lg border w-56 z-50 cursor-default"
                      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
                    >
                      {/* Kullanım özeti */}
                      <div className="mb-2.5">
                        <div className="flex items-center justify-between text-xs font-semibold" style={{ color: ringColor }}>
                          <span>{Math.round(tokenPct * 100)}% {t('chat.tokenInfo.used')}</span>
                          <span>{(currentMaxTokens / 1024).toFixed(0)}K {t('chat.tokenInfo.contextWindow')}</span>
                        </div>
                        <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-3)' }}>
                          {tokenCount.toLocaleString('tr-TR')} / {currentMaxTokens.toLocaleString('tr-TR')} token
                        </div>
                      </div>

                      {/* Divider */}
                      <div className="mb-2.5" style={{ borderTop: '1px solid var(--border)' }} />

                      {/* Slider */}
                      <div className="flex items-center justify-between text-xs mb-1" style={{ color: 'var(--text-2)' }}>
                        <span>{t('chat.quickSettings.numCtx')}</span>
                        <span className="font-mono" style={{ color: 'var(--accent)' }}>
                          {(currentMaxTokens / 1024).toFixed(0)}K
                        </span>
                      </div>
                      <input
                        type="range"
                        min="4096"
                        max="131072"
                        step="4096"
                        value={currentMaxTokens}
                        onChange={(e) => setGenParams({ num_ctx: parseInt(e.target.value) })}
                        className="w-full cursor-pointer"
                        style={{ accentColor: 'var(--accent)' }}
                      />
                      <div className="text-[10px] flex justify-between opacity-50 mt-0.5" style={{ color: 'var(--text)' }}>
                        <span>4K</span><span>128K</span>
                      </div>

                      {/* Uyarı */}
                      {currentMaxTokens > 65536 && (
                        <div className="flex items-start gap-1 text-[10px] mt-2"
                          style={{ color: 'var(--warning, #f59e0b)' }}>
                          <span>⚠️</span>
                          <span>{t('chat.tokenInfo.vramWarn')}</span>
                        </div>
                      )}

                      {/* ⚙️ ipucu */}
                      <div className="text-[10px] mt-2 pt-2" style={{ borderTop: '1px solid var(--border)', color: 'var(--text-3)' }}>
                        ⚙️ {t('chat.tokenInfo.settingsHint')}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            {streaming ? (
              <button onClick={stopGeneration}
                className="flex items-center justify-center transition-colors hover:brightness-110"
                style={{ color: '#fff', background: 'var(--error)', border: 'none', borderRadius: '50%',
                         height: '36px', width: '36px', cursor: 'pointer' }} title={t('chat.stop')}>
                <Square size={15} fill="currentColor" />
              </button>
            ) : (
              <button onClick={sendMessage} disabled={(!text.trim() && !attachment) || uploading}
                className="flex items-center justify-center transition-all disabled:opacity-40 hover:brightness-110"
                style={{ background: (text.trim() || attachment) && !uploading ? 'var(--grad)' : 'var(--surface-2)',
                         color: (text.trim() || attachment) && !uploading ? '#fff' : 'var(--text-3)',
                         border: 'none', borderRadius: '50%', height: '36px', width: '36px', cursor: 'pointer',
                         boxShadow: (text.trim() || attachment) && !uploading ? '0 6px 18px -6px var(--glow)' : 'none' }}
                title={t('chat.composer.send')}>
                <Send size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// DÜZELTME: accessToken artık (G2 güvenlik değişikliğinden beri) localStorage'da
// DEĞİL, yalnızca zustand store'un belleğinde tutuluyor — bu yüzden token'ı
// canlı store'dan okumak gerekiyor. Eskiden localStorage'dan okunuyordu ve daima
// boş dönüyordu; bu da fetch() ile atılan mesaj/dosya isteklerinin sunucu
// tarafından 401 ile reddedilmesine (mesajların hiç gitmemesine) yol açıyordu.
function _getToken(): string {
  return useAuthStore.getState().accessToken || ''
}
