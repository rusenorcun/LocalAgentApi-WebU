# Raft Tabanlı Dağıtık Key-Value Store — 2 Kişilik Proje Planı

> Amaç: Java ile, sıfırdan, Raft konsensüs algoritması üzerine kurulu, 3–5 node'lu, çökmeye dayanıklı bir key-value store yazmak. Ürün çıkarmak değil; altyapı yazmış, test etmiş ve anlatabilen iki mühendis olmak.

---

## 0. Bittiğinde elimizde ne olacak?

Proje "bitti" demek için şu beşi aynı anda sağlanmalı:

1. `docker compose up` ile 3 node ayağa kalkıyor, istemci `put`/`get` yapabiliyor.
2. Lider `kill -9` ile öldürülünce 1 saniye içinde yeni lider seçiliyor, onaylanmış hiçbir yazı kaybolmuyor.
3. Deterministik simülasyon testi 10.000 farklı seed ile Raft'ın 5 güvenlik kuralını ihlal etmeden geçiyor.
4. 24 saatlik kaos koşusu (rastgele node öldürme, ağ bölme, disk yavaşlatma) sonunda linearizability kontrolü temiz çıkıyor.
5. README'de 60 saniyelik demo, mimari diyagram, benchmark sonuçları ve tasarım kararlarını anlatan ADR'ler var.

Bu beş madde CV'deki tek satırın arkasındaki kanıttır. Mülakatta "kodu göster" dendiğinde açılacak şey bunlar.

---

## 1. Kapsam

### Yapılacaklar
- Raft: lider seçimi, log replikasyonu, commit, snapshot + log kırpma, tek-sunucu üyelik değişikliği, ReadIndex ile linearizable okuma
- Depolama: segmentli WAL (write-ahead log), bellek içi tablo, snapshot dosya formatı
- Ağ: gRPC ile node'lar arası RPC ve istemci API'si
- İstemci: Java kütüphanesi + CLI, lider yönlendirme, retry, tekrar-güvenli (idempotent) istekler
- Test: deterministik simülasyon, kaos düzeneği, linearizability kontrolü
- Gözlem: Prometheus metrikleri, React izleme paneli
- Belge: README, ADR'ler, benchmark raporu, blog yazısı

### Yapılmayacaklar (kapsam kaymasına karşı — bunlara "hayır" deyin)
- Multi-Raft / sharding (tek Raft grubu yeter)
- Transaction, ikincil indeks, sorgu dili
- TLS, kimlik doğrulama
- Kubernetes operator
- LSM/SSTable compaction (opsiyonel Faz 3+ bonusudur; olmazsa bellek içi tablo + snapshot yeterli)

---

## 2. Teknoloji seçimleri

| Alan | Seçim | Neden |
|---|---|---|
| Dil | Java 21 (LTS) | İkiniz de biliyorsunuz; yeni dil + zor konu riski ikiye katlar. Virtual thread ve record'lar işi kolaylaştırır. |
| Build | Gradle (Kotlin DSL), çok modüllü | Modül sınırları iş bölümüne birebir oturur. |
| RPC | gRPC + Protobuf | Sözleşme dosyada, iki kişi paralel çalışabilir. Netty gRPC'nin altında zaten gelir. |
| Raft çekirdeği | Saf Java, framework yok | Test edilebilirlik. Spring Boot çekirdeğe girmez. |
| Yönetim API'si | Spring Boot (sadece `/admin`, `/metrics`) | Bildiğiniz araç, panel için yeter. |
| Metrik | Micrometer → Prometheus | Standart, Grafana ile de okunur. |
| Test | JUnit 5, AssertJ, jqwik (property-based) | jqwik rastgele girdi üretip invariant bozan senaryoyu küçültür. |
| Log | SLF4J + Logback | Standart. |
| Panel | React + TypeScript + Vite | Beko'nun alanı, ayrı klasör, ayrı build. |
| Yerel küme | Docker Compose | Kaos testleri ve demo için 3–5 konteyner. |
| Kaos | Toxiproxy (ağ) + kendi harness'ınız (süreç) | Toxiproxy gecikme/kesinti enjekte eder; süreç öldürmeyi kendiniz yazarsınız. |
| CI | GitHub Actions | Ücretsiz, yeterli. |
| Lisans | Apache-2.0 | Altyapı projelerinin standardı. |

