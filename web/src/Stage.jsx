import { useEffect, useMemo, useRef, useState } from 'react'
import { marked } from 'marked'
import { api } from './api.js'

marked.setOptions({ breaks: true })

function Message({ msg, colors }) {
  const html = useMemo(() => marked.parse(msg.content || ''), [msg.content])

  if (msg.role === 'system' || msg.role === 'narrator') {
    return <div className="msg-system">— {msg.persona}: {msg.content} —</div>
  }
  const color = msg.color_index >= 0 ? colors[msg.color_index % colors.length] : '#8a919c'
  const thinkingLive = msg.streaming && !msg.content && msg.thinking
  return (
    <div className="msg">
      <div className="msg-head">
        <span className="dot" style={{ background: color }} />
        <span className="msg-name" style={{ color }}>{msg.persona}</span>
      </div>
      {msg.thinking && (
        <details className="thinking" open={!!thinkingLive}>
          <summary>💭 {thinkingLive ? 'thinking…' : 'thoughts'}</summary>
          <div className="thinking-body">{msg.thinking}</div>
        </details>
      )}
      <div className={`msg-body ${msg.streaming ? 'streaming' : ''}`}
           dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  )
}

export default function Stage({ chat, colors, onInterject, summarizer }) {
  const listRef = useRef(null)
  const stickToBottom = useRef(true)
  const [search, setSearch] = useState('')
  const [moreTurns, setMoreTurns] = useState(4)
  // Shared modal for model-written reports: null | {title, body: 'loading'|text}
  const [report, setReport] = useState(null)
  const idle = !chat.running && chat.messages.length > 0

  const runReport = async (title, call) => {
    setReport({ title, body: 'loading' })
    try { setReport({ title, body: await call() }) }
    catch (e) { setReport(null); chat.toast(e.message, 'danger') }
  }

  // Smart autoscroll: follow only when the user is already at the bottom.
  useEffect(() => {
    const el = listRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [chat.messages, chat.typing])

  const onScroll = () => {
    const el = listRef.current
    if (!el) return
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  }

  const visible = search
    ? chat.messages.filter((m) =>
        (m.content || '').toLowerCase().includes(search.toLowerCase()) ||
        (m.persona || '').toLowerCase().includes(search.toLowerCase()))
    : chat.messages

  const endless = !chat.turn.max // max_turns 0 = endless run
  const pct = !endless ? Math.min(100, (chat.turn.current / chat.turn.max) * 100) : 0
  const dotClass = chat.running ? (chat.paused ? 'paused' : 'running') : 'idle'

  return (
    <main className="stage">
      <header className="stage-header">
        <span className={`status-dot ${dotClass}`} />
        <h1 className="topic" title={chat.topic}>{chat.topic || 'No conversation yet'}</h1>
        <div className="progress-wrap">
          <span className="progress-label">turn {chat.turn.current}/{endless ? '∞' : chat.turn.max}</span>
          {!endless && (
            <div className="progress"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
          )}
        </div>
        <span className="usage">{chat.usage.total_tokens.toLocaleString()} tok · ${chat.usage.estimated_cost.toFixed(4)}</span>
        <input
          className="input search"
          placeholder="search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </header>

      <div className="messages" ref={listRef} onScroll={onScroll}>
        {chat.messages.length === 0 && (
          <div className="hero">
            <h2>⬢ Auto Chat Studio</h2>
            <p>Assemble a cast of 2–10 AI personas — each on its own model, from any provider — set the scene, and watch them talk.</p>
            <p className="hero-hint">Personas stream in real time. Pause anytime to steer the topic or drop in a system event.</p>
          </div>
        )}
        {visible.map((m, i) => <Message key={i} msg={m} colors={colors} />)}
        {chat.typing && (
          <div className="typing">
            <span className="dot pulse" style={{ background: colors[chat.typing.index % colors.length] }} />
            {chat.typing.persona} is composing
            <span className="typing-dots"><i>·</i><i>·</i><i>·</i></span>
          </div>
        )}
      </div>

      <footer className="controls">
        <button
          className="btn btn-warn"
          disabled={!chat.running}
          onClick={async () => {
            try { await (chat.paused ? api.resume() : api.pause()) } catch { /* server state wins */ }
          }}
        >
          {chat.paused ? 'Resume' : 'Pause'}
        </button>
        <button
          className="btn btn-danger"
          disabled={!chat.running}
          onClick={() => api.stop().catch(() => {})}
        >
          Stop
        </button>
        <button
          className="btn btn-ghost"
          disabled={!chat.running || !chat.paused}
          onClick={onInterject}
        >
          Interject…
        </button>
        {idle && (
          <>
            <span className="divider" />
            <input
              className="input turns-input" type="number" min={1} max={200}
              value={moreTurns} title="How many more turns"
              onChange={(e) => setMoreTurns(+e.target.value || 1)}
            />
            <button
              className="btn btn-ghost"
              title="Keep the conversation going"
              onClick={() => api.continueRun(moreTurns).catch((e) => chat.toast(e.message, 'danger'))}
            >
              ▶ Continue
            </button>
            <button
              className="btn btn-ghost"
              title="Redo the last message"
              onClick={() => api.regenerate().catch((e) => chat.toast(e.message, 'danger'))}
            >
              ↻ Redo last
            </button>
            <button
              className="btn btn-ghost"
              title="Clear the stage for a fresh start (this conversation stays in History)"
              onClick={() => {
                if (!window.confirm('Clear the stage? The conversation is already saved in History.')) return
                api.clear().catch((e) => chat.toast(e.message, 'danger'))
              }}
            >
              🧹 Clear
            </button>
            <button
              className="btn btn-ghost"
              disabled={!summarizer?.model}
              title={summarizer?.model ? 'Summarize with the first cast member’s model' : 'Pick a model for the first cast member first'}
              onClick={() => runReport('Conversation Summary',
                async () => (await api.summarize(summarizer.provider, summarizer.model)).summary)}
            >
              ✦ Summarize
            </button>
            <button
              className="btn btn-ghost"
              disabled={!summarizer?.model}
              title="Score the participants and declare a winner"
              onClick={() => runReport('⚖ The Verdict',
                async () => (await api.judge(summarizer.provider, summarizer.model)).verdict)}
            >
              ⚖ Judge
            </button>
          </>
        )}
        <span className="status-text">{chat.status}</span>
        <span className="spacer" />
        {['md', 'html', 'json', 'txt'].map((fmt) => (
          <a
            key={fmt}
            className={`btn btn-ghost btn-xs ${chat.messages.length ? '' : 'disabled'}`}
            href={`/api/conversation/export?format=${fmt}`}
            download
          >
            ⭳ {fmt}
          </a>
        ))}
        {!chat.connected && <span className="reconnect">reconnecting…</span>}
      </footer>

      {report !== null && (
        <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && setReport(null)}>
          <div className="modal">
            <div className="modal-head">
              <h3>{report.title}</h3>
              <button className="icon-btn" onClick={() => setReport(null)}>✕</button>
            </div>
            {report.body === 'loading'
              ? <p className="muted">The model is deliberating…</p>
              : <div className="summary-body"
                     dangerouslySetInnerHTML={{ __html: marked.parse(report.body) }} />}
          </div>
        </div>
      )}
    </main>
  )
}
