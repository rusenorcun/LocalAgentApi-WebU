import { api } from './client'

export interface McpStatus {
  running: boolean
  healthy: boolean
  managed: boolean
  external: boolean
  pid: number | null
  started_at: string | null
  host: string
  port: number
  url: string
  token_masked: string
  token_file: string
}

export interface ToolInfo {
  name: string
  description: string
  enabled?: boolean
}

export interface McpTools {
  chat_tools: ToolInfo[]
  relay_tools: ToolInfo[] | null
  relay_healthy: boolean
}

export const getMcpStatus = () =>
  api.get<McpStatus>('/api/v2/mcp/status').then((r) => r.data)

export const startMcp = () =>
  api.post<{ ok: boolean; already?: boolean; pid?: number | null; warning?: string }>(
    '/api/v2/mcp/start').then((r) => r.data)

export const stopMcp = (force = false) =>
  api.post<{ ok: boolean; stopped?: number | null }>(
    `/api/v2/mcp/stop${force ? '?force=true' : ''}`).then((r) => r.data)

export const getMcpToken = () =>
  api.get<{ token: string; masked: string; url: string; public_hint: string }>(
    '/api/v2/mcp/token').then((r) => r.data)

export const getMcpTools = () =>
  api.get<McpTools>('/api/v2/mcp/tools').then((r) => r.data)
