import { useEffect, useState } from 'react'
import { api } from './api.js'

/** Model lists cached per provider for the session. */
const modelCache = {}

function ModelSelect({ provider, value, onChange, toast }) {
  const [models, setModels] = useState(modelCache[provider] || [])
  const [state, setState] = useState(modelCache[provider] ? 'ready' : 'loading')

  useEffect(() => {
    let cancelled = false
    if (modelCache[provider]) {
      setModels(modelCache[provider])
      setState('ready')
      return
    }
    setState('loading')
    api.models(provider)
      .then((r) => {
        if (cancelled) return
        modelCache[provider] = r.models
        setModels(r.models)
        setState('ready')
      })
      .catch((e) => {
        if (cancelled) return
        setState(e.message.includes('API key') ? 'needs-key' : 'error')
        setModels([])
      })
    return () => { cancelled = true }
  }, [provider])

  if (state === 'needs-key') {
    return (
      <button
        className="btn btn-warn btn-xs"
        onClick={async () => {
          const key = window.prompt(`API key for ${provider}:`)
          if (!key) return
          try {
            await api.setKey(provider, key)
            delete modelCache[provider]
            const r = await api.models(provider)
            modelCache[provider] = r.models
            setModels(r.models)
            setState('ready')
            toast(`API key saved for ${provider}`)
          } catch (e) { toast(e.message, 'danger') }
        }}
      >
        set API key…
      </button>
    )
  }

  if (state === 'error' && (provider === 'ollama' || provider === 'lmstudio')) {
    return (
      <button
        className="btn btn-warn btn-xs"
        title="Provider unreachable — set its address (e.g. 192.168.0.177:1235)"
        onClick={async () => {
          const url = window.prompt(
            `${provider} is unreachable. Enter its address\n(e.g. 192.168.0.177:1235 — /v1 is added automatically for LM Studio):`)
          if (url === null) return
          try {
            await api.setProviderUrl(provider, url)
            delete modelCache[provider]
            setState('loading')
            const r = await api.models(provider)
            modelCache[provider] = r.models
            setModels(r.models)
            setState('ready')
            toast(`${provider} connected — ${r.models.length} models found`, 'success')
          } catch (e) {
            setState('error')
            toast(`Still unreachable: ${e.message}`, 'danger')
          }
        }}
      >
        unreachable — set URL…
      </button>
    )
  }

  return (
    <select
      className="select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={state !== 'ready'}
    >
      <option value="">
        {state === 'loading' ? 'loading…' : state === 'error' ? 'unreachable' : 'model…'}
      </option>
      {models.map((m) => <option key={m} value={m}>{m}</option>)}
    </select>
  )
}

export default function Sidebar({
  personas, providers, templates, cast, setCast, scene, setScene,
  running, onStart, onApplyTemplate, onOpenLibrary, onOpenHistory,
  onOpenUsage, onSaveTemplate, toast, colors,
}) {
  const availablePersonas = personas.filter((p) => !cast.some((m) => m.persona === p.name))

  const updateMember = (i, patch) => {
    setCast((c) => c.map((m, j) => (j === i ? { ...m, ...patch } : m)))
  }

  return (
    <aside className="sidebar">
      <div className="brand">⬢ AUTO CHAT <span>STUDIO</span></div>

      <div className="section-title">CAST <em>({cast.length})</em></div>
      <div className="cast-list">
        {cast.map((m, i) => (
          <div className="cast-card" key={m.persona} style={{ borderLeftColor: colors[i % colors.length] }}>
            <div className="cast-head">
              <span className="dot" style={{ background: colors[i % colors.length] }} />
              <strong>{m.persona}</strong>
              <button
                className="icon-btn"
                title="Remove from cast"
                disabled={running}
                onClick={() => setCast((c) => c.filter((_, j) => j !== i))}
              >✕</button>
            </div>
            <div className="cast-controls">
              <select
                className="select"
                value={m.provider}
                disabled={running}
                onChange={(e) => updateMember(i, { provider: e.target.value, model: '' })}
              >
                {providers.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
              </select>
              <ModelSelect
                provider={m.provider}
                value={m.model}
                onChange={(model) => updateMember(i, { model })}
                toast={toast}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="cast-actions">
        <select
          className="select"
          value=""
          disabled={running || cast.length >= 10 || availablePersonas.length === 0}
          onChange={(e) => {
            if (!e.target.value) return
            setCast((c) => [...c, { persona: e.target.value, provider: 'ollama', model: '' }])
          }}
        >
          <option value="">＋ add persona…</option>
          {availablePersonas.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
        <button className="btn btn-ghost btn-xs" onClick={onOpenLibrary}>Library…</button>
      </div>

      <div className="section-title">SCENE</div>
      <div className="scene">
        <label>Topic
          <textarea
            className="input"
            rows={2}
            value={scene.topic}
            disabled={running}
            onChange={(e) => setScene((s) => ({ ...s, topic: e.target.value }))}
          />
        </label>

        <label>Template
          <div className="row">
            <select
              className="select"
              value=""
              disabled={running}
              onChange={(e) => {
                const t = templates.find((x) => x.name === e.target.value)
                if (t) onApplyTemplate(t)
              }}
            >
              <option value="">apply…</option>
              {templates.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
            <button className="btn btn-ghost btn-xs" onClick={onSaveTemplate} disabled={running}>save</button>
          </div>
        </label>

        <div className="row">
          <label className="grow">Turns
            <input
              className="input" type="number" min={2} max={200}
              value={scene.maxTurns}
              disabled={running}
              onChange={(e) => setScene((s) => ({ ...s, maxTurns: +e.target.value || 20 }))}
            />
          </label>
          <label className="grow">Order
            <select
              className="select"
              value={scene.turnOrder}
              disabled={running}
              onChange={(e) => setScene((s) => ({ ...s, turnOrder: e.target.value }))}
            >
              <option value="round-robin">round-robin</option>
              <option value="random">random</option>
            </select>
          </label>
        </div>

        <label className="check">
          <input
            type="checkbox"
            checked={scene.streaming}
            disabled={running}
            onChange={(e) => setScene((s) => ({ ...s, streaming: e.target.checked }))}
          />
          Stream responses
        </label>
      </div>

      <button className="btn btn-start" onClick={onStart} disabled={running}>
        {running ? '●  Conversation live…' : '▶  Start Conversation'}
      </button>

      <div className="sidebar-footer">
        <button className="btn btn-ghost btn-xs" onClick={onOpenHistory}>History</button>
        <button className="btn btn-ghost btn-xs" onClick={onOpenUsage}>Usage</button>
      </div>
    </aside>
  )
}
