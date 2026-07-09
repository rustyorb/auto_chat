import { useEffect, useState } from 'react'
import { api } from './api.js'

/** Model lists cached per provider for the session. */
const modelCache = {}

export function ModelSelect({ provider, value, onChange, toast }) {
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

  // Searchable combobox: type to filter the (often long) model list, or paste
  // any model id directly.
  const listId = `models-${provider}`
  return (
    <>
      <input
        className="input"
        list={listId}
        value={value}
        placeholder={state === 'loading' ? 'loading…' : `model… (${models.length})`}
        disabled={state === 'loading'}
        onChange={(e) => onChange(e.target.value)}
        onFocus={(e) => e.target.select()}
      />
      <datalist id={listId}>
        {models.map((m) => <option key={m} value={m} />)}
      </datalist>
    </>
  )
}

export default function Sidebar({
  personas, providers, templates, cast, setCast, scene, setScene,
  running, onStart, onSurprise, onApplyTemplate, onOpenLibrary, onOpenHistory,
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
            <details className="cast-advanced">
              <summary>tuning</summary>
              <div className="row">
                <label className="grow">temp
                  <input
                    className="input" type="number" min={0} max={2} step={0.1}
                    placeholder="default"
                    value={m.temperature ?? ''}
                    disabled={running}
                    onChange={(e) => updateMember(i, {
                      temperature: e.target.value === '' ? null : +e.target.value,
                    })}
                  />
                </label>
                <label className="grow">max tok
                  <input
                    className="input" type="number" min={16} step={64}
                    placeholder="default"
                    value={m.max_tokens ?? ''}
                    disabled={running}
                    onChange={(e) => updateMember(i, {
                      max_tokens: e.target.value === '' ? null : +e.target.value,
                    })}
                  />
                </label>
              </div>
            </details>
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
            // New members inherit the previous member's provider/model — the
            // common case is "same model, different persona".
            setCast((c) => {
              const prev = c[c.length - 1]
              return [...c, {
                persona: e.target.value,
                provider: prev?.provider || 'lmstudio',
                model: prev?.model || '',
              }]
            })
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
              value={scene.endless ? '' : scene.maxTurns}
              placeholder={scene.endless ? '∞' : ''}
              disabled={running || scene.endless}
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

        <label className="check" title="Run until you press Stop">
          <input
            type="checkbox"
            checked={!!scene.endless}
            disabled={running}
            onChange={(e) => setScene((s) => ({ ...s, endless: e.target.checked }))}
          />
          ∞ Endless — run until stopped
        </label>

        <label className="check" title="Every few turns, an unseen Director injects a twist to keep the scene moving">
          <input
            type="checkbox"
            checked={!!scene.director}
            disabled={running}
            onChange={(e) => setScene((s) => ({ ...s, director: e.target.checked }))}
          />
          🎬 Auto-Director
          {scene.director && (
            <span className="director-every">
              twist every
              <input
                className="input turns-input" type="number" min={2} max={50}
                value={scene.directorEvery ?? 4}
                disabled={running}
                onChange={(e) => setScene((s) => ({ ...s, directorEvery: +e.target.value || 4 }))}
              />
              turns
            </span>
          )}
        </label>

        <div className="row">
          <label className="grow">Turn delay (s)
            <input
              className="input" type="number" min={0} max={30} step={0.5}
              value={scene.turnDelay}
              disabled={running}
              onChange={(e) => setScene((s) => ({ ...s, turnDelay: +e.target.value || 0 }))}
            />
          </label>
          <label className="check grow">
            <input
              type="checkbox"
              checked={scene.streaming}
              disabled={running}
              onChange={(e) => setScene((s) => ({ ...s, streaming: e.target.checked }))}
            />
            Stream responses
          </label>
        </div>
      </div>

      <button className="btn btn-start" onClick={onStart} disabled={running}>
        {running ? '●  Conversation live…' : '▶  Start Conversation'}
      </button>
      <button
        className="btn btn-ghost"
        onClick={onSurprise}
        disabled={running}
        title="Invent a wild topic and a fresh cast using the first cast member's model"
      >
        🎲 Surprise me
      </button>

      <div className="sidebar-footer">
        <button className="btn btn-ghost btn-xs" onClick={onOpenHistory}>History</button>
        <button className="btn btn-ghost btn-xs" onClick={onOpenUsage}>Usage</button>
      </div>
    </aside>
  )
}
