'use client'

type Props = {
  connected: boolean
  messages: Record<string, unknown>[]
}

export function DebugConsole({ connected, messages }: Props) {
  return (
    <section className="panel">
      <div className="row-between">
        <h3>Live Debug Console</h3>
        <span className={connected ? 'online' : 'offline'}>{connected ? 'Connected' : 'Disconnected'}</span>
      </div>
      <div className="console">
        {messages.length === 0 && <p>No live logs yet.</p>}
        {messages.map((message, index) => (
          <pre key={index}>{JSON.stringify(message, null, 2)}</pre>
        ))}
      </div>
    </section>
  )
}