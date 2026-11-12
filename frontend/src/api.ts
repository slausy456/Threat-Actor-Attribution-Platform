import axios from 'axios'
import type { Candidate, Comparison, Persona } from './types'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api', timeout: 12000 })
export const getPersonas = async () => (await api.get<Persona[]>('/personas')).data
export const comparePersonas = async (a: string, b: string) => (await api.post<Comparison>('/compare', { a, b })).data
export const getCandidates = async (id: string, top = 20, since?: string, until?: string) => (await api.get<Candidate[]>(`/personas/${encodeURIComponent(id)}/candidates`, { params: { top, since, until } })).data
export const exportData = async (format: 'json'|'csv'|'report') => (await api.get('/export', { params: { format }, responseType: format === 'json' ? 'json' : 'text' })).data
export const health = async () => (await api.get('/health')).data
