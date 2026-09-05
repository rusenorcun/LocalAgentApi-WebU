import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save } from 'lucide-react'
import { api } from '../../api/client'

// Her ayar için insan dili etiket + açıklama + grup.
// Bilinmeyen anahtarlar "Gelişmiş" grubunda ham adıyla görünür.
const META: Record<string, { label: string; desc: string; group: string }> = {
  ALLOW_REGISTRATION: {
    label: 'Yeni kayıt',
    desc: 'Yeni kullanıcı hesabı açılabilsin mi? Kullanıcılarını ekledikten sonra KAPAT — internete açık kayıt ekranı bot hesaplara davetiyedir.',
    group: 'Genel',
  },
  MODEL_NAME: {
    label: 'Varsayılan model (ham ad)',
    desc: 'Yeni sohbetlerin başladığı Ollama model adı. Kullanıcıya gösterilen isimler "Modeller" sekmesinden yönetilir.',
    group: 'Genel',
  },
  NUM_CTX: {
    label: 'Bağlam penceresi (token)',
    desc: 'Modele her istekte gönderilen en fazla token. Büyük değer = daha çok hafıza ama daha çok VRAM. 16GB için 8192-32768 arası.',
    group: 'Sohbet ve Bağlam',
  },
  MAX_CHAT_TOKENS: {
    label: 'Sohbet saklama sınırı (token)',
    desc: 'Tek sohbette diskte tutulacak en fazla token. Aşılınca kullanıcıdan yeni sohbet istenir.',
    group: 'Sohbet ve Bağlam',
  },
  ENABLE_COMPACTION: {
    label: 'Otomatik özetleme',
    desc: 'Pencereye sığmayan eski mesajlar modelle özetlenip "sürekli özet" olarak korunur. Uzun sohbetlerde model geçmişi unutmaz.',
    group: 'Sohbet ve Bağlam',
  },
  ENABLE_THINKING: {
    label: 'Düşünme modu (reasoning)',
    desc: 'AÇIK: model nihai cevaptan önce uzun bir <think> bloğu üretir — token/sn aynı kalsa da toplam yanıt süresi belirgin uzar. KAPALI: model doğrudan nihai cevaba geçer, çok daha hızlı yanıt verir. Zor/çok adımlı sorular için açmayı deneyin.',
    group: 'Sohbet ve Bağlam',
  },
  IMAGE_TO_TEXT: {
    label: 'Görsel → metin hattı (önerilen)',
    desc: 'Yüklenen görseller küçük bir VL modeliyle metne dökülür; ana modele yalnızca metin gider. 16GB VRAM için güvenli yöntem.',
    group: 'Dosya ve Görsel',
  },
  CAPTION_MODEL: {
    label: 'Görsel açıklama modeli',
    desc: 'Görselleri metne çeviren küçük model (örn. qwen3-vl:8b). Önce "ollama pull" ile indirilmiş olmalı.',
    group: 'Dosya ve Görsel',
  },
  ENABLE_IMAGE_ANALYSIS: {
    label: 'Doğrudan görsel analizi (riskli)',
    desc: 'Görseller ana modele görüntü olarak gider. Yalnızca "Görsel → metin" KAPALIYKEN devreye girer; 16GB VRAM\'de çökme riski vardır.',
    group: 'Dosya ve Görsel',
  },
  MAX_IMAGES_PER_FILE: {
    label: 'Dosya başına görsel sınırı',
    desc: 'Bir dosyadan işlenecek en fazla görsel sayısı.',
    group: 'Dosya ve Görsel',
  },
  IMAGE_MAX_EDGE: {
    label: 'Görsel küçültme (uzun kenar, px)',
    desc: 'Görseller işlenmeden önce bu boyuta küçültülür. Küçük değer = az VRAM, az detay.',
    group: 'Dosya ve Görsel',
  },
  MIN_IMAGE_EDGE: {
    label: 'Asgari görsel boyutu (px)',
    desc: 'Bundan küçük gömülü görseller (logo, ikon) atlanır; slotlar gerçek şekil/grafiklere kalır.',
    group: 'Dosya ve Görsel',
  },
  MULTIMODAL_NUM_CTX: {
    label: 'Görselli tur bağlamı (token)',
    desc: 'Görsel içeren isteklerde kullanılan küçük bağlam penceresi (vision encoder VRAM yer).',
    group: 'Gelişmiş',
  },
  NUM_GPU: {
    label: 'GPU katman sayısı (0 = otomatik)',
    desc: 'Modelin GPU\'ya yüklenecek katman sayısı. Düşürmek RAM\'e taşırır: yavaş ama VRAM\'de yer açar.',
    group: 'Gelişmiş',
  },
  NUM_GPU_MULTIMODAL: {
    label: 'Görselli tur GPU katmanı (0 = aynı)',
    desc: 'Görselli isteklerde ayrı (daha düşük) GPU katman değeri. NUM_GPU\'dan farklıysa model her geçişte yeniden yüklenir (yavaş).',
    group: 'Gelişmiş',
  },
}

