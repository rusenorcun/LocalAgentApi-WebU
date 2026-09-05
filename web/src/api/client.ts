import axios from 'axios'
import { useAuthStore } from '../store/authStore'

// NOT: Tüm çağrılar tam yol ('/api/v2/...') kullanır; baseURL boş.
// (baseURL '/api/v2' iken tam yollar '/api/v2/api/v2/...' olarak ikileniyordu.)
export const api = axios.create({ baseURL: '', withCredentials: true })

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<string> | null = null

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    // Giriş/register/refresh uçları 401 döndürdüğünde bu "oturum süresi doldu"
    // değil, gerçek bir kimlik doğrulama hatasıdır (örn. yanlış şifre). Burada
    // refresh denemek + /login'e atmak yerine hata doğrudan çağırana iletilir
    // ki LoginPage başarısız girişi uyarı olarak gösterebilsin.
    const url = original?.url || ''
    const isPreAuth = ['/api/v2/auth/login', '/api/v2/auth/register', '/api/v2/auth/refresh']
      .some((p) => url.startsWith(p))
    if (
      err.response?.status === 401 &&
      !original._retry &&
      !isPreAuth &&
      original.headers?.Authorization
    ) {
      original._retry = true
      if (!refreshing) {
        refreshing = axios
          .post('/api/v2/auth/refresh', {}, { withCredentials: true })
          .then((r) => {
            const token = r.data.access_token
            useAuthStore.getState().setTokens(token, r.data.username, r.data.role)
            return token
          })
          .finally(() => { refreshing = null })
      }
      try {
        const token = await refreshing
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      } catch {
        useAuthStore.getState().logout()
        window.location.href = '/login'
        // ÖNEMLİ: reject dönmezse çağıran taraf undefined alır ve
        // res.data erişimi TypeError fırlatır (beyaz ekran sebebi olabilir)
        return Promise.reject(err)
      }
    }
    return Promise.reject(err)
  }
)
