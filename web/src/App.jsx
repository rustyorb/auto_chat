import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { useChat } from './useChat.js'
import Sidebar from './Sidebar.jsx'
import Stage from './Stage.jsx'
import { PersonaLibrary, HistoryBrowser, UsagePanel, InterjectDialog, SaveTemplateDialog } from './Modals.jsx'

export const PERSONA_COLORS = [
  '#4cc9f0', '#f72585', '#ffd166', '#06d6a0', '#c77dff',
  '#ff8fab', '#80ffdb', '#fca311', '#90e0ef', '#e5989b',
]

function loadSaved(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback
  } catch { return fallback }
}

export default function App() {
  const chat = useChat()
  const [personas, setPersonas] = useState([])
  const [providers, setProviders] = useState([])
  const [templates, setTemplates] = useState([])
  // [{persona, provider, model, temperature?, max_tokens?}]
  const [cast, setCast] = useState(() => loadSaved('autochat.cast', { list: [] }).list)
  const [scene, setScene] = useState(() => loadSaved('autochat.scene', {
    topic: 'A casual chat about AI.', maxTurns: 20,
    turnOrder: 'round-robin', streaming: true, turnDelay: 1,
  }))
  const [modal, setModal] = useState(null) // 'library' | 'history' | 'usage' | 'interject' | 'saveTemplate'

  // Remember setup across refreshes
  useEffect(() => { localStorage.setItem('autochat.scene', JSON.stringify(scene)) }, [scene])
  useEffect(() => { localStorage.setItem('autochat.cast', JSON.stringify({ list: cast })) }, [cast])

  const loadPersonas = useCallback(async () => {
    const list = await api.personas()
    setPersonas(list)
    return list
  }, [])

  const loadTemplates = useCallback(async () => {
    setTemplates(await api.templates())
  }, [])

  useEffect(() => {
    (async () => {
      try {
        const [list] = await Promise.all([loadPersonas(), loadTemplates()])
        setProviders(await api.providers())
        // Seed cast with the first two library personas (unless restored)
        setCast((c) => c.length ? c
          : list.slice(0, 2).map((p) => ({ persona: p.name, provider: 'lmstudio', model: '' })))
      } catch (e) {
        chat.toast(`Failed to load setup: ${e.message}`, 'danger')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const start = async () => {
    if (cast.length < 2) return chat.toast('Add at least 2 personas to the cast', 'danger')
    for (const m of cast) {
      if (!m.model) return chat.toast(`Pick a model for ${m.persona}`, 'danger')
    }
    try {
      chat.resetLocal(scene.topic, scene.maxTurns)
      await api.start({
        cast: cast.map((m) => ({
          persona: m.persona, provider: m.provider, model: m.model,
          temperature: m.temperature ?? null, max_tokens: m.max_tokens ?? null,
        })),
        topic: scene.topic,
        max_turns: scene.maxTurns,
        turn_order: scene.turnOrder,
        streaming: scene.streaming,
        turn_delay: scene.turnDelay ?? 1,
      })
      chat.setRunning(true)
    } catch (e) {
      chat.toast(e.message, 'danger')
    }
  }

  const applyTemplate = (t) => {
    setScene((s) => ({ ...s, topic: t.initial_topic, maxTurns: t.max_turns }))
    const names = new Set(personas.map((p) => p.name))
    if (names.has(t.persona1_name) && names.has(t.persona2_name)) {
      setCast((c) => {
        const provider = c[0]?.provider || 'lmstudio'
        const model = c[0]?.model || ''
        return [
          { persona: t.persona1_name, provider, model },
          { persona: t.persona2_name, provider, model },
        ]
      })
    }
    chat.toast(`Template applied: ${t.name}`)
  }

  return (
    <div className="app">
      <Sidebar
        personas={personas}
        providers={providers}
        templates={templates}
        cast={cast}
        setCast={setCast}
        scene={scene}
        setScene={setScene}
        running={chat.running}
        onStart={start}
        onApplyTemplate={applyTemplate}
        onOpenLibrary={() => setModal('library')}
        onOpenHistory={() => setModal('history')}
        onOpenUsage={() => setModal('usage')}
        onSaveTemplate={() => setModal('saveTemplate')}
        toast={chat.toast}
        colors={PERSONA_COLORS}
      />
      <Stage
        chat={chat}
        colors={PERSONA_COLORS}
        onInterject={() => setModal('interject')}
        summarizer={cast[0]}
      />

      {modal === 'library' && (
        <PersonaLibrary
          personas={personas}
          providers={providers}
          onChanged={loadPersonas}
          onClose={() => setModal(null)}
          toast={chat.toast}
        />
      )}
      {modal === 'history' && (
        <HistoryBrowser providers={providers} onClose={() => setModal(null)} toast={chat.toast} />
      )}
      {modal === 'usage' && <UsagePanel onClose={() => setModal(null)} />}
      {modal === 'interject' && (
        <InterjectDialog
          onClose={() => setModal(null)}
          onSubmit={async (kind, content) => {
            try {
              await api.interject(kind, content)
              chat.toast('Interjection queued — resume to see the reaction')
            } catch (e) { chat.toast(e.message, 'danger') }
            setModal(null)
          }}
        />
      )}
      {modal === 'saveTemplate' && (
        <SaveTemplateDialog
          cast={cast}
          scene={scene}
          onClose={() => setModal(null)}
          onSaved={() => { loadTemplates(); setModal(null); chat.toast('Template saved') }}
          toast={chat.toast}
        />
      )}

      <div className="toasts">
        {chat.toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>{t.text}</div>
        ))}
      </div>
    </div>
  )
}
