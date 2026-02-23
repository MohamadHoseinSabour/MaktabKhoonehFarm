'use client'

import { FormEvent, useState } from 'react'

import { updateLinks } from '@/services/api'

type Props = {
  courseId: string
}

export function LinkManager({ courseId }: Props) {
  const [rawLinks, setRawLinks] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setResult(null)
    try {
      const response = await updateLinks(courseId, rawLinks)
      setResult(JSON.stringify(response))
      setRawLinks('')
    } catch (error) {
      setResult((error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel">
      <h3>Refresh Links</h3>
      <form onSubmit={submit} className="stack">
        <textarea
          value={rawLinks}
          onChange={(e) => setRawLinks(e.target.value)}
          placeholder="Paste all download links"
          rows={8}
          required
        />
        <button className="btn" disabled={loading}>
          {loading ? 'Parsing...' : 'Apply Link Batch'}
        </button>
      </form>
      {result && <pre className="console">{result}</pre>}
    </section>
  )
}