const GROUP_ORDER = ['Genel', 'Sohbet ve Bağlam', 'Dosya ve Görsel', 'Gelişmiş']

export default function SettingsTab() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'settings'],
    queryFn: () => api.get('/api/v2/admin/settings').then(r => r.data),
  })

  const [changes, setChanges] = useState<Record<string, any>>({})
  const [saved, setSaved] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const updateSettings = useMutation({
    mutationFn: () => api.put('/api/v2/admin/settings', { changes }),
    onSuccess: (res) => {
      // Sunucudan donen guncel degerleri cache'e hemen yaz — refresh beklemeden yansisin.
      queryClient.setQueryData(['admin', 'settings'], (old: any) => ({
        ...old,
        settings: res.data.settings,
      }))
      setSaved(true); setErrorMsg(null); setChanges({})
      setTimeout(() => setSaved(false), 2000)
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      const status = err?.response?.status
      setErrorMsg(
        detail ? `Hata (${status}): ${detail}` :
        status ? `Hata: sunucu ${status} döndü.` :
        `Hata: istek sunucuya ulaşamadı (ağ/CORS?).`
      )
    },
  })

  if (isLoading) return <Spinner />

  const current: Record<string, any> = data?.settings ?? {}
  const types: Record<string, string> = data?.types ?? {}
  const restartOnly: string[] = data?.restart_only ?? []

  const val = (k: string) => (k in changes ? changes[k] : current[k])
  const set = (k: string, v: any) => setChanges(s => ({ ...s, [k]: v }))

  // Ayarları gruplara dağıt
  const grouped: Record<string, string[]> = {}
  for (const k of Object.keys(current)) {
    const g = META[k]?.group ?? 'Gelişmiş'
    ;(grouped[g] ??= []).push(k)
  }

  const renderInput = (k: string) => {
    if (types[k] === 'bool') {
      return (
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" checked={!!val(k)} onChange={e => set(k, e.target.checked)}
                 className="w-4 h-4 accent-[var(--accent)]" />
          <span className="text-sm font-medium"
                style={{ color: val(k) ? 'var(--success)' : 'var(--text-3)' }}>
            {val(k) ? 'Açık' : 'Kapalı'}
          </span>
        </label>
      )
    }
    if (types[k] === 'int') {
      return (
        <input type="number" value={val(k) ?? 0} onChange={e => set(k, parseInt(e.target.value))}
          className="px-3 py-1.5 rounded-xl text-sm outline-none w-40"
          style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }} />
      )
    }
    return (
      <input type={k.toLowerCase().includes('secret') || k.toLowerCase().includes('pass') ? 'password' : 'text'}
        value={val(k) ?? ''} onChange={e => set(k, e.target.value)}
        className="px-3 py-1.5 rounded-xl text-sm outline-none w-full max-w-sm"
        style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }} />
    )
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Sistem Ayarları</h1>
        <button onClick={() => updateSettings.mutate()}
          disabled={Object.keys(changes).length === 0}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-opacity disabled:opacity-40 hover:opacity-90"
          style={{ background: saved ? 'var(--success)' : 'var(--accent)', color: 'var(--accent-fg)' }}>
          <Save size={16} />
          {saved ? 'Kaydedildi' : 'Kaydet'}
        </button>
      </div>

      <p className="text-sm mb-6" style={{ color: 'var(--text-3)' }}>
        Değişiklikler kaydedilince anında uygulanır — yeniden başlatma gerekmez.
      </p>

      {errorMsg && (
        <div className="mb-6 px-4 py-3 rounded-xl text-sm"
             style={{ background: 'rgba(239,68,68,.1)', border: '1px solid var(--error)', color: 'var(--error)' }}>
          {errorMsg}
        </div>
      )}

      {GROUP_ORDER.filter(g => grouped[g]?.length).map(g => (
        <div key={g} className="mb-8">
          <h2 className="text-sm font-semibold uppercase tracking-wider mb-3"
              style={{ color: 'var(--text-3)' }}>{g}</h2>
          <div className="flex flex-col gap-3">
            {grouped[g].map(k => (
              <div key={k} className="flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-4 px-4 py-3 rounded-2xl"
                style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium" style={{ color: 'var(--text)' }}>
                    {META[k]?.label ?? k}
                  </p>
                  <p className="text-xs mt-1 leading-relaxed" style={{ color: 'var(--text-3)' }}>
                    {META[k]?.desc ?? ''}
                  </p>
                  <p className="text-[10px] mt-1 font-mono" style={{ color: 'var(--text-3)', opacity: 0.6 }}>{k}</p>
                  {restartOnly.includes(k) && (
                    <p className="text-xs mt-0.5" style={{ color: 'var(--warning)' }}>Yeniden başlatma gerektirir</p>
                  )}
                </div>
                <div className="sm:shrink-0 sm:pt-1">
                  {renderInput(k)}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Spinner() {
  return <div className="flex items-center justify-center h-32" style={{ color: 'var(--text-3)' }}>Yükleniyor…</div>
}
