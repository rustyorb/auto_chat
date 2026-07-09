async function req(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  personas: () => req('/api/personas'),
  createPersona: (p) => req('/api/personas', { method: 'POST', body: JSON.stringify(p) }),
  updatePersona: (name, p) => req(`/api/personas/${encodeURIComponent(name)}`, { method: 'PUT', body: JSON.stringify(p) }),
  deletePersona: (name) => req(`/api/personas/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  providers: () => req('/api/providers'),
  models: (provider) => req(`/api/models/${encodeURIComponent(provider)}`),
  setKey: (provider, key) => req('/api/keys', { method: 'POST', body: JSON.stringify({ provider, key }) }),
  setProviderUrl: (provider, url) => req('/api/providers/url', { method: 'POST', body: JSON.stringify({ provider, url }) }),

  start: (body) => req('/api/conversation/start', { method: 'POST', body: JSON.stringify(body) }),
  pause: () => req('/api/conversation/pause', { method: 'POST' }),
  resume: () => req('/api/conversation/resume', { method: 'POST' }),
  stop: () => req('/api/conversation/stop', { method: 'POST' }),
  interject: (kind, content) => req('/api/conversation/interject', { method: 'POST', body: JSON.stringify({ kind, content }) }),
  continueRun: (turns) => req('/api/conversation/continue', { method: 'POST', body: JSON.stringify({ turns }) }),
  regenerate: () => req('/api/conversation/regenerate', { method: 'POST' }),
  loadConversation: (historyId, cast) => req('/api/conversation/load', { method: 'POST', body: JSON.stringify({ history_id: historyId, cast }) }),
  summarize: (provider, model) => req('/api/conversation/summarize', { method: 'POST', body: JSON.stringify({ provider, model }) }),
  generatePersona: (description, provider, model) => req('/api/personas/generate', { method: 'POST', body: JSON.stringify({ description, provider, model }) }),

  templates: () => req('/api/templates'),
  saveTemplate: (t) => req('/api/templates', { method: 'POST', body: JSON.stringify(t) }),
  deleteTemplate: (name) => req(`/api/templates/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  history: (search, favorites) => req(`/api/history?${new URLSearchParams({ ...(search ? { search } : {}), favorites })}`),
  historyItem: (id) => req(`/api/history/${id}`),
  toggleFavorite: (id) => req(`/api/history/${id}/favorite`, { method: 'POST' }),
  deleteHistory: (id) => req(`/api/history/${id}`, { method: 'DELETE' }),

  usage: () => req('/api/usage'),
}
