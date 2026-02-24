'use client'

import { FormEvent, useState } from 'react'

import { updateLinks } from '@/services/api'

type Props = {
  courseId: string
  showExpiredNotice?: boolean
}

type LinkBatchResult = {
  batch_id?: string | null
  matched: number
  created: number
  unmatched: number
  duplicates: number
  details: Array<Record<string, unknown>>
}

export function LinkManager({ courseId, showExpiredNotice = false }: Props) {
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
    <section className="panel stack" id="link-manager">
      <h3>بروزرسانی لینک‌های دانلود</h3>
      {showExpiredNotice && (
        <p className="operation-banner warn">لینک‌های دانلود منقضی شده‌اند. لطفاً بلاک جدید لینک‌ها را جهت ادامه دانلود جایگذاری کنید.</p>
      )}
      <form onSubmit={submit} className="stack">
        <textarea
          value={rawLinks}
          onChange={(e) => setRawLinks(e.target.value)}
          placeholder="تمام لینک‌های دانلود را اینجا الصاق کنید..."
          rows={8}
          dir="ltr"
          required
        />
        <button className="btn" disabled={loading} style={{ alignSelf: 'flex-start' }}>
          {loading ? 'در حال پایش...' : 'بروزرسانی لینک‌ها'}
        </button>
      </form>
      {error && <pre className="console" dir="ltr">{error}</pre>}
      {result && (
        <section className="link-result stack">
          <div className="row">
            <span className="badge badge-downloaded">یافت شده: {result.matched}</span>
            <span className="badge badge-processed">جدید ایجاد شده: {result.created}</span>
            <span className="badge badge-error">نامعتبر: {result.unmatched}</span>
            <span className="badge badge-muted">تکراری: {result.duplicates}</span>
          </div>
          <details>
            <summary style={{ cursor: 'pointer', opacity: 0.8 }}>مشاهده جزئیات کامل خروجی ({result.details.length})</summary>
            <pre className="console" dir="ltr" style={{ marginTop: '0.5rem' }}>
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
