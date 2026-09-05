import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

type SectionId = 'overview' | 'install' | 'first-model' | 'mcp-connect' | 'tool-writing' | 'rest-api' | 'cli'

const NAV_GROUPS: { title: string; items: { id: SectionId; label: string }[] }[] = [
  { title: 'Başlangıç', items: [
    { id: 'overview', label: 'Genel bakış' },
    { id: 'install', label: 'Kurulum' },
    { id: 'first-model', label: 'İlk model' },
  ] },
  { title: 'MCP', items: [
    { id: 'mcp-connect', label: 'Sunucuyu bağlama' },
    { id: 'tool-writing', label: 'Araç yazma' },
  ] },
  { title: 'Referans', items: [
    { id: 'rest-api', label: 'REST API' },
    { id: 'cli', label: 'CLI komutları' },
  ] },
]

// Ufak yardımcılar — makale içeriğinde tekrar eden desenler (kod bloğu, uyarı kutusu, madde).
function Code({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] p-4 mb-5 text-[13.5px]"
         style={{ background: 'var(--bg)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)', color: 'var(--text-2)', lineHeight: 1.9, whiteSpace: 'pre-wrap', overflowX: 'auto' }}>
      {children}
    </div>
  )
}
function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl px-5 py-[18px] mb-6 flex gap-3.5 items-start"
         style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.7" className="shrink-0 mt-0.5">
        <path d="M13 2L4 14h7l-1 8 9-12h-7z" />
      </svg>
      <div className="text-sm" style={{ color: 'var(--text-2)' }}>{children}</div>
    </div>
  )
}
function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="text-[19px] font-semibold mt-7 mb-3" style={{ color: 'var(--text)' }}>{children}</h3>
}
function P({ children }: { children: React.ReactNode }) {
  return <p className="text-[15px] mb-5" style={{ color: 'var(--text-2)' }}>{children}</p>
}
function Table({ head, rows }: { head: string[]; rows: (string | React.ReactNode)[][] }) {
  return (
    <div className="overflow-x-auto mb-5 rounded-[10px]" style={{ border: '1px solid var(--border)' }}>
      <table className="w-full text-[13.5px]" style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'var(--surface-2)' }}>
            {head.map((h) => (
              <th key={h} className="text-left px-3.5 py-2.5 font-semibold" style={{ color: 'var(--text-2)', borderBottom: '1px solid var(--border)' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderTop: i > 0 ? '1px solid var(--border-2)' : undefined }}>
              {r.map((c, j) => (
                <td key={j} className="px-3.5 py-2.5" style={{ color: j === 0 ? 'var(--text)' : 'var(--text-2)', fontFamily: j === 0 ? 'var(--font-mono)' : undefined }}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const CRUMBS: Record<SectionId, [string, string]> = {
  overview: ['Başlangıç', "LocalAgent'a genel bakış"],
  install: ['Başlangıç', 'Kurulum (Windows)'],
  'first-model': ['Başlangıç', 'İlk modelini indir'],
  'mcp-connect': ['MCP', 'MCP sunucusunu bağlama'],
  'tool-writing': ['MCP', 'Yeni bir araç yazma'],
  'rest-api': ['Referans', 'REST API'],
  cli: ['Referans', 'CLI / betik komutları'],
}

export default function DocsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.accessToken)
  const [section, setSection] = useState<SectionId>('overview')
  const [crumbGroup, crumbTitle] = CRUMBS[section]

  return (
    <div className="min-h-[100dvh]" style={{ background: 'var(--bg)' }}>
      <header className="flex items-center justify-between px-6 md:px-10 py-5" style={{ borderBottom: '1px solid var(--border-2)' }}>
        <button onClick={() => navigate(token ? '/panel' : '/')}
          className="flex items-center gap-2 text-sm font-medium transition-opacity hover:opacity-80"
          style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer' }}>
          <ArrowLeft size={16} /> {token ? 'Panele dön' : 'Ana sayfa'}
        </button>
        <div className="flex items-center gap-2.5">
          <span className="logo-tile" style={{ width: 28, height: 28, fontSize: 12 }}>›_</span>
          <span className="font-bold text-[15px]" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>
            {t('app.appName')}
          </span>
        </div>
      </header>

      <div className="max-w-[1080px] mx-auto px-6 md:px-10 py-10">
        <div className="grid md:grid-cols-[220px_1fr] gap-8 items-start">
          <nav className="flex flex-col gap-0.5 text-[13.5px] md:sticky md:top-6">
            {NAV_GROUPS.map((g) => (
              <div key={g.title}>
                <div className="text-[11px] uppercase font-semibold px-3 pt-3 pb-1.5" style={{ letterSpacing: '.07em', color: 'var(--text-3)' }}>
                  {g.title}
                </div>
                {g.items.map((it) => (
                  <button key={it.id} onClick={() => setSection(it.id)}
                     className="block w-full text-left px-3 py-2 rounded-lg"
                     style={{
                       border: 'none', cursor: 'pointer',
                       color: section === it.id ? 'var(--accent)' : 'var(--text-2)',
                       background: section === it.id ? 'var(--accent-soft)' : 'transparent',
                       fontWeight: section === it.id ? 500 : 400,
                     }}>
                    {it.label}
                  </button>
                ))}
              </div>
            ))}
          </nav>

          <article key={section} className="max-w-[720px]" style={{ lineHeight: 1.7, animation: 'fadeUp .3s both' }}>
            <div className="text-[12.5px] font-semibold uppercase mb-2.5" style={{ letterSpacing: '.06em', color: 'var(--accent)' }}>
              {crumbGroup}
            </div>
            <h2 className="text-[30px] font-bold mb-3.5" style={{ color: 'var(--text)', letterSpacing: '-.02em' }}>
              {crumbTitle}
            </h2>

            {section === 'overview' && (
              <>
                <P>
                  {t('app.appName')}, Ollama üzerinde çalışan yerel dil modellerini kayıtlı kullanıcılara özel
                  sohbet geçmişiyle sunan, tek panelden yönetilen bir sistemdir. Ayrıca bir{' '}
                  <strong style={{ color: 'var(--text)' }}>MCP (Model Context Protocol)</strong> köprüsüyle bu
                  yerel modelleri Claude Desktop / claude.ai'ye de açar. Veritabanı hariç her şey makinende kalır.
                </P>
                <Callout>
                  <strong style={{ color: 'var(--text)' }}>Hızlı başlangıç:</strong> Ollama'yı çalıştır,{' '}
                  <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>call set_env.bat &amp;&amp; run.bat</code>{' '}
                  ile backend'i başlat, panelden bir model indir. Hepsi bu — detaylar "Kurulum" sayfasında.
                </Callout>
                <H3>Temel kavramlar</H3>
                <ul className="pl-5 mb-5 text-[15px]" style={{ color: 'var(--text-2)' }}>
                  <li className="mb-2"><strong style={{ color: 'var(--text)' }}>Modeller</strong> — Ollama üzerinden çalışan yerel LLM'ler. "Modeller" sekmesinden indirilir, belleğe alınır ve varsayılan sohbet modeli seçilir.</li>
                  <li className="mb-2"><strong style={{ color: 'var(--text)' }}>Sohbet içi araçlar</strong> — modelin çağırabileceği fonksiyonlar (hesap makinesi, Python, web arama); her sohbette otomatik etkin.</li>
                  <li className="mb-2"><strong style={{ color: 'var(--text)' }}>MCP relay</strong> — aynı yerel modelleri Claude Desktop/claude.ai'ye açan ayrı bir köprü (bkz. "MCP" bölümü).</li>
                  <li className="mb-2"><strong style={{ color: 'var(--text)' }}>Kullanıcılar</strong> — davetli erişim; roller (admin/üye) "Kullanıcılar" sekmesinden yönetilir.</li>
                  <li className="mb-2"><strong style={{ color: 'var(--text)' }}>API Anahtarları</strong> — kişisel programatik erişim anahtarları oluşturulabilir; Aider ve MCP istemcilerinde kullanılabilir.</li>
                </ul>
                <P>
                  Devam etmek için soldan <strong style={{ color: 'var(--text)' }}>Kurulum</strong>'u aç, ya da
                  doğrudan panele dön ve <strong style={{ color: 'var(--text)' }}>Sohbet</strong>'e başla.
                </P>
              </>
            )}

            {section === 'install' && (
              <>
                <P>Tek makine, Windows üzerinde çalışacak şekilde tasarlandı. Veritabanı SQLite (dosya tabanlı) — ayrı bir DB sunucusu gerekmez.</P>
                <H3>1. Ön koşullar</H3>
                <ul className="pl-5 mb-5 text-[15px]" style={{ color: 'var(--text-2)' }}>
                  <li className="mb-2">Python 3.10+</li>
                  <li className="mb-2">Ollama kurulu ve çalışıyor (<code style={{ fontFamily: 'var(--font-mono)' }}>ollama serve</code>)</li>
                  <li className="mb-2">Node.js (web arayüzünü derlemek için — <code style={{ fontFamily: 'var(--font-mono)' }}>run.bat</code> otomatik yapar)</li>
                </ul>
                <H3>2. Ortam değişkenlerini ayarla</H3>
                <P>
                  <code style={{ fontFamily: 'var(--font-mono)' }}>set_env.example.bat</code> dosyasını{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>set_env.bat</code> olarak kopyala ve doldur.
                  En azından <code style={{ fontFamily: 'var(--font-mono)' }}>JWT_SECRET</code>'i değiştir:
                </P>
                <Code>
                  <div><span style={{ color: 'var(--text-3)' }}># kalıcı, gizli bir anahtar üret</span></div>
                  <div><span style={{ color: 'var(--accent)' }}>$</span> python -c "import secrets; print(secrets.token_urlsafe(48))"</div>
                </Code>
                <H3>3. Başlat</H3>
                <Code>
                  <div><span style={{ color: 'var(--accent)' }}>$</span> call set_env.bat &amp;&amp; run.bat</div>
                </Code>
                <P>
                  İlk çalıştırmada sanal ortam (<code style={{ fontFamily: 'var(--font-mono)' }}>.venv</code>) kurulur,
                  bağımlılıklar (<code style={{ fontFamily: 'var(--font-mono)' }}>requirements.txt</code>) yüklenir ve
                  web arayüzü derlenir (<code style={{ fontFamily: 'var(--font-mono)' }}>web/dist</code> yoksa). Sunucu{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>http://127.0.0.1:9000</code> adresinde ayağa kalkar
                  (port <code style={{ fontFamily: 'var(--font-mono)' }}>set_env.bat</code>'taki <code style={{ fontFamily: 'var(--font-mono)' }}>PORT</code> ile değişir).
                </P>
                <H3>4. İlk kullanıcıyı oluştur</H3>
                <P>Kayıt ekranından normal kayıt olunabilir; admin rolü gerekiyorsa (veya kayıt kapalıysa) doğrudan veritabanına ekle:</P>
                <Code>
                  <div><span style={{ color: 'var(--accent)' }}>$</span> .venv\Scripts\python.exe create_admin.py kullanici_adi GucluBirSifre123</div>
                </Code>
                <Callout>
                  3 kullanıcıyı ekledikten sonra <code style={{ fontFamily: 'var(--font-mono)' }}>set_env.bat</code>{' '}
                  içinde <code style={{ fontFamily: 'var(--font-mono)' }}>ALLOW_REGISTRATION=false</code> yaparak
                  açık kaydı kapat — internete açık bir kayıt ekranı bot hesaplara davetiyedir.
                </Callout>
                <H3>5. Dışarıdan erişim (opsiyonel)</H3>
                <P>
                  Sabit IP'n varsa Caddy ile HTTPS: modemde yalnızca <strong style={{ color: 'var(--text)' }}>443</strong>{' '}
                  portunu bu makineye yönlendir (11434/Ollama asla açılmaz), sonra:
                </P>
                <Code>
                  <div><span style={{ color: 'var(--accent)' }}>$</span> caddy_baslat.bat</div>
                </Code>
              </>
            )}

            {section === 'first-model' && (
              <>
                <P>
                  Varsayılan model <code style={{ fontFamily: 'var(--font-mono)' }}>qwen3.6:35b-a3b-q4_K_M</code>{' '}
                  olarak ayarlıdır (<code style={{ fontFamily: 'var(--font-mono)' }}>set_env.bat</code> içindeki{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>MODEL_NAME</code>). Panelden farklı bir model
                  indirip varsayılan yapmak için:
                </P>
                <H3>Panelden indirme</H3>
                <ul className="pl-5 mb-5 text-[15px]" style={{ color: 'var(--text-2)' }}>
                  <li className="mb-2">Sol menüden <strong style={{ color: 'var(--text)' }}>Modeller</strong>'e gir (admin rolü gerekir).</li>
                  <li className="mb-2">"Sistem / Ollama" kutusuna Ollama model adını yaz (örn. <code style={{ fontFamily: 'var(--font-mono)' }}>qwen2.5:7b-instruct</code>) ve İndir'e bas — ilerleme canlı akar.</li>
                  <li className="mb-2">İndirilen model "Katalog"a manuel eklenip görünen ad/açıklama/hız puanı verilebilir; bu, sohbetteki model seçiciye yansır.</li>
                </ul>
                <H3>Komut satırından indirme</H3>
                <Code>
                  <div><span style={{ color: 'var(--accent)' }}>$</span> ollama pull qwen3-vl:8b   <span style={{ color: 'var(--text-3)' }}># görsel açıklama modeli, dosya yükleme için önerilir</span></div>
                </Code>
                <H3>Hız ayarları (16GB VRAM için)</H3>
                <P>
                  Model bağlam penceresi <code style={{ fontFamily: 'var(--font-mono)' }}>NUM_CTX</code> ile, GPU'ya
                  yüklenecek katman sayısı <code style={{ fontFamily: 'var(--font-mono)' }}>NUM_GPU</code> ile
                  ayarlanır (<code style={{ fontFamily: 'var(--font-mono)' }}>set_env.bat</code>). Ollama'nın kendi
                  hız ayarlarını (flash attention, KV cache) kalıcı yazmak için:
                </P>
                <Code>
                  <div><span style={{ color: 'var(--accent)' }}>$</span> ollama_hiz_ayarlari.bat</div>
                </Code>
              </>
            )}

            {section === 'mcp-connect' && (
              <>
                <P>
                  MCP relay (<code style={{ fontFamily: 'var(--font-mono)' }}>mcp/ollama_mcp.py</code>) yerel
                  modellerini Claude Desktop veya claude.ai'ye araç olarak açar. İki erişim modu var.
                </P>
                <H3>Yerel (stdio) — Claude Desktop</H3>
                <ol className="pl-5 mb-5 text-[15px] list-decimal" style={{ color: 'var(--text-2)' }}>
                  <li className="mb-2">MCP SDK'yı venv'e kur: <code style={{ fontFamily: 'var(--font-mono)' }}>pip install "mcp[cli]"</code></li>
                  <li className="mb-2"><code style={{ fontFamily: 'var(--font-mono)' }}>%APPDATA%\Claude\claude_desktop_config.json</code>'a ekle (hazır kopya: <code style={{ fontFamily: 'var(--font-mono)' }}>mcp/claude_desktop_config.example.json</code>):</li>
                </ol>
                <Code>{`{
  "mcpServers": {
    "yerel-ollama": {
      "command": ".venv\\\\Scripts\\\\python.exe",
      "args": ["mcp\\\\ollama_mcp.py"]
    }
  }
}`}</Code>
                <P>Claude Desktop'ı yeniden başlat — araçlar 🔌 menüsünde görünür. Port/URL yok; Claude betiği ihtiyaç anında kendisi başlatıp kapatır.</P>

                <H3>Uzaktan (HTTP modu) — hazır, VPN gerekmez</H3>
                <P>
                  <code style={{ fontFamily: 'var(--font-mono)' }}>mcp_http_baslat.bat</code> sunucuyu HTTP olarak
                  açar; proje Caddy'si <code style={{ fontFamily: 'var(--font-mono)' }}>/mcp</code> yolunu zaten bu
                  sunucuya HTTPS ile proxy'liyor. Token ilk çalıştırmada otomatik üretilip{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>mcp/.mcp_token</code> içine kaydedilir.
                </P>
                <Code>
                  <div><span style={{ color: 'var(--text-3)' }}># genel adres</span></div>
                  <div>https://rorcun.com/mcp</div>
                </Code>
                <P>İstemci config'i (header destekleyenler için):</P>
                <Code>{`{
  "mcpServers": {
    "yerel-ollama": {
      "url": "https://rorcun.com/mcp",
      "headers": { "Authorization": "Bearer <mcp/.mcp_token icerigi>" }
    }
  }
}`}</Code>
                <P>Yalnız URL girilebilen istemciler (claude.ai custom connector) için token'ı query string'e ekle: <code style={{ fontFamily: 'var(--font-mono)' }}>https://rorcun.com/mcp?token=...</code>. Detaylar için panelde <strong style={{ color: 'var(--text)' }}>MCP Server</strong> sayfasına bak.</P>
              </>
            )}

            {section === 'tool-writing' && (
              <>
                <P>İki ayrı araç sistemi var — birbirine karıştırmamak önemli:</P>
                <ul className="pl-5 mb-5 text-[15px]" style={{ color: 'var(--text-2)' }}>
                  <li className="mb-2"><strong style={{ color: 'var(--text)' }}>Sohbet içi araçlar</strong> (<code style={{ fontFamily: 'var(--font-mono)' }}>server/tools/</code>) — panel sohbetinde modelin otomatik çağırabildiği fonksiyonlar.</li>
                  <li className="mb-2"><strong style={{ color: 'var(--text)' }}>MCP relay araçları</strong> (<code style={{ fontFamily: 'var(--font-mono)' }}>mcp/ollama_mcp.py</code>) — Claude Desktop/claude.ai'nin çağırdığı, ayrı bir süreçte çalışan araçlar.</li>
                </ul>

                <H3>Sohbet içi araç ekleme</H3>
                <P>
                  Yeni bir <code style={{ fontFamily: 'var(--font-mono)' }}>server/tools/xxx_tool.py</code> dosyası
                  yaz, bir <code style={{ fontFamily: 'var(--font-mono)' }}>ToolSpec</code> tanımlayıp{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>register_tool(...)</code> çağır, sonra{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>server/tools/__init__.py</code>'daki import
                  listesine ekle. Gerçek örnek (<code style={{ fontFamily: 'var(--font-mono)' }}>calculator_tool.py</code>, kısaltılmış):
                </P>
                <Code>{`from . import ToolSpec, register_tool

async def _run(args: dict):
    expr = (args or {}).get("expression", "")
    # ... güvenli hesap ...
    return f"{expr} = {sonuc}"

register_tool(ToolSpec(
    name="calculator",
    description="Aritmetik/matematik ifadelerini kesin hesaplar.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "orn '2*(3+4)**2'"}
        },
        "required": ["expression"],
    },
    run=_run,
))`}</Code>
                <P>
                  <code style={{ fontFamily: 'var(--font-mono)' }}>run(args)</code> ya düz bir metin döner (modele
                  gidecek sonuç), ya da <code style={{ fontFamily: 'var(--font-mono)' }}>{'{ "text": ..., "sources": [...] }'}</code>{' '}
                  (arayüzde kaynak göstermek için). Pipeline'ı (<code style={{ fontFamily: 'var(--font-mono)' }}>run_agent_turn</code>) değiştirmene gerek yok.
                </P>

                <H3>MCP relay aracı ekleme</H3>
                <P>
                  <code style={{ fontFamily: 'var(--font-mono)' }}>mcp/ollama_mcp.py</code> içinde{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>@mcp.tool()</code> ile süslenmiş bir async
                  fonksiyon yaz — docstring'i Claude'un aracı ne zaman kullanacağına karar verdiği açıklamadır:
                </P>
                <Code>{`@mcp.tool()
async def yeni_arac(istem: str, baglam: str = "") -> str:
    """Kısa, net açıklama — Claude bunu okuyup ne zaman
    çağıracağına karar verir.

    Args:
        istem: Kullanıcının isteği.
        baglam: (opsiyonel) ek bağlam.
    """
    return await _chat(CHAT_MODEL, istem, system=baglam)`}</Code>
                <P>Claude Desktop'ı yeniden başlatınca yeni araç 🔌 menüsünde görünür; HTTP modunda da otomatik dahil olur.</P>
              </>
            )}

            {section === 'rest-api' && (
              <>
                <P>Tüm uçlar <code style={{ fontFamily: 'var(--font-mono)' }}>/api/v2</code> altında, JWT Bearer token ile korumalı (<code style={{ fontFamily: 'var(--font-mono)' }}>Authorization: Bearer ...</code>). Aşağıdaki gruplar gerçek router'lardan alınmıştır.</P>

                <H3>auth</H3>
                <Table head={['Uç', 'Açıklama']} rows={[
                  ['POST /auth/register', 'Yeni kullanıcı kaydı (açıksa)'],
                  ['POST /auth/login', 'Giriş, access + refresh token döner'],
                  ['POST /auth/refresh', 'httpOnly cookie ile sessiz token yenileme'],
                  ['POST /auth/logout', 'Oturumu kapatır'],
                  ['GET /auth/me', 'Profil bilgisi'],
                  ['PATCH /auth/me/password', 'Şifre değiştir'],
                  ['PATCH /auth/me/preferences', 'Tema/dil/persona tercihleri'],
                ]} />

                <H3>chats</H3>
                <Table head={['Uç', 'Açıklama']} rows={[
                  ['GET/POST /chats', 'Listele / yeni sohbet oluştur'],
                  ['GET /chats/search', 'Sohbet içinde arama'],
                  ['GET/PATCH/DELETE /chats/{id}', 'Getir / yeniden adlandır-sabitle / sil'],
                  ['POST /chats/{id}/messages', 'Mesaj gönder (SSE stream yanıt)'],
                  ['POST /chats/{id}/regenerate', 'Son yanıtı yeniden üret'],
                  ['POST /chats/{id}/stop', 'Üretimi sunucu tarafında durdur'],
                  ['POST /chats/{id}/compact', 'Eski mesajları özetleyip sıkıştır'],
                  ['POST /chats/{id}/truncate', 'Bir mesajdan itibaren geçmişi kes'],
                  ['POST /chats/{id}/select-branch', 'Düzenlenmiş mesaj dallarından birini seç'],
                  ['POST/DELETE /chats/{id}/upload', 'Dosya ekle / eki kaldır'],
                  ['POST /chats/batch-summarize', 'Birden çok sohbeti özetle'],
                ]} />

                <H3>models</H3>
                <Table head={['Uç', 'Açıklama']} rows={[
                  ['GET /models', 'Kullanıcıya gösterilen model listesi'],
                  ['GET/POST /models/admin', 'Katalog listele / yeni model ekle (admin)'],
                  ['PATCH/DELETE /models/admin/{id}', 'Model düzenle / sil (admin)'],
                  ['GET /models/admin/status', 'Diskte + bellekte yüklü Ollama modelleri'],
                  ['POST /models/admin/pull', 'Ollama\'dan model indir (SSE ilerleme)'],
                  ['POST /models/admin/uninstall', 'Diskten model sil'],
                  ['POST /models/admin/retune', 'Otomatik hız/VRAM ayarını yeniden hesapla'],
                ]} />

                <H3>admin</H3>
                <Table head={['Uç', 'Açıklama']} rows={[
                  ['GET /admin/users', 'Kullanıcı listesi'],
                  ['PATCH /admin/users/{id}/role', 'Rol değiştir (admin/üye)'],
                  ['POST /admin/users/{id}/unlock', 'Brute-force kilidini aç'],
                  ['DELETE /admin/users/{id}/sessions', 'Kullanıcının oturumlarını kapat'],
                  ['DELETE /admin/users/{id}', 'Kullanıcıyı sil'],
                  ['GET /admin/stats', 'Genel istatistikler (Genel Bakış sayfası bunu kullanır)'],
                  ['GET /admin/audit', 'Audit log / olay kayıtları'],
                  ['GET/PUT /admin/settings', 'Sistem geneli ayarlar (NUM_CTX, ALLOW_REGISTRATION, ...)'],
                ]} />

                <H3>projects, rag, summaries</H3>
                <Table head={['Uç', 'Açıklama']} rows={[
                  ['GET/POST /projects', 'Proje çalışma alanları listele / oluştur'],
                  ['POST/DELETE /projects/{id}/chats/{chatId}', 'Sohbeti projeye ekle / çıkar'],
                  ['GET/POST/DELETE /projects/{id}/documents', 'Proje belgeleri'],
                  ['GET/POST /rag/documents', 'Bilgi tabanı belgeleri listele / yükle'],
                  ['POST /rag/query', 'Bilgi tabanında anlamsal arama'],
                  ['GET/DELETE /summaries', 'Sohbet özetlerini listele / sil'],
                ]} />
              </>
            )}

            {section === 'cli' && (
              <>
                <P>Ayrı bir "localagent" ikili dosyası yok — proje, Windows'ta çift-tıkla veya terminalden çalıştırılan `.bat`/Python betikleriyle yönetiliyor.</P>
                <Table head={['Komut', 'Ne yapar']} rows={[
                  [<>run.bat</>, 'Ana giriş noktası: venv kurar, bağımlılıkları yükler, web arayüzünü derler (gerekirse), FastAPI\'yi başlatır.'],
                  [<>start.bat</>, 'run.bat\'ı BUILD=1 ile çağırır — frontend\'i her seferinde yeniden derler.'],
                  [<>start_dev.bat</>, 'Geliştirme modu: FastAPI --reload + Vite dev server (5173) ayrı pencerelerde.'],
                  [<>caddy_baslat.bat</>, 'Yalnızca Caddy\'yi (HTTPS reverse proxy) başlatır; zaten çalışıyorsa ikinci kopya açmaz.'],
                  [<>mcp_http_baslat.bat</>, 'MCP relay\'i HTTP modunda başlatır, token\'ı otomatik üretir/okur.'],
                  [<>ollama_hiz_ayarlari.bat</>, 'Ollama hız ortam değişkenlerini (flash attention, KV cache) kalıcı yazar.'],
                  [<>create_admin.py &lt;kullanici&gt; &lt;sifre&gt;</>, 'Veritabanına doğrudan admin kullanıcı ekler/günceller.'],
                  [<>create_tables.py</>, 'Veritabanı tablolarını (SQLAlchemy modelleri) sıfırdan oluşturur.'],
                ]} />
                <H3>Ortam değişkenleri (set_env.bat)</H3>
                <Table head={['Değişken', 'Varsayılan', 'Açıklama']} rows={[
                  ['JWT_SECRET', '—', 'Zorunlu, sabit gizli anahtar'],
                  ['PORT', '9000', 'Backend portu (Caddyfile ile aynı olmalı)'],
                  ['MODEL_NAME', 'qwen3.6:35b-a3b-q4_K_M', 'Varsayılan sohbet modeli'],
                  ['NUM_CTX', '8192', 'Modele giden bağlam penceresi'],
                  ['MAX_CHAT_TOKENS', '250000', 'Sohbet başına saklama sınırı'],
                  ['ALLOW_REGISTRATION', 'false', 'Yeni kayıt açık/kapalı'],
                  ['IMAGE_TO_TEXT', 'true', 'Görselleri küçük VL modeliyle metne çevir (16GB için önerilen)'],
                ]} />
              </>
            )}
          </article>
        </div>
      </div>
    </div>
  )
}
