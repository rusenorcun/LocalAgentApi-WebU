import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, SlidersHorizontal, Database, Download } from 'lucide-react'
import QuickSettings, { isGenParamsModified } from './QuickSettings'
import KnowledgeBase from '../rag/KnowledgeBase'
import { useUIStore } from '../../store/uiStore'
import { lockBodyScroll } from '../../lib/scrollLock'

type Tab = 'settings' | 'kb'

interface Props {
  open: boolean
  onClose: () => void
  chatId?: string
  /** Sohbeti Markdown olarak indir — sohbet yoksa verilmez. */
  onExport?: () => void
}

/**
 * Sağdaki araç paneli: sohbet ayarları + bilgi tabanı + sohbet aksiyonları.
 *
 * Mobilde sağdan kayan bir çekmece, 1024px üstünde ise akışta duran sabit bir
 * sütun (konumlandırma .tools-drawer içinde; bkz. index.css). Daha önce bu
 * işlevler üç ayrı yüzeye dağılmıştı (küçük popover + ayrı bilgi tabanı
 * çekmecesi + "diğer" menüsü); mobilde hepsi ekrandan taşıyordu.
 */
export default function ToolsPanel({ open, onClose, chatId, onExport }: Props) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('settings')
  const genParams = useUIStore((s) => s.genParams)
  const modified = isGenParamsModified(genParams)

  // Çekmece modundayken (lg altı) Esc ile kapansın ve arka plan kaymasın.
  // lg+ ekranda panel akışta duran bir sütun olduğu için kilide gerek yok.
  useEffect(() => {
    if (!open) return
    const overlayMode = !window.matchMedia('(min-width: 1024px)').matches
    const release = overlayMode ? lockBodyScroll() : null
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => {
      release?.()
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  const tabs: { id: Tab; label: string; icon: typeof Database; dot?: boolean }[] = [
    { id: 'settings', label: t('chat.quickSettings.title', 'Ayarlar'), icon: SlidersHorizontal, dot: modified },
    { id: 'kb', label: t('chat.knowledgeBase', 'Bilgi Tabanı'), icon: Database },
  ]

  return (
    <aside className={`tools-drawer flex flex-col ${open ? 'is-open' : ''}`}
           style={{ background: 'var(--surface)' }}
           aria-hidden={!open}>
      <div className="flex items-center justify-between px-3 pt-3 pb-2 shrink-0 pt-safe">
        <span className="text-[12.5px] font-semibold uppercase"
              style={{ color: 'var(--text-3)', letterSpacing: '.06em' }}>
          Araçlar
        </span>
        <button onClick={onClose} title="Paneli kapat"
          className="p-1.5 rounded-lg hover:bg-[var(--surface-2)]"
          style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer' }}>
          <X size={16} />
        </button>
      </div>

      {/* Sekmeler */}
      <div className="flex gap-1 px-3 pb-2 shrink-0">
        {tabs.map(({ id, label, icon: Icon, dot }) => {
          const active = tab === id
          return (
            <button key={id} onClick={() => setTab(id)}
              className="relative flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-[10px] text-[12.5px] font-medium transition-colors"
              style={{
                border: '1px solid ' + (active ? 'transparent' : 'var(--border)'),
                background: active ? 'var(--accent-soft)' : 'transparent',
                color: active ? 'var(--accent)' : 'var(--text-2)',
                cursor: 'pointer',
              }}>
              <Icon size={14} /> {label}
              {dot && !active && (
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--accent)' }} />
              )}
            </button>
          )
        })}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {tab === 'settings' ? <QuickSettings chatId={chatId} /> : <KnowledgeBase />}
      </div>

      {onExport && (
        <div className="p-3 shrink-0 pb-safe" style={{ borderTop: '1px solid var(--border)' }}>
          <button onClick={onExport}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-[13px] font-medium transition-colors hover:bg-[var(--surface-2)]"
            style={{ border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', cursor: 'pointer' }}>
            <Download size={15} /> Markdown indir
          </button>
        </div>
      )}
    </aside>
  )
}