---

## 3. Mimari

### 3.1 Bileşenler

```
                 ┌─────────────────────────────────────────┐
                 │               İstemci (CLI / lib)       │
                 │  put/get/delete, lider yönlendirme,     │
                 │  retry, clientId+seq ile tekrar güvenli │
                 └───────────────┬─────────────────────────┘
                                 │ gRPC KvService
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│    Node 1     │◄──────►│    Node 2     │◄──────►│    Node 3     │
│  (lider)      │  gRPC  │  (takipçi)    │  gRPC  │  (takipçi)    │
│               │ Raft   │               │ Raft   │               │
│ ┌───────────┐ │ Service│ ┌───────────┐ │ Service│ ┌───────────┐ │
│ │ RaftNode  │ │        │ │ RaftNode  │ │        │ │ RaftNode  │ │
│ │ (tek iş   │ │        │ │           │ │        │ │           │ │
│ │  parçacığı)│ │        │ │           │ │        │ │           │ │
│ └─────┬─────┘ │        │ └─────┬─────┘ │        │ └─────┬─────┘ │
│       │ apply │        │       │       │        │       │       │
│ ┌─────▼─────┐ │        │ ┌─────▼─────┐ │        │ ┌─────▼─────┐ │
│ │KvStateMach│ │        │ │KvStateMach│ │        │ │KvStateMach│ │
│ └───────────┘ │        │ └───────────┘ │        │ └───────────┘ │
│ ┌───────────┐ │        │ ┌───────────┐ │        │ ┌───────────┐ │
│ │ WAL + HS  │ │        │ │ WAL + HS  │ │        │ │ WAL + HS  │ │
│ │ (disk)    │ │        │ │ (disk)    │ │        │ │ (disk)    │ │
│ └───────────┘ │        │ └───────────┘ │        │ └───────────┘ │
│  /admin /metrics        │  /admin /metrics        │  /admin /metrics
└───────────────┘        └───────────────┘        └───────────────┘
        ▲                        ▲                        ▲
        └────────────────────────┴────────────────────────┘
                          React izleme paneli (HTTP)
```

HS = HardState (currentTerm, votedFor). Her node aynı kodu çalıştırır; rol (lider/takipçi/aday) çalışma zamanında değişir.

### 3.2 Gradle modülleri

```
raft-kv/
├── raft-core/        Raft durum makinesi. Saf Java. Ağ ve disk BİLMEZ; arayüz üzerinden konuşur.
├── storage/          WAL, HardState, snapshot dosyaları, KvStateMachine.
├── transport-grpc/   .proto dosyaları, gRPC sunucu/istemci, Transport arayüzünün gerçek implementasyonu.
├── server/           Her şeyi birleştiren çalıştırılabilir uygulama + Spring Boot admin/metrics.
├── client/           Java istemci kütüphanesi + CLI.
├── sim-test/         Deterministik simülasyon: sahte ağ, sahte saat, invariant kontrolleri.
├── chaos/            Docker Compose + Toxiproxy senaryoları, linearizability kontrolcüsü.
├── bench/            Yük üreteci ve ölçüm raporu.
└── dashboard/        React + TS panel (ayrı npm projesi).
```

Kural: `raft-core` yalnızca `java.base`'e bağımlıdır. gRPC, dosya sistemi, Spring; hiçbiri oraya giremez. Bu kural tüm testin temelidir.

### 3.3 Raft durumu (paper Figure 2 ile birebir)

