import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { RotateCcw, AlertTriangle } from 'lucide-react'
import ModelSelector from './ModelSelector'
import { useUIStore, DEFAULT_GEN_PARAMS, type GenParams } from '../../store/uiStore'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getChat, patchChat } from '../../api/chats'

interface Props {
  chatId?: string
}

interface SliderDef {
  key: keyof typeof DEFAULT_GEN_PARAMS
  labelKey: string
  min: number
  max: number
  step: number
  format: (v: number) => string
  warnKey?: string
  warnThreshold?: number
}

const SLIDER_DEFS: SliderDef[] = [
  {
    key: 'num_ctx',
    labelKey: 'chat.quickSettings.numCtx',
    min: 4096,
    max: 131072,
    step: 4096,
    format: (v) => v >= 1024 ? `${Math.round(v / 1024)}K` : String(v),
    warnKey: 'chat.quickSettings.vramWarn',
    warnThreshold: 65536,
  },
  {
    key: 'num_predict',
    labelKey: 'chat.quickSettings.numPredict',
    min: 0,
    max: 16384,
    step: 512,
    format: (v) => v === 0 ? 'Sınırsız' : `${v} tok`,
  },
  {
    key: 'temperature',
    labelKey: 'chat.quickSettings.temperature',
    min: 0,
    max: 2,
    step: 0.05,
    format: (v) => v.toFixed(2),
  },
  {
    key: 'top_p',
    labelKey: 'chat.quickSettings.topP',
    min: 0,
    max: 1,
    step: 0.05,
    format: (v) => v.toFixed(2),
  },
]

/** Üretim parametreleri varsayılandan farklı mı (panel sekmesindeki noktayı sürer). */
export function isGenParamsModified(p: GenParams) {
  return p.num_ctx !== DEFAULT_GEN_PARAMS.num_ctx ||
    p.num_predict !== DEFAULT_GEN_PARAMS.num_predict ||
    p.temperature !== DEFAULT_GEN_PARAMS.temperature ||
    p.top_p !== DEFAULT_GEN_PARAMS.top_p
}

/**
 * Sohbet ayarları — artık kendi açılır kutusu yok; sağdaki araç panelinin
 * (ToolsPanel) "Ayarlar" sekmesi olarak gömülü çalışır. Böylece mobilde
 * ekrandan taşan küçük popover yerine tek bir sağ panel var.
 */
export default function QuickSettings({ chatId }: Props) {
  const { t } = useTranslation()
  const genParams = useUIStore((s) => s.genParams)
  const setGenParams = useUIStore((s) => s.setGenParams)
  const resetGenParams = useUIStore((s) => s.resetGenParams)
  const captionModel = useUIStore((s) => s.captionModel)
  const setCaptionModel = useUIStore((s) => s.setCaptionModel)

  // Sohbete özel persona / sistem promptu
  const qc = useQueryClient()
  const { data: chatData } = useQuery({
    queryKey: ['chat', chatId],
    queryFn: () => getChat(chatId!).then((r) => r.data),
    enabled: !!chatId,
  })
  const [persona, setPersona] = useState('')
  useEffect(() => { setPersona(chatData?.system_prompt || '') }, [chatData?.system_prompt, chatId])
  const savePersona = async () => {
    if (!chatId || persona === (chatData?.system_prompt || '')) return
    try { await patchChat(chatId, { system_prompt: persona }) } catch { /* sessiz */ }
    qc.invalidateQueries({ queryKey: ['chat', chatId] })
  }

  const isModified = isGenParamsModified(genParams)

  return (
    <div className="p-4 space-y-4">

      {chatId && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-1.5"
            style={{ color: 'var(--text-3)' }}>{t('chat.quickSettings.persona')}</p>
          <textarea
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            onBlur={savePersona}
            rows={3}
            placeholder={t('chat.quickSettings.personaPlaceholder')}
            className="w-full text-xs rounded-lg p-2 resize-none outline-none leading-relaxed"
            style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
        </div>
      )}

      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider mb-1.5"
          style={{ color: 'var(--text-3)' }}>{t('chat.quickSettings.captionModel')}</p>
        <div className="rounded-lg p-1" style={{ background: 'var(--surface-2)' }}>
          <ModelSelector
            value={captionModel}
            onChange={(m) => setCaptionModel(m)}
            visionOnly
            includeInternal
            block
          />
        </div>
        <p className="text-[10px] mt-1" style={{ color: 'var(--text-3)' }}>
          {t('chat.quickSettings.captionHint')}
        </p>
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px solid var(--border)' }} />

      {/* Üretim parametreleri */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-3)' }}>{t('chat.quickSettings.genParams')}</p>
          {isModified && (
            <button
              onClick={resetGenParams}
              className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-lg transition-colors hover:bg-[var(--surface-2)]"
              style={{ color: 'var(--text-3)' }}
              title={t('chat.quickSettings.resetTitle')}
            >
              <RotateCcw size={10} /> {t('chat.quickSettings.reset')}
            </button>
          )}
        </div>

        {SLIDER_DEFS.map(({ key, labelKey, min, max, step, format, warnKey, warnThreshold }) => {
          const val = genParams[key] as number
          const warning = warnKey && warnThreshold && val > warnThreshold ? t(warnKey) : null
          return (
            <div key={key}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs" style={{ color: 'var(--text-2)' }}>{t(labelKey)}</span>
                <span className="text-xs font-mono font-medium"
                  style={{ color: val !== DEFAULT_GEN_PARAMS[key] ? 'var(--accent)' : 'var(--text-2)' }}>
                  {format(val)}
                </span>
              </div>
              <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={val}
                onChange={(e) => setGenParams({ [key]: parseFloat(e.target.value) })}
                className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
                style={{ accentColor: 'var(--accent)' }}
              />
              {warning && (
                <p className="flex items-center gap-1 text-[10px] mt-1"
                  style={{ color: 'var(--warning, #f59e0b)' }}>
                  <AlertTriangle size={9} /> {warning}
                </p>
              )}
            </div>
          )
        })}
      </div>

    </div>
  )
}
