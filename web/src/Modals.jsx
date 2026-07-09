import { useEffect, useState } from 'react'
import { api } from './api.js'
import { ModelSelect } from './Sidebar.jsx'

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'modal-wide' : ''}`}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

// --- Persona library --------------------------------------------------------

const EMPTY_FORM = { name: '', age: 25, gender: '', personality: '', avatar: '', fallback_provider: '', fallback_model: '' }

function PersonaGenerator({ providers, onDraft, toast }) {
  const [description, setDescription] = useState('')
  const [provider, setProvider] = useState('lmstudio')
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)

  return (
    <div className="generator">
      <div className="section-title">✨ GENERATE WITH AI</div>
      <label>Describe the persona
        <input
          className="input"
          placeholder="e.g. a paranoid weather forecaster who trusts pigeons"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <div className="row">
        <select className="select" value={provider}
          onChange={(e) => { setProvider(e.target.value); setModel('') }}>
          {providers.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
        </select>
        <ModelSelect provider={provider} value={model} onChange={setModel} toast={toast} />
        <button
          className="btn btn-start btn-xs"
          disabled={busy || !description.trim() || !model}
          onClick={async () => {
            setBusy(true)
            try {
              const draft = await api.generatePersona(description.trim(), provider, model)
              onDraft(draft)
              toast(`Drafted ${draft.name} — review and save`)
            } catch (e) { toast(e.message, 'danger') }
            setBusy(false)
          }}
        >
          {busy ? 'dreaming…' : 'generate'}
        </button>
      </div>
    </div>
  )
}

export function PersonaLibrary({ personas, providers, onChanged, onClose, toast }) {
  const [editing, setEditing] = useState(null)   // original name being edited, or '' for new
  const [form, setForm] = useState(EMPTY_FORM)

  const openEdit = (p) => {
    setEditing(p.name)
    setForm({
      name: p.name, age: p.age, gender: p.gender, personality: p.personality,
      avatar: p.avatar || '',
      fallback_provider: p.fallback_provider || '', fallback_model: p.fallback_model || '',
    })
  }

  const submit = async () => {
    if (!form.name || !form.gender || !form.personality) {
      return toast('Name, gender and personality are required', 'danger')
    }
    try {
      const body = { ...form, age: +form.age || 1 }
      if (editing) await api.updatePersona(editing, body)
      else await api.createPersona(body)
      toast(editing ? `Updated ${form.name}` : `Added ${form.name}`)
      setEditing(null)
      setForm(EMPTY_FORM)
      onChanged()
    } catch (e) { toast(e.message, 'danger') }
  }

  return (
    <Modal title="Persona Library" onClose={onClose} wide>
      <div className="library">
        <div className="library-list">
          {personas.map((p) => (
            <div key={p.name} className="library-item">
              <div>
                <strong>{p.avatar ? `${p.avatar} ` : ''}{p.name}</strong>
                <div className="muted">{p.gender}, {p.age}</div>
              </div>
              <div className="row">
                <button className="btn btn-ghost btn-xs" onClick={() => openEdit(p)}>edit</button>
                <button
                  className="btn btn-danger btn-xs"
                  onClick={async () => {
                    if (!window.confirm(`Delete ${p.name}?`)) return
                    try { await api.deletePersona(p.name); toast(`Deleted ${p.name}`, 'warning'); onChanged() }
                    catch (e) { toast(e.message, 'danger') }
                  }}
                >del</button>
              </div>
            </div>
          ))}
          <button className="btn btn-ghost btn-xs" onClick={() => { setEditing(''); setForm(EMPTY_FORM) }}>
            ＋ New persona
          </button>
          <PersonaGenerator
            providers={providers}
            toast={toast}
            onDraft={(draft) => {
              setEditing('')
              setForm({ ...EMPTY_FORM, ...draft })
            }}
          />
        </div>

        {editing !== null && (
          <div className="library-form">
            <div className="row">
              <label className="grow">Name<input className="input" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
              <label>Avatar<input className="input avatar-input" value={form.avatar}
                placeholder="🙂" maxLength={4}
                onChange={(e) => setForm({ ...form, avatar: e.target.value })} /></label>
            </div>
            <div className="row">
              <label className="grow">Age<input className="input" type="number" value={form.age}
                onChange={(e) => setForm({ ...form, age: e.target.value })} /></label>
              <label className="grow">Gender<input className="input" value={form.gender}
                onChange={(e) => setForm({ ...form, gender: e.target.value })} /></label>
            </div>
            <label>Personality<textarea className="input" rows={5} value={form.personality}
              onChange={(e) => setForm({ ...form, personality: e.target.value })} /></label>
            <div className="row">
              <label className="grow">Fallback provider
                <select className="select" value={form.fallback_provider}
                  onChange={(e) => setForm({ ...form, fallback_provider: e.target.value })}>
                  <option value="">none</option>
                  {providers.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
                </select>
              </label>
              <label className="grow">Fallback model<input className="input" value={form.fallback_model}
                onChange={(e) => setForm({ ...form, fallback_model: e.target.value })} /></label>
            </div>
            <div className="row">
              <button className="btn btn-start" onClick={submit}>{editing ? 'Save' : 'Add'}</button>
              <button className="btn btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

// --- History ------------------------------------------------------------------

const PAGE = 50

export function HistoryBrowser({ providers, onClose, toast }) {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  const [favorites, setFavorites] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [viewing, setViewing] = useState(null)
  const [resuming, setResuming] = useState(null) // {id, names}
  const [provider, setProvider] = useState('lmstudio')
  const [model, setModel] = useState('')

  const refresh = async () => {
    try {
      const page = await api.history(search, favorites, 0, PAGE)
      setItems(page)
      setHasMore(page.length === PAGE)
    } catch (e) { toast(e.message, 'danger') }
  }

  const loadMore = async () => {
    try {
      const page = await api.history(search, favorites, items.length, PAGE)
      setItems((cur) => [...cur, ...page])
      setHasMore(page.length === PAGE)
    } catch (e) { toast(e.message, 'danger') }
  }

  useEffect(() => { refresh() }, [favorites]) // eslint-disable-line react-hooks/exhaustive-deps

  if (resuming) {
    const isBranch = resuming.upTo != null
    return (
      <Modal title={`${isBranch ? '⑂ Branch' : 'Resume'}: ${resuming.theme}`}
             onClose={() => setResuming(null)}>
        <p className="muted">
          {isBranch
            ? `Loads the first ${resuming.upTo} messages on stage — press “Continue” to explore a different path from that point. The original stays in History.`
            : 'Loads this conversation back on stage so you can keep it going with “Continue”. Everyone speaks through the model you pick here.'}
        </p>
        <p><strong>Cast:</strong> {resuming.names.join(', ')}</p>
        <div className="row">
          <select className="select" value={provider}
            onChange={(e) => { setProvider(e.target.value); setModel('') }}>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
          </select>
          <ModelSelect provider={provider} value={model} onChange={setModel} toast={toast} />
        </div>
        <div className="row">
          <button className="btn btn-start" disabled={!model}
            onClick={async () => {
              try {
                await api.loadConversation(resuming.id,
                  resuming.names.map((n) => ({ persona: n, provider, model })),
                  resuming.upTo ?? null)
                toast(isBranch
                  ? 'Branched — press Continue to explore the new path'
                  : 'Conversation loaded — press Continue to extend it')
                onClose()
              } catch (e) { toast(e.message, 'danger') }
            }}>Load on stage</button>
          <button className="btn btn-ghost" onClick={() => setResuming(null)}>Back</button>
        </div>
      </Modal>
    )
  }

  if (viewing) {
    const msgs = viewing.conversation || []
    const branchAt = (i) => {
      const slice = msgs.slice(0, i + 1)
      const names = [...new Set(slice
        .filter((m) => m.role === 'assistant' || m.role === 'user')
        .map((m) => m.persona))]
      if (names.length < 2) return toast('Branch a little later — need at least 2 speakers so far', 'danger')
      setResuming({
        id: viewing.id, names, upTo: i + 1,
        theme: viewing.metadata?.theme || '',
      })
      setViewing(null)
    }
    return (
      <Modal title={`#${viewing.id ?? ''} — ${viewing.metadata?.theme || ''}`} onClose={() => setViewing(null)} wide>
        <p className="muted">⑂ branches the story at that message — everything after it is replaced by a new path.</p>
        <div className="history-view">
          {msgs.map((m, i) => (
            <div key={i} className="history-msg">
              <strong>{m.persona}</strong>
              <button
                className="btn btn-ghost btn-xs branch-btn"
                title="Branch from here — continue a different way after this message"
                onClick={() => branchAt(i)}
              >⑂</button>
              <p>{m.content}</p>
            </div>
          ))}
        </div>
      </Modal>
    )
  }

  return (
    <Modal title="Conversation History" onClose={onClose} wide>
      <div className="row history-toolbar">
        <input className="input grow" placeholder="search…" value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && refresh()} />
        <label className="check"><input type="checkbox" checked={favorites}
          onChange={(e) => setFavorites(e.target.checked)} /> ★ only</label>
        <button className="btn btn-ghost btn-xs" onClick={refresh}>search</button>
        <button
          className="btn btn-danger btn-xs"
          title="Delete all conversations except starred ones"
          onClick={async () => {
            if (!window.confirm('Delete ALL non-starred conversations? Starred (★) ones are kept.')) return
            try {
              const r = await api.clearHistory()
              toast(`Deleted ${r.deleted} conversations (favorites kept)`, 'warning')
              refresh()
            } catch (e) { toast(e.message, 'danger') }
          }}
        >clear all</button>
      </div>
      <div className="history-list">
        {items.map((c) => (
          <div key={c.id} className="library-item">
            <div>
              <strong title={c.theme}>{c.title || c.theme}</strong> {c.is_favorite ? '★' : ''}
              <div className="muted">
                {new Date(c.timestamp).toLocaleString()} · {c.persona1} vs {c.persona2} · {c.turn_count} turns
              </div>
            </div>
            <div className="row">
              <button className="btn btn-ghost btn-xs"
                onClick={async () => setViewing({ ...(await api.historyItem(c.id)), id: c.id })}>view</button>
              <button className="btn btn-ghost btn-xs" title="Load on stage and keep it going"
                onClick={async () => {
                  try {
                    const item = await api.historyItem(c.id)
                    const names = [...new Set((item.conversation || [])
                      .filter((m) => m.role === 'assistant' || m.role === 'user')
                      .map((m) => m.persona))]
                    if (names.length < 2) return toast('Not enough speakers to resume', 'danger')
                    setResuming({ id: c.id, names, theme: c.theme })
                  } catch (e) { toast(e.message, 'danger') }
                }}>resume</button>
              <button className="btn btn-ghost btn-xs"
                onClick={async () => { await api.toggleFavorite(c.id); refresh() }}>★</button>
              <button className="btn btn-danger btn-xs"
                onClick={async () => {
                  if (!window.confirm(`Delete conversation #${c.id}?`)) return
                  await api.deleteHistory(c.id); refresh()
                }}>del</button>
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="muted">No conversations found.</p>}
        {hasMore && (
          <button className="btn btn-ghost btn-xs" onClick={loadMore}>
            ↓ load more
          </button>
        )}
      </div>
    </Modal>
  )
}

