/**
 * Çekmece/sayfa açıkken arka planın kaymasını engeller.
 *
 * Sayaçlı: aynı anda birden fazla katman (sol gezinme çekmecesi + sağ araç
 * paneli) açık olabilir; biri kapanınca diğeri hâlâ açıkken kilidin düşmemesi
 * için kilit yalnızca son katman kapandığında kaldırılır.
 */
let locks = 0

export function lockBodyScroll(): () => void {
  locks += 1
  document.body.classList.add('drawer-open')
  let released = false
  return () => {
    if (released) return
    released = true
    locks = Math.max(0, locks - 1)
    if (locks === 0) document.body.classList.remove('drawer-open')
  }
}
