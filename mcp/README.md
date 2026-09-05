# Yerel Ollama MCP Sunucusu

Claude Desktop / Cowork içinden **tamamen yerel** modellere delegasyon:
Claude konuşmayı yönetir, ağır işi yerel modeller yapar (veri dışarı çıkmaz).

## Araçlar

| Araç | Model/Kaynak | Ne için |
|------|--------------|---------|
| `genel_sohbet` | `qwen3.6:35b-a3b-q4_K_M` | Genel sohbet, soru-cevap, yazım, özet |
| `derin_analiz` | `gpt-oss:120b` | Derin muhakeme, çok adımlı analiz (**yavaş** — dakikalar sürebilir) |
| `kod_yaz` | `qwen3-coder:30b` | Kod üretimi/refactor |
| `web_ara` | DuckDuckGo (`ddgs`) | Güncel web araması — haber/fiyat/sürüm gibi konular |
| `yerel_sohbet` | istediğiniz model | Herhangi bir modelle tek atımlık üretim (model adı doğrulanır) |
| `modelleri_listele` | — | Disk + bellek model durumu |

## Sağlık kontrolü (/healthz)

HTTP modunda token'sız `GET /healthz` ucu vardır:

```json
{ "status": "ok", "service": "yerel-ollama-mcp", "ollama": true, "tools": 6 }
```

`ollama` alanı Ollama'nın erişilebilir olduğunu gösterir. Panel
(Admin → MCP Server) bu ucu 10 saniyede bir yoklar.

## Kurulum

1. Üç model de kurulu (`ollama list` ile doğrulayın).
2. MCP SDK'yı projenin venv'ine kurun (`requirements.txt` artık `mcp[cli]`
   içerir; run.bat taze kurulumda otomatik kurar). Elle kurmak için:
   ```
   C:\Project\LocalAgentApi-WebU - OpenCode\.venv\Scripts\pip install "mcp[cli]"
   ```
3. Claude Desktop yapılandırmasına ekleyin —
   `%APPDATA%\Claude\claude_desktop_config.json` (yolları KENDİ proje
   klasörünüze göre düzeltin):
   ```json
   {
     "mcpServers": {
       "yerel-ollama": {
         "command": "C:\\Project\\LocalAgentApi-WebU - OpenCode\\.venv\\Scripts\\python.exe",
         "args": ["C:\\Project\\LocalAgentApi-WebU - OpenCode\\mcp\\ollama_mcp.py"],
         "env": {
           "OLLAMA_HOST": "http://127.0.0.1:11434",
           "MCP_REASONER_MODEL": "gpt-oss:120b",
           "MCP_CODER_MODEL": "qwen3-coder:30b"
         }
       }
     }
   }
   ```
   (Hazır kopya: `claude_desktop_config.example.json`)
4. Claude Desktop'ı yeniden başlatın. Araçlar 🔌 menüsünde görünür.

## Erişim modları

### Yerel (varsayılan — stdio)
Sunucu sürekli çalışmaz; Claude Desktop, config'deki komutu ihtiyaç anında
alt süreç olarak başlatır ve kapatır. Port/URL yoktur. Yukarıdaki kurulum
bunun içindir — başka bir şey çalıştırmanız gerekmez.

### Uzaktan (HTTP modu) — KURULU VE HAZIR

`mcp_http_baslat.bat` sunucuyu Streamable HTTP olarak açar ve **Caddy zaten
bu iş için hazırlanmış durumda** (bkz. proje kökündeki `Caddyfile`,
`handle /mcp /mcp/*` bloğu). VPN/Tailscale/port yönlendirme GEREKMEZ —
zaten açık olan 443 portu üzerinden, kimlik doğrulama (MCP_TOKEN) ile korunur:

```
Genel adres:  https://rorcun.com/mcp
Yerel adres:  http://127.0.0.1:8765/mcp   (yalnızca bu makineden)
```

