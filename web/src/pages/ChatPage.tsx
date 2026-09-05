import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Menu, PanelLeft, PanelRight, Zap } from 'lucide-react'
import MessageList from '../components/chat/MessageList'
import Composer from '../components/chat/Composer'
import CommandPalette from '../components/chat/CommandPalette'
import ToolsPanel from '../components/chat/ToolsPanel'
import Sidebar from '../components/chat/Sidebar'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '../store/uiStore'
import { getChat } from '../api/chats'

export default function ChatPage() {
  const { chatId } = useParams<{ chatId?: string }>()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const chatListOpen = useUIStore((s) => s.sidebarOpen)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const setChatListOpen = useUIStore((s) => s.setSidebarOpen)
  const setMainNavOpen = useUIStore((s) => s.setMainNavOpen)
  const qc = useQueryClient()
  // Sağ araç paneli: sohbet ayarları + bilgi tabanı + dışa aktarma tek yerde.
  const [toolsOpen, setToolsOpen] = useState(false)

  const { data: chat } = useQuery({
    queryKey: ['chat', chatId],
    queryFn: () => getChat(chatId!).then((r) => r.data),
    enabled: !!chatId,
  })

  // Sohbeti Markdown olarak indir (rol başlıkları + içerik).
  const exportChat = () => {
    if (!chat) return
    const lines: string[] = [`# ${chat.title}`, '']
    for (const m of chat.messages || []) {
      if (m.role === 'system' && !m.content.includes('Sistem Özeti')) continue
      const who = m.role === 'user' ? 'Kullanıcı' : m.role === 'assistant' ? 'Asistan' : 'Sistem'
      lines.push(`## ${who}`, '', m.content, '')
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (chat.title || 'sohbet').replace(/[\\/:*?"<>|]/g, '_') + '.md'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex h-[100dvh] overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="flex flex-col flex-1 min-w-0">
        {/* Üst bar: solda gezinme (ana menü + sohbet listesi), ortada başlık,
            sağda tek "Araçlar" düğmesi. */}
        <header className="flex items-center gap-1.5 md:gap-3 px-2.5 md:px-4 min-h-[3.5rem] py-1 shrink-0 border-b pt-safe"
                style={{ background: 'color-mix(in srgb, var(--surface) 70%, transparent)',
                         backdropFilter: 'blur(10px)', borderColor: 'var(--border)' }}>
          {/* Mobilde PanelLayout kendi üst çubuğunu sohbette göstermiyor (100dvh
              çakışması olmasın diye) — ana gezinmeye (Modeller/Ayarlar vb.)
              buradan, paylaşılan mainNavOpen bayrağıyla ulaşılıyor. */}
          <button onClick={() => setMainNavOpen(true)} title="Ana menü" className="md:hidden p-1.5 rounded-lg hover:bg-[var(--surface-2)] shrink-0"
            style={{ color: 'var(--text-2)' }}>
            <PanelLeft size={18} />
          </button>
          <button onClick={toggleSidebar} title="Sohbet listesi"
            className="p-1.5 rounded-lg hover:bg-[var(--surface-2)] shrink-0"
            style={{ color: 'var(--text-2)' }}>
            <Menu size={18} />
          </button>

          <div className="flex-1 min-w-0 flex items-center gap-2">
            {chat && (
              <>
                <p className="text-sm font-bold truncate" style={{ color: 'var(--text)', letterSpacing: '-.01em' }}>
                  {chat.title}
                </p>
                {chat.summarized_count > 0 && (
                  <span className="hidden sm:inline text-[10px] px-1.5 py-0.5 rounded-full shrink-0"
                        style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}
                        {...{ title: t('chat.welcome.summaryCount') }}>
                    ⧉ {chat.summarized_count}
                  </span>
                )}
              </>
            )}
          </div>

          {/* Tek aksiyon: sağdaki araç paneli (ayarlar + bilgi tabanı + indir).
              Her ekran boyutunda aynı yer — mobilde çekmece, geniş ekranda sütun. */}
          <button onClick={() => setToolsOpen((v) => !v)} title="Araçlar"
            className="p-1.5 rounded-lg transition-colors hover:bg-[var(--surface-2)] shrink-0"
            style={{ color: toolsOpen ? 'var(--accent)' : 'var(--text-3)',
                     background: toolsOpen ? 'var(--accent-soft)' : 'transparent' }}>
            <PanelRight size={18} />
          </button>
        </header>

        {/* Mesaj alanı */}
        <div className="flex-1 overflow-hidden flex flex-col chat-page-vt">
          {!chatId ? (
            <WelcomeScreen onNewChat={(id) => navigate(`/chat/${id}`)} />
          ) : (
            <>
              <MessageList chatId={chatId} />
              <Composer chatId={chatId} model={chat?.model}
                        tokenCount={chat?.token_count} maxTokens={chat?.max_tokens}
                        onModelChange={async (model) => {
                          const { patchChat } = await import('../api/chats')
                          await patchChat(chatId!, { model })
                          qc.invalidateQueries({ queryKey: ['chat', chatId] })
                        }}
              />
            </>
          )}
        </div>
      </div>

      {/* Sağ araç paneli — mobilde sağdan kayan çekmece, lg+ ekranda sabit sütun */}
      {toolsOpen && (
        <div className="drawer-scrim is-tools" onClick={() => setToolsOpen(false)} />
      )}
      <ToolsPanel
        open={toolsOpen}
        onClose={() => setToolsOpen(false)}
        chatId={chatId}
        onExport={chatId && chat ? exportChat : undefined}
      />

      {/* Sohbet listesi — masaüstünde PanelLayout'un rayında ("Sohbet" düğmesinin
          altında) gösteriliyor. Sohbet rotasında o ray mobilde ekranda değil,
          o yüzden mobilde aynı chatListOpen bayrağıyla alttan açılan bir sayfa
          (bottom sheet) gösteriyoruz — .sidebar-sheet (index.css) burada devreye giriyor. */}
      <AnimatePresence>
        {chatListOpen && (
          <div className="md:hidden">
            <motion.div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,.5)' }}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setChatListOpen(false)} />
            <motion.div
              className="sidebar-sheet z-50 flex flex-col pb-safe"
              style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)', boxShadow: 'var(--shadow-xl)' }}
              initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }}
              transition={{ type: 'spring', damping: 32, stiffness: 320 }}>
              <div className="flex items-center justify-center pt-2.5 pb-1 shrink-0">
                <div style={{ width: 36, height: 4, borderRadius: 2, background: 'var(--border)' }} />
              </div>
              <div className="flex-1 min-h-0 flex flex-col px-2 pb-2">
                <Sidebar fullHeight />
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Her zaman mount: Ctrl+K dinleyicisi bileşenin içinde */}
      <CommandPalette />
    </div>
  )
}

