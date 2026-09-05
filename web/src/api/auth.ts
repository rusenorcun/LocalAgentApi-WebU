import { api } from './client'

export interface AuthResponse {
  access_token: string
  username: string
  role: string
  theme?: string
  lang?: string
}

export const login = (username: string, password: string) =>
  api.post<AuthResponse>('/api/v2/auth/login', { username, password })

export const register = (username: string, password: string) =>
  api.post<AuthResponse>('/api/v2/auth/register', { username, password })

export const logout = () => api.post('/api/v2/auth/logout')

export const getMe = () => api.get('/api/v2/auth/me')

export const updatePreferences = (prefs: { theme?: string; lang?: string; default_model?: string; persona?: string }) =>
  api.patch('/api/v2/auth/me/preferences', prefs)

export const changePassword = (current_password: string, new_password: string) =>
  api.patch('/api/v2/auth/me/password', { current_password, new_password })
