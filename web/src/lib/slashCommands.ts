// Slash komutları / prompt şablonları. Composer'da "/" ile tetiklenir.
export interface SlashCommand {
  cmd: string
  label: string
  desc: string
  template: string // {input} = komuttan sonraki metin
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: 'özetle', label: '/özetle', desc: 'Metni madde madde özetle',
    template: 'Aşağıdaki metni Türkçe, madde madde ve öz biçimde özetle:\n\n{input}' },
  { cmd: 'çevir', label: '/çevir', desc: 'İngilizceye çevir',
    template: 'Aşağıdaki metni İngilizceye çevir (yalnızca çeviriyi ver):\n\n{input}' },
  { cmd: 'açıkla', label: '/açıkla', desc: 'Basit ve adım adım açıkla',
    template: 'Şunu basit, adım adım ve örneklerle açıkla:\n\n{input}' },
  { cmd: 'refactor', label: '/refactor', desc: 'Kodu iyileştir',
    template: 'Aşağıdaki kodu daha okunabilir ve verimli olacak şekilde refactor et; önemli değişiklikleri kısaca açıkla:\n\n{input}' },
  { cmd: 'düzelt', label: '/düzelt', desc: 'Koddaki hatayı bul ve düzelt',
    template: 'Aşağıdaki koddaki hatayı bul ve düzeltilmiş halini ver; nedenini kısaca açıkla:\n\n{input}' },
  { cmd: 'test', label: '/test', desc: 'Birim testleri yaz',
    template: 'Aşağıdaki kod için kapsamlı birim testleri yaz:\n\n{input}' },
]

// "/cmd kalan metin" → şablon. Bilinmeyen/komut değilse metni aynen döner.
export function expandSlash(text: string): string {
  const m = /^\/([\wçğıöşüÇĞİÖŞÜ]+)\s*([\s\S]*)$/.exec(text.trim())
  if (!m) return text
  const cmd = SLASH_COMMANDS.find((c) => c.cmd.toLowerCase() === m[1].toLowerCase())
  if (!cmd) return text
  return cmd.template.replace('{input}', (m[2] || '').trim())
}

// "/" yazılınca eşleşen komutları döndür (boşluk yoksa).
export function matchSlash(text: string): SlashCommand[] {
  const t = text.trim()
  if (!t.startsWith('/') || /\s/.test(t)) return []
  const prefix = t.slice(1).toLowerCase()
  return SLASH_COMMANDS.filter((c) => c.cmd.toLowerCase().startsWith(prefix))
}
