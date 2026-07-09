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

export default function App() {
  const chat = useChat()
  const [personas, setPersonas] = useState([])
  const [providers, setProviders] = useState([])
  const [templates, setTemplates] = useState([])
  const [cast, setCast] = useState([]) // [{persona, provider, model}]
  const [scene, setScene] = useState({
    topic: 'A casual chat about AI.', maxTurns: 20,
    turnOrder: 'round-robin', streaming: true,
  })
  const [modal, setModal] = useState(null) // 'library' | 'history' | 'usage' | 'interject' | 'saveTemplate'

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
        // Seed cast with the first two library personas
        setCast(list.slice(0, 2).map((p) => ({ persona: p.name, provider: 'ollama', model: '' })))
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
        cast: cast.map((m) => ({ persona: m.persona, provider: m.provider, model: m.model })),
        topic: scene.topic,
        max_turns: scene.maxTurns,
        turn_order: scene.turnOrder,
        streaming: scene.streaming,
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
      setCast([
        { persona: t.persona1_name, provider: 'ollama', model: '' },
        { persona: t.persona2_name, provider: 'ollama', model: '' },
      ])
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
        <HistoryBrowser onClose={() => setModal(null)} toast={chat.toast} />
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