function WelcomeScreen({ onNewChat }: { onNewChat: (id: string) => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const navigate = useNavigate()
  void onNewChat
  const handleNew = async () => {
    try {
      const { createChat } = await import('../api/chats')
      const res = await createChat('Yeni sohbet')
      if (!res?.data?.id) throw new Error(t('chat.welcome.createFailed'))
      qc.invalidateQueries({ queryKey: ['chats'] })
      navigate(`/chat/${res.data.id}`)
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.message || t('chat.welcome.createFailed'))
    }
  }
  return (
    <div className="relative flex-1 flex flex-col items-center justify-center gap-4 p-8 overflow-hidden">
      {/* NewDesing arka plan efektleri */}
      <div className="absolute inset-0 pointer-events-none"
           style={{ background: 'radial-gradient(circle at 50% 0%, rgba(99,102,241,.14), transparent 60%)' }} />
      <div className="absolute inset-0 pointer-events-none opacity-40 grid-bg" />
      <div className="absolute pointer-events-none"
           style={{ top: -120, left: -80, width: 420, height: 420, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(167,139,250,.3), transparent 70%)',
                    filter: 'blur(20px)', animation: 'floatA 14s ease-in-out infinite' }} />
      <div className="absolute pointer-events-none"
           style={{ bottom: -160, right: -60, width: 480, height: 480, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(99,102,241,.26), transparent 70%)',
                    filter: 'blur(20px)', animation: 'floatB 18s ease-in-out infinite' }} />

      <div className="relative z-10 flex flex-col items-center gap-4 text-center"
           style={{ animation: 'fadeUp .5s both' }}>
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[12.5px] font-medium"
             style={{ border: '1px solid var(--border)', background: 'var(--accent-soft)', color: 'var(--accent)' }}>
          <span data-dot="active" /> {t('chat.welcome.badge', 'Yerel · Gizli · Senin donanımında')}
        </div>
        <div className="grad-text font-bold text-sm uppercase" style={{ letterSpacing: '.08em' }}>
          {t('app.appName')}
        </div>
        <h2 className="text-3xl md:text-4xl font-bold max-w-lg"
            style={{ color: 'var(--text)', letterSpacing: '-.03em', lineHeight: 1.1 }}>
          {t('chat.welcome.title')}
        </h2>
        <p className="text-base max-w-md" style={{ color: 'var(--text-2)' }}>{t('chat.welcome.subtitle')}</p>
        <button onClick={handleNew}
          className="mt-2 px-6 py-3 rounded-xl font-semibold transition-all hover:brightness-110 hover:-translate-y-px inline-flex items-center gap-2"
          style={{ background: 'var(--grad)', color: '#fff', border: 'none', cursor: 'pointer',
                   boxShadow: '0 10px 30px -10px var(--glow)' }}>
          <Zap size={16} /> {t('chat.newChat')}
        </button>
      </div>
    </div>
  )
}
