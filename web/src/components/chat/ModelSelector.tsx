import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Zap, Star, Eye } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { getModels } from '../../api/models'

interface Props {
  value: string
  onChange: (model: string) => void
  /** Açılır listenin yönü — composer yanında 'up' kullanılır */
  direction?: 'up' | 'down'
  /** Sadece vision modelleri göster */
  visionOnly?: boolean
  /** Dahili (internal) modelleri de göster (caption seçimi için) */
  includeInternal?: boolean
  /** Dar paneller için tam genişlik tetikleyici + taşmayan açılır menü */
  block?: boolean
}

export default function ModelSelector({ value, onChange, direction = 'down', visionOnly = false, includeInternal = false, block = false }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: ['models', includeInternal],
    queryFn: () => getModels(includeInternal),
  })
  const models = data?.data?.models ?? []
  // Eşleşen model; değer boşsa ve dahili modeller dahilse varsayılan caption (dahili görü) gösterilir.
  const current =
    models.find((m: any) => m.ollama_name === value || m.display_name === value) ??
    ((!value && includeInternal)
      ? models.find((m: any) => m.is_vision && m.internal) ?? null
      : null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const speedDots = (speed: number) =>
    Array.from({ length: 5 }, (_, i) => (
      <span key={i} className="rounded-full"
        style={{ width: 5, height: 5,
                 background: i < speed ? 'var(--accent)' : 'var(--text-3)',
                 opacity: i < speed ? 1 : 0.4 }} />
    ))

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(v => !v)}
        className={`flex items-center gap-2 px-3 py-1.5 text-[13px] font-medium transition-colors hover:bg-[var(--surface-2)] ${block ? 'w-full justify-between' : ''}`}
        style={{ color: 'var(--text)', border: '1px solid var(--border)', background: 'var(--surface)',
                 borderRadius: 9, cursor: 'pointer' }}>
        <span className={block ? 'flex items-center gap-2 min-w-0' : 'contents'}>
          <span data-dot="active" />
          {current?.is_vision && <Eye size={12} style={{ color: 'var(--accent)' }} />}
          <span className="max-w-[160px] truncate">{current?.display_name ?? value}</span>
        </span>
        <ChevronDown size={13} className="transition-transform"
                     style={{ color: 'var(--text-3)', transform: open ? 'rotate(180deg)' : 'none' }} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: direction === 'up' ? 8 : -8 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: direction === 'up' ? 8 : -8 }}
            transition={{ duration: 0.15 }}
            className={`absolute z-50 overflow-hidden ${
              direction === 'up' ? 'bottom-full mb-2' : 'top-full mt-2'} ${
              block ? 'left-0 right-0' : `w-[344px] max-w-[86vw] ${direction === 'up' ? 'left-0' : 'right-0'}`}`}
            style={{ background: 'var(--surface)', border: '1px solid var(--border)',
                     borderRadius: 14, boxShadow: 'var(--shadow-xl)' }}>
            <div className="max-h-[340px] overflow-y-auto">
              {models.filter((m: any) => (includeInternal || !m.internal) && (!visionOnly || m.is_vision)).map((m: any) => {
                const isActive = (m.ollama_name ?? m.display_name) === value
                return (
                <button key={m.id ?? m.display_name} onClick={() => { onChange(m.ollama_name ?? m.display_name); setOpen(false) }}
                  className="block w-full text-left transition-colors hover:bg-[var(--surface-2)]"
                  style={{ padding: '11px 13px', border: 'none', cursor: 'pointer',
                           borderBottom: '1px solid var(--border-2)',
                           background: isActive ? 'var(--accent-soft)' : 'transparent' }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                      {m.display_name}
                    </span>
                    {m.is_default && <Star size={12} fill="var(--warning)" style={{ color: 'var(--warning)' }} />}
                    {m.is_vision && (
                      <span {...{ title: t('chat.modelSelector.visionBadge') }}
                        className="flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                        style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
                        <Eye size={9} /> Vision
                      </span>
                    )}
                    <span className="ml-auto inline-flex items-center gap-1">
                      <span className="flex gap-[3px]">{speedDots(m.speed ?? 3)}</span>
                      <Zap size={11} style={{ color: 'var(--text-3)' }} />
                    </span>
                  </div>
                  {m.description && (
                    <p className="text-xs line-clamp-2 leading-relaxed" style={{ color: 'var(--text-2)' }}>{m.description}</p>
                  )}
                </button>
              )})}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
