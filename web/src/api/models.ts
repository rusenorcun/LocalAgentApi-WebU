import { api } from './client'

export interface ModelInfo {
  id?: number; display_name: string; description: string
  strengths: string[]; speed: number; is_default: boolean; enabled: boolean
  ollama_name?: string; internal?: boolean; is_vision?: boolean
}
export const getModels = (includeInternal = false) =>
  api.get<{ models: ModelInfo[]; default: string }>(
    `/api/v2/models${includeInternal ? '?include_internal=true' : ''}`)

export const listModels = getModels