Kalıcı (diske yazılmadan RPC'ye cevap verilmez):
- `currentTerm`, `votedFor`, `log[]` (her entry: `term`, `index`, `command`)

Uçucu (her node):
- `commitIndex`, `lastApplied`

Uçucu (sadece lider):
- `nextIndex[peer]`, `matchIndex[peer]`

Zamanlayıcılar:
- Seçim zaman aşımı: rastgele 150–300 ms (yerel Docker için 300–600 ms başlayın)
- Heartbeat: seçim zaman aşımının en az 1/3'ü (50 ms / 100 ms)

Seçim zamanlayıcısı **sadece** şu üç durumda sıfırlanır (en çok hata yapılan yer):
1. Mevcut liderden geçerli `AppendEntries` alınca (term kontrolü geçen)
2. Yeni seçim başlatınca
3. Bir adaya oy verince

### 3.4 RPC sözleşmeleri

`transport-grpc/src/main/proto/raft.proto`

```proto
syntax = "proto3";
package raft;

service RaftService {
  rpc RequestVote(RequestVoteRequest) returns (RequestVoteResponse);
  rpc AppendEntries(AppendEntriesRequest) returns (AppendEntriesResponse);
  rpc InstallSnapshot(stream InstallSnapshotChunk) returns (InstallSnapshotResponse);
}

message LogEntry {
  uint64 term = 1;
  uint64 index = 2;
  bytes command = 3;   // serileştirilmiş KvCommand (put/delete/config-change/noop)
}

message RequestVoteRequest {
  uint64 term = 1;
  string candidate_id = 2;
  uint64 last_log_index = 3;
  uint64 last_log_term = 4;
}
message RequestVoteResponse {
  uint64 term = 1;
  bool vote_granted = 2;
}

message AppendEntriesRequest {
  uint64 term = 1;
  string leader_id = 2;
  uint64 prev_log_index = 3;
  uint64 prev_log_term = 4;
  repeated LogEntry entries = 5;
  uint64 leader_commit = 6;
}
message AppendEntriesResponse {
  uint64 term = 1;
  bool success = 2;
  // hızlı geri sarma (fast backup) için ipuçları
  uint64 conflict_index = 3;
  uint64 conflict_term = 4;
}

message InstallSnapshotChunk {
  uint64 term = 1;
  string leader_id = 2;
  uint64 last_included_index = 3;
  uint64 last_included_term = 4;
  uint64 offset = 5;
  bytes data = 6;
  bool done = 7;
}
message InstallSnapshotResponse { uint64 term = 1; }
```

`transport-grpc/src/main/proto/kv.proto`

```proto
service KvService {
  rpc Put(PutRequest) returns (PutResponse);
  rpc Get(GetRequest) returns (GetResponse);
  rpc Delete(DeleteRequest) returns (DeleteResponse);
}

message ClientHeader {
  string client_id = 1;   // istemci başlarken üretir
  uint64 seq = 2;         // her yazma isteğinde artar; lider aynı (client_id, seq) çiftini iki kez uygulamaz
}

message PutRequest    { ClientHeader h = 1; bytes key = 2; bytes value = 3; }
message PutResponse   { Status status = 1; string leader_hint = 2; }
message GetRequest    { bytes key = 1; bool linearizable = 2; }
message GetResponse   { Status status = 1; bytes value = 2; bool found = 3; string leader_hint = 4; }
message DeleteRequest { ClientHeader h = 1; bytes key = 2; }
message DeleteResponse{ Status status = 1; string leader_hint = 2; }

enum Status { OK = 0; NOT_LEADER = 1; TIMEOUT = 2; UNAVAILABLE = 3; }
```

İstemci davranışı: `NOT_LEADER` gelirse `leader_hint`'e yönlen; `TIMEOUT` gelirse aynı `seq` ile tekrar dene (lider dedup yapar, iki kez uygulanmaz).

### 3.5 Depolama

**WAL (write-ahead log)**
- 64 MB'lık segment dosyaları: `wal-000001.log`, `wal-000002.log` ...
- Kayıt formatı: `[len:u32][crc32c:u32][term:u64][index:u64][type:u8][payload]`
- Append → `fsync` → sonra RPC'ye cevap. Faz 4'te batch fsync (10 ms pencerede biriktir) eklenir.
- Açılışta kurtarma: segmentleri sırayla oku, CRC bozuk kayda gelince orada kes (yarım yazılmış kuyruk normaldir).
- `truncateFrom(index)`: çakışan entry'leri silmek için (takipçi tarafında).

**HardState**: `hardstate.bin` içinde `currentTerm` + `votedFor`; her değişimde fsync. Tek küçük dosya, atomik yazım için `tmp + rename`.

**State machine**: `ConcurrentSkipListMap<byte[], byte[]>` (sıralı olması snapshot'ı kolaylaştırır). Ayrıca `lastApplied` ve dedup tablosu `Map<clientId, (seq, response)>` state machine'in parçasıdır ki snapshot'a girsin.

**Snapshot**: `snap-<lastIncludedIndex>-<term>.bin` → header + tüm map + dedup tablosu. Yazıldıktan sonra o index'e kadar WAL segmentleri silinir.

### 3.6 İş parçacığı modeli (en kritik tasarım kararı)

Tek bir **Raft iş parçacığı** vardır. Tüm durum değişimleri sadece onun üstünde olur. Herkes ona olay (event) yollar:

```
gRPC thread ──► queue.put(AppendEntriesReceived(...))
timer thread ─► queue.put(ElectionTimeout)                 ┌──────────────┐
client thread ► queue.put(ClientCommand(cmd, future))  ──► │ Raft thread  │ ──► transport.send(...)
                                                            │ (loop)       │ ──► log.append(...)
                                                            └──────────────┘ ──► stateMachine.apply(...)
```

Neden: kilit yok, yarış durumu yok, simülasyonda aynı olay sırasını tekrar üretebiliyorsunuz. Performans için ileride disk yazması ayrı thread'e taşınabilir (pipelining) ama Faz 4'e kadar dokunmayın.

### 3.7 Modül arayüzleri (iki kişinin sözleşmesi — 1. haftada yazılıp dondurulur)

`raft-core` bu dört arayüzü tanımlar, gerçek implementasyonlar başka modüllerde yaşar:

```java
public interface RaftLog {
    long lastIndex();
    long lastTerm();
    long termAt(long index);                       // 0 ise yok
    void append(List<LogEntry> entries);           // dönmeden önce dayanıklı olmalı
    void truncateFrom(long index);                 // index ve sonrasını sil
    List<LogEntry> slice(long fromInclusive, long toExclusive);
    void saveHardState(long currentTerm, String votedFor);
    HardState loadHardState();
    void compactTo(long index);                    // snapshot sonrası
}

public interface StateMachine {
    byte[] apply(LogEntry entry);                  // deterministik olmalı
    Snapshot takeSnapshot(long lastIncludedIndex, long lastIncludedTerm);
    void restore(Snapshot snapshot);
}

public interface Transport {
    void send(String toNodeId, RaftMessage message);       // asenkron, kaybolabilir
    void onReceive(Consumer<RaftMessage> handler);
}

public interface Clock {
    long nowMillis();
    void schedule(Runnable task, long delayMillis);         // simülasyonda sahte saat
}
```

`raft-core` içindeki `RaftNode` sadece bu arayüzleri görür. `sim-test` hepsinin bellek içi sahtesini verir; `storage` ve `transport-grpc` gerçeğini verir. Bu sayede:
- Kişi A, disk ve ağ yokken Raft'ı sonuna kadar test edebilir.
- Kişi B, Raft bitmeden WAL'ı ve gRPC'yi tek başına test edebilir.

---

## 4. İş bölümü

İki ayrı "sahiplik alanı" var. Kim hangisini alır siz seçin; panel yazacak kişi B'yi alsın (React tarafı orada).

| | Kişi A — Raft çekirdeği ve doğruluk | Kişi B — Depolama, ağ, istemci, gözlem |
|---|---|---|
| Modüller | `raft-core`, `sim-test` | `storage`, `transport-grpc`, `client`, `server`, `dashboard` |
| Faz 1 | RaftNode iskeleti, term/rol geçişleri, bellek içi log ile tek node apply döngüsü | WAL + kurtarma, HardState, KvStateMachine, gRPC KvService, CLI |
| Faz 2 | RequestVote, AppendEntries, commit kuralı, log eşleme, fast backup, simülasyon harness'ı | gRPC RaftService transport, küme config, istemci yönlendirme/retry, dedup, Docker Compose |
| Faz 3 | InstallSnapshot, tek-sunucu üyelik değişikliği, ReadIndex | Snapshot dosya formatı, WAL kırpma, metrikler, (bonus) SSTable |
| Faz 4 | Linearizability kontrolcüsü, kaos senaryoları | React panel, admin API, Toxiproxy entegrasyonu, Grafana |
| Faz 5 | Benchmark analizi, ADR'ler | Benchmark yük üreteci, README, demo videosu |
| Ortak | `chaos/`, `bench/`, blog yazısı, her PR'da karşılıklı review | |

Kural: sınırı geçen her değişiklik (arayüz değişimi) PR'da ikinizin de onayını alır.

---

## 5. Zaman planı — 16 hafta

Varsayım: kişi başı haftada ~15 saat. Daha az zaman varsa faz sürelerini uzatın, fazları atlamayın.

### Faz 0 — Kurulum (Hafta 1)
- [ ] İkiniz de Raft makalesini (extended version, 18 sayfa) baştan sona okuyun, Figure 2'yi çıktı alıp duvara asın
- [ ] thesecretlivesofdata.com/raft görselleştirmesini birlikte izleyin
- [ ] GitHub repo, Gradle çok modüllü iskelet, CI (build + test), README taslağı
- [ ] `.proto` dosyaları ve §3.7 arayüzleri yazılır, PR ile ikiniz onaylar
- [ ] ADR-001: "Tek Raft iş parçacığı" kararı yazılır
- **Kabul**: `./gradlew build` yeşil, CI yeşil, boş modüller yerinde

### Faz 1 — Tek node (Hafta 2–3)
- A: `RaftNode` tek node modunda kendini lider sayar, komutları loga yazar, apply eder
- B: WAL yaz/oku/kurtar, bozuk kuyruk testi, KvStateMachine, gRPC ile `put/get`, CLI
- **Kabul**: tek node'a 10.000 put; süreç `kill -9`; yeniden başlat; hepsi `get` ile okunuyor. WAL testi: son kayıt yarım yazılmış dosya düzgün kurtarılıyor.

### Faz 2 — Seçim ve replikasyon (Hafta 4–7) — en zor faz
- A, hafta 4–5: RequestVote + seçim; hafta 6–7: AppendEntries, commit, çakışma çözümü, fast backup
- A, paralel: `sim-test` harness (sahte transport: kayıp/gecikme/sıra bozma/bölünme; sahte saat; seed ile tekrar üretilebilir)
- B: gerçek transport, `cluster.yaml`, istemci lider yönlendirme + retry + dedup, 3 node Docker Compose
- **Kabul**:
  - 3 node ayakta; lider `kill -9` → yeni lider < 1 s; onaylı veri kaybı 0
  - Simülasyon: 1.000 seed × 5 node, 5 güvenlik invariant'ı ihlalsiz
  - Aynı `(clientId, seq)` iki kez gönderilince state machine bir kez uyguluyor

Beş güvenlik invariant'ı (her simülasyon adımında kontrol edilir):
1. Election Safety: bir term'de en fazla bir lider
2. Leader Append-Only: lider kendi logundan hiç silmez
3. Log Matching: iki logda aynı index+term varsa öncesi de aynıdır
4. Leader Completeness: commit edilmiş entry, sonraki tüm liderlerin logundadır
5. State Machine Safety: hiçbir iki node aynı index'e farklı komut uygulamaz

### Faz 3 — Snapshot, kırpma, üyelik (Hafta 8–10)
- A: InstallSnapshot RPC; tek-sunucu ekle/çıkar (joint consensus değil, Ongaro'nun tezindeki basit yöntem); ReadIndex ile linearizable `get`
- B: snapshot dosya formatı, WAL `compactTo`, Micrometer metrikleri, `/admin/status` endpoint'i
- **Kabul**: 1M entry sonrası disk boyutu sınırlı; geride kalan node snapshot ile yetişiyor; 3→4→5→3 node değişikliği canlı trafikte hatasız

### Faz 4 — Kaos, doğruluk, panel (Hafta 11–14)
- A: istemci geçmişini kaydeden ve register modeline göre linearizability kontrol eden araç; kaos senaryoları (bölünme, asimetrik bölünme, saat kayması, yavaş disk, SIGSTOP ile donan lider)
- B: React panel (her node'un rolü, term, commitIndex, log uzunluğu, canlı), Toxiproxy senaryo script'leri, Grafana dashboard
- **Kabul**: 24 saatlik kaos koşusu; kontrolcü ihlal bulmuyor; panel canlı gösteriyor

### Faz 5 — Benchmark, belge, yayın (Hafta 15–16)
- Benchmark: 8 istemci, 100k op; p50/p99 gecikme ve throughput; değişkenler: fsync her entry vs batch, 3 vs 5 node, 100 B vs 4 KB değer
- README final, tüm ADR'ler, blog yazısı ("Raft'ı sıfırdan yazarken öğrendiğimiz 10 şey"), 2 dakikalık demo videosu/GIF, `v1.0.0` release
- **Kabul**: §0'daki beş madde

---

## 6. Test stratejisi

Katman katman, en ucuzdan en pahalıya:

| Katman | Ne | Nerede çalışır | Süre |
|---|---|---|---|
| Birim | WAL append/kurtarma/truncate/CRC; oy verme kuralları; log eşleme | Her PR | saniyeler |
| Property (jqwik) | Rastgele entry dizileriyle WAL round-trip; rastgele RPC dizileriyle term monotonluğu | Her PR | < 1 dk |
| Deterministik simülasyon | N bellek içi node, sahte ağ + sahte saat, seed başına binlerce olay, 5 invariant | PR: 200 seed · Gece: 10.000 seed | 2 dk / 1 sa |
| Entegrasyon | 3 gerçek süreç (Docker), gerçek gRPC, gerçek disk | Her PR (kısa) | 3 dk |
| Kaos | Toxiproxy + süreç öldürme + linearizability kontrolü | Gece + release öncesi | 1–24 sa |

**Simülasyon neden bu kadar önemli?** Zamanlamaya dayalı testler (Thread.sleep, gerçek timer) hem yavaştır hem de "arada bir patlar". Sahte saat ve sahte ağla aynı seed her seferinde aynı senaryoyu üretir; bir bug bulununca `seed=48213` ile bire bir tekrar edersiniz. Bu yaklaşım FoundationDB ve TigerBeetle'ın kullandığı yöntemdir; mülakatta anlatınca ağırlığı hissedilir.

**Linearizability kontrolü**: istemci her işlem için `(çağrı zamanı, dönüş zamanı, işlem, sonuç)` kaydeder. Kontrolcü, tek bir register modeli üzerinde tüm işlemleri sıraya dizmeyi dener; dizemiyorsa ihlal vardır. Küçük geçmişler için kendi arama tabanlı kontrolcünüzü yazın (birkaç yüz satır); büyük geçmişler için Jepsen'in Knossos/Elle aracını Docker'da çalıştırmak bonus.

---

## 7. GitHub ve çalışma düzeni

### 7.1 Repo yapısı

```
raft-kv/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # PR: build, birim, property, sim 200 seed, entegrasyon
│   │   └── nightly.yml         # gece: sim 10k seed, kaos 1 saat
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── CODEOWNERS
├── docs/
│   ├── adr/
│   │   ├── 0001-tek-raft-thread.md
│   │   ├── 0002-grpc-secimi.md
│   │   ├── 0003-wal-formati.md
│   │   ├── 0004-tek-sunucu-uyelik-degisikligi.md
│   │   ├── 0005-readindex-vs-lease-read.md
│   │   └── template.md
│   ├── architecture.md
│   ├── testing.md
│   └── benchmarks.md
├── raft-core/ storage/ transport-grpc/ server/ client/ sim-test/ chaos/ bench/ dashboard/
├── docker/
│   ├── docker-compose.yml      # 3 node + toxiproxy + prometheus + grafana
│   └── Dockerfile
├── build.gradle.kts  settings.gradle.kts  gradle.properties
├── README.md  CONTRIBUTING.md  CHANGELOG.md  LICENSE
└── .editorconfig  .gitignore
```

### 7.2 Dallanma ve commit
- `main` korumalı: doğrudan push yok, PR + 1 onay + yeşil CI şart
- Kısa ömürlü dallar: `feat/raft-election`, `fix/wal-crc-tail`, `docs/adr-0003`
- Squash merge; commit mesajı Conventional Commits: `feat(raft): implement RequestVote handling`, `fix(storage): truncate corrupt WAL tail`, `test(sim): add asymmetric partition scenario`
- Her PR küçük olsun: 300 satırın üstü ikiye bölünür

### 7.3 PR şablonu

```markdown
## Ne değişti
## Neden
## Nasıl test edildi
- [ ] birim
- [ ] sim (seed sayısı: )
- [ ] entegrasyon
## Arayüz değişikliği var mı? (varsa iki onay gerekir)
## İlgili issue
```

### 7.4 CODEOWNERS

```
/raft-core/       @kisiA
/sim-test/        @kisiA
/storage/         @kisiB
/transport-grpc/  @kisiB
/client/          @kisiB
/server/          @kisiB
/dashboard/       @kisiB
/docs/adr/        @kisiA @kisiB
```

### 7.5 Issue ve pano
- Milestone: `Faz 0` … `Faz 5`
- Etiketler: `area:raft` `area:storage` `area:transport` `area:client` `area:panel` `area:test` `kind:bug` `kind:adr` `good-first-issue`
- GitHub Projects panosu: Backlog → Bu hafta → Yapılıyor → Review'da → Bitti
- Her faz başında birlikte 1 saatlik "issue yazma" oturumu; her issue'da kabul kriteri olsun

### 7.6 CI (`ci.yml` özeti)
1. JDK 21 kur, Gradle cache
2. `./gradlew build` (derleme + birim + property)
3. `./gradlew :sim-test:run --args="--seeds=200"`
4. Docker Compose ile 3 node kaldır, entegrasyon testi, indir
5. `dashboard/` için `npm ci && npm run build && npm test`
6. Rozetler README'ye: build, nightly, coverage

### 7.7 Haftalık ritim
- Pazartesi 30 dk: haftanın issue'larını seç, blokajları konuş
- Her gün: açık PR'ları 24 saat içinde review et
- Cuma 30 dk: "demo dakikası" — bu hafta çalışan yeni bir şeyi birbirinize gösterin (motivasyonun en büyük kaynağı)
- Faz sonu: tag (`v0.1.0`, `v0.2.0` …), CHANGELOG, kısa retrospektif

### 7.8 README iskeleti

```markdown
# raft-kv
Java ile sıfırdan yazılmış Raft tabanlı dağıtık key-value store.
[rozetler]

## 60 saniyede demo
docker compose up -d
./kv put sepet:42 "3 ürün"
docker kill raft-kv-node1        # lider
./kv get sepet:42               # → 3 ürün (yeni liderden)
[GIF]

## Neden var
## Mimari (diyagram + docs/architecture.md linki)
## Garantiler ve sınırlar
## Test yaklaşımı (docs/testing.md)
## Benchmark (docs/benchmarks.md)
## Tasarım kararları (docs/adr/)
## Yol haritası
## Lisans
```

### 7.9 ADR şablonu

```markdown
# ADR-000X: Başlık
Tarih · Durum (öneri / kabul / iptal)
## Bağlam
## Karar
## Alternatifler ve neden seçilmedi
## Sonuçlar (iyi ve kötü)
```

---

## 8. Gözlemlenebilirlik

Micrometer ile Prometheus'a açılacak metrikler:
- `raft_term`, `raft_role` (0/1/2), `raft_commit_index`, `raft_last_applied`, `raft_log_last_index`
- `raft_elections_total`, `raft_leader_changes_total`
- `wal_append_seconds`, `wal_fsync_seconds` (histogram), `wal_segment_count`
- `rpc_append_entries_seconds`, `rpc_request_vote_total`
- `kv_ops_total{op,status}`, `kv_op_latency_seconds{op}`

`/admin/status` (JSON): `nodeId, role, term, leaderId, commitIndex, lastApplied, logLastIndex, peers[]`.

React panel: her node'un `/admin/status`'unu 500 ms'de bir çeker; küme görünümü (kim lider, term, log uzunlukları çubuk olarak), seçim geçmişi, son 60 saniye throughput. Sadece okur; "node öldür" butonu yalnızca `chaos/` harness'ında olur.

---

## 9. Benchmark ve yazı

Ölçülecekler ve beklenen dersler:
- fsync her entry vs 10 ms batch → throughput 10–50× fark; "dayanıklılık vs gecikme" trade-off'u
- 3 node vs 5 node → çoğunluk beklemenin maliyeti
- Linearizable `get` (ReadIndex) vs stale `get` → tutarlılık fiyatı
- Değer boyutu 100 B vs 4 KB → ağ mı disk mi darboğaz

Blog yazısı başlıkları için aday: "Raft'ı sıfırdan yazarken yaptığımız 7 hata", "Sahte saatle 10.000 senaryo: dağıtık sistemi laptop'ta test etmek". Yazıyı ikiniz imzalayın, LinkedIn ve dev.to'ya koyun, CV'ye link verin.

---

## 10. Riskler ve önlemler

| Risk | Önlem |
|---|---|
| Zamanlamaya dayalı testler arada patlıyor | Gerçek timer'la test yazmayın; sahte saat + seed. Gerçek zamanlı test sadece entegrasyonda. |
| Faz 2'de A tıkanıyor, B boşta | Arayüzler 1. haftada donmuş; B Faz 3 depolama işlerine erken başlar. |
| Kapsam kayması ("bir de transaction ekleyelim") | §1'deki "yapılmayacaklar" listesi; yeni fikir → `docs/roadmap.md`, koda değil. |
| fsync laptop'ta çok yavaş, moral bozuyor | Normal; Faz 4'e kadar batch yok, sayılar düşük olacak. Bilinçli tercih olarak ADR'ye yazın. |
| Raft'ta ince bug (Figure 8 senaryosu, term karışıklığı) | "Students' Guide to Raft" yazısındaki 20 tuzağı kontrol listesi yapın; lider sadece kendi term'indeki entry'yi sayarak commit eder. |
| Motivasyon düşüşü (ay 2–3) | Cuma demo ritüeli; her faz sonunda tag + kısa yazı; küçük görünür kazanımlar. |
| Bir kişi ayrılırsa | Her modülün README'si var, arayüzler belgeli, kalan kişi devam edebilir. |

---

## 11. Kaynaklar (okuma sırasıyla)

1. Ongaro & Ousterhout, "In Search of an Understandable Consensus Algorithm (Extended Version)" — makalenin kendisi, Figure 2 kutsal kitap
2. thesecretlivesofdata.com/raft — 10 dakikalık görsel anlatım
3. "Students' Guide to Raft" (MIT 6.824/6.5840 yazısı) — en sık yapılan hataların listesi
4. Diego Ongaro'nun doktora tezi — üyelik değişikliği (bölüm 4) ve ReadIndex (bölüm 6.4) buradan
5. MIT 6.5840 Lab 3 ödev metni — kabul kriterlerini buradan uyarlayabilirsiniz
6. Jepsen blog yazıları (etcd, Consul analizleri) — linearizability ne demek, nasıl bozulur
7. Kleppmann, "Designing Data-Intensive Applications" — bölüm 5, 8, 9
8. etcd'nin `raft` kütüphanesi kaynak kodu (Go) — takıldığınızda referans, kopyalamak için değil
9. TigerBeetle ve FoundationDB'nin deterministik simülasyon konuşmaları (YouTube)

---

## 12. Bu hafta yapılacaklar (Faz 0 kontrol listesi)

- [ ] Repo adı ve lisans seçildi, repo açıldı, ikiniz de admin
- [ ] Raft makalesi ikiniz tarafından okundu; 1 saatlik "birbirimize anlatalım" oturumu yapıldı
- [ ] Kim A, kim B karar verildi; CODEOWNERS yazıldı
- [ ] Gradle çok modüllü iskelet, boş modüller, `./gradlew build` yeşil
- [ ] `raft.proto`, `kv.proto` ve §3.7 arayüzleri PR'da, ikiniz onayladı
- [ ] `ci.yml` çalışıyor, README'de rozet
- [ ] ADR-0001 yazıldı
- [ ] Faz 1 issue'ları açıldı, milestone'a bağlandı, pano kuruldu
- [ ] Cuma demo saati takvime kondu