`MCP_HOST` daima `127.0.0.1` kalır — port 8765 hiçbir zaman dışarı açılmaz;
dışarıdan tek erişim yolu Caddy'nin HTTPS ile sonlandırdığı `/mcp` yoludur.

### Kimlik doğrulama (MCP_TOKEN) — OTOMATİK

Kullanıcı kaydı/oturum sistemi gerekmez — tek sahipli servis için standart
çözüm statik API anahtarıdır. `mcp_http_baslat.bat` artık bunu **otomatik**
yapıyor: ilk çalıştırmada bir anahtar üretilip `mcp/.mcp_token` dosyasına
kaydedilir, sonraki her çalıştırmada aynı anahtar okunur (istemci config'i
bozulmaz) ve terminale genel adres + anahtar birlikte yazdırılır. Anahtarı
değiştirmek için `mcp/.mcp_token` dosyasını silip `.bat`'ı yeniden çalıştırmanız
yeterli — bu dosyayı paylaşmayın/versiyon kontrolüne eklemeyin.

`MCP_TOKEN` doluyken sunucu anahtarsız her isteği 401 ile reddeder.
127.0.0.1 dışına anahtarsız açılmaya çalışılırsa hiç başlamaz (fail-fast) —
bu ekstra bir güvenlik ağı, normal kullanımda tetiklenmez çünkü host zaten
127.0.0.1'de kalıyor.

İstemci tarafı — iki yol (ikisi de `.bat` çıktısında hazır yazılı gelir):

1. **Header destekleyen istemciler** (Claude Desktop remote URL):
   ```json
   { "mcpServers": { "yerel-ollama": {
       "url": "https://rorcun.com/mcp",
       "headers": { "Authorization": "Bearer BURAYA_TOKEN" } } } }
   ```
2. **Yalnız URL girilebilen istemciler** (claude.ai custom connector):
   token'ı URL'e query parametresi olarak ekleyin:
   ```
   https://rorcun.com/mcp?token=BURAYA_TOKEN
   ```

Notlar: Trafik uçtan uca Caddy'nin HTTPS'i içinde taşındığı için anahtar
düz metin olarak ağda dolaşmaz. Anahtar sızarsa `mcp/.mcp_token` dosyasını
silip sunucuyu yeniden başlatmanız yeterli — yeni anahtar üretilir.

## Panel yönetimi (Admin → MCP Server)

Artık `.bat`'a gerek yok — web panelinden yönetilir (yalnızca admin):

| Uç | İş |
|----|----|
| `GET /api/v2/mcp/status` | Çalışıyor/healthy/pid + maskeli token (10 sn'de bir otomatik yenilenir) |
| `POST /api/v2/mcp/start` | Relay'i alt süreç olarak başlatır; log `data/mcp_server.log`'a yazılır |
| `POST /api/v2/mcp/stop?force=true` | Durdurur. `force=true`: `.bat` ile başlatılmış dış örneği de düşürür |
| `GET /api/v2/mcp/token` | Tam anahtar (istemci config'i için) |
| `GET /api/v2/mcp/tools` | Sohbet-içi araçlar (REGISTRY) + relay'in CANLI tools/list çıktısı |

Panel ile başlatılan süreç "managed", `.bat` ile başlanan "external"
görünür; ikisi de aynı `mcp/.mcp_token` dosyasını kullandığı için istemci
config'i değişmez.

## Notlar

- **gpt-oss:120b hızı:** 16 GB VRAM'de model büyük ölçüde CPU'da çalışır
  (~64 GB RAM önerilir). `derin_analiz` çağrıları dakikalar sürebilir; Claude
  aracı beklemeye devam eder. Hız isterseniz `MCP_REASONER_MODEL=gpt-oss:20b`.
- **Kuyruk çekişmesi:** Web arayüzü ile MCP aynı Ollama'yı kullanır; aynı anda
  iki büyük istek birbirini bekletir/model takası yaratır.
- Modelleri değiştirmek için config'teki `env` bölümünü düzenleyip Claude
  Desktop'ı yeniden başlatmanız yeterli.
