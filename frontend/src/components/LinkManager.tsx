'use client'

import { FormEvent, useState } from 'react'

import { updateLinks } from '@/services/api'

type Props = {
  courseId: string
}

type LinkBatchResult = {
  batch_id?: string | null
  matched: number
  created: number
  unmatched: number
  duplicates: number
  details: Array<Record<string, unknown>>
}

export function LinkManager({ courseId }: Props) {
  const [rawLinks, setRawLinks] = useState('')
  const [result, setResult] = useState<LinkBatchResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const response = await updateLinks(courseId, rawLinks)
      setResult(response as LinkBatchResult)
      setRawLinks('')
    } catch (error) {
      setError((error as Error).message)
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
      {error && <pre className="console">{error}</pre>}
      {result && (
        <section className="link-result stack">
          <div className="row">
            <span className="badge badge-downloaded">Matched: {result.matched}</span>
            <span className="badge badge-processed">Created: {result.created}</span>
            <span className="badge badge-error">Unmatched: {result.unmatched}</span>
            <span className="badge badge-muted">Duplicates: {result.duplicates}</span>
          </div>
          <details>
            <summary>Show parsed details ({result.details.length})</summary>
            <pre className="console">
              {JSON.stringify(
                result.details.length > 80
                  ? [...result.details.slice(0, 80), { info: `truncated ${result.details.length - 80} more rows` }]
                  : result.details,
                null,
                2
              )}
            </pre>
          </details>
        </section>
      )}
    </section>
  )
}