// --- Usage ----------------------------------------------------------------------

export function UsagePanel({ onClose }) {
  const [data, setData] = useState(null)
  useEffect(() => { api.usage().then(setData).catch(() => {}) }, [])

  return (
    <Modal title="Usage & Costs" onClose={onClose} wide>
      {!data ? <p className="muted">Loading…</p> : (
        <>
          <p>
            <strong>This session:</strong> {(data.session?.total_tokens || 0).toLocaleString()} tokens ·{' '}
            ${(data.session?.estimated_cost || 0).toFixed(4)}
            <span className="muted"> — since the current conversation started</span>
          </p>
          <p>
            <strong>All time:</strong> {data.total.call_count} calls ·{' '}
            {data.total.total_tokens.toLocaleString()} tokens · ${data.total.estimated_cost.toFixed(4)}
          </p>
          {(data.by_provider?.length > 0) && (
            <table className="table">
              <thead><tr><th>Provider</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead>
              <tbody>
                {data.by_provider.map((r, i) => (
                  <tr key={i}>
                    <td>{r.provider}</td><td>{r.call_count}</td>
                    <td>{r.total_tokens?.toLocaleString()}</td>
                    <td>${(r.estimated_cost || 0).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <table className="table">
            <thead><tr><th>Provider</th><th>Model</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead>
            <tbody>
              {data.by_model.map((r, i) => (
                <tr key={i}>
                  <td>{r.provider}</td><td>{r.model}</td><td>{r.call_count}</td>
                  <td>{r.total_tokens?.toLocaleString()}</td>
                  <td>${(r.estimated_cost || 0).toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Modal>
  )
}

// --- Interject --------------------------------------------------------------------

export function InterjectDialog({ onClose, onSubmit }) {
  const [kind, setKind] = useState('topic')
  const [content, setContent] = useState('')
  return (
    <Modal title="Interject" onClose={onClose}>
      <label>Type
        <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="topic">Steer to a new topic</option>
          <option value="system">System event</option>
          <option value="narrator">Narrator scene note</option>
        </select>
      </label>
      <label>Content
        <textarea className="input" rows={4} value={content} autoFocus
          onChange={(e) => setContent(e.target.value)} />
      </label>
      <div className="row">
        <button className="btn btn-start" disabled={!content.trim()}
          onClick={() => onSubmit(kind, content.trim())}>Send</button>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  )
}

// --- Save template -------------------------------------------------------------------

export function SaveTemplateDialog({ cast, scene, onClose, onSaved, toast }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('custom')
  return (
    <Modal title="Save Template" onClose={onClose}>
      <label>Name<input className="input" value={name} autoFocus
        onChange={(e) => setName(e.target.value)} /></label>
      <label>Description<textarea className="input" rows={3} value={description}
        onChange={(e) => setDescription(e.target.value)} /></label>
      <label>Category
        <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
          {['custom', 'debate', 'interview', 'brainstorming', 'tutoring', 'storytelling']
            .map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <div className="row">
        <button className="btn btn-start" disabled={!name.trim() || !description.trim()}
          onClick={async () => {
            try {
              await api.saveTemplate({
                name: name.trim(), description: description.trim(),
                persona1_name: cast[0]?.persona || '', persona2_name: cast[1]?.persona || '',
                initial_topic: scene.topic, max_turns: scene.maxTurns, category,
              })
              onSaved()
            } catch (e) { toast(e.message, 'danger') }
          }}>Save</button>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  )
}
