import React from 'react'

type Props = {
  status: string
}

const statusMap: Record<string, string> = {
  pending: 'badge badge-pending',
  downloading: 'badge badge-downloading',
  downloaded: 'badge badge-downloaded',
  processing: 'badge badge-processing',
  processed: 'badge badge-processed',
  uploading: 'badge badge-uploading',
  uploaded: 'badge badge-uploaded',
  error: 'badge badge-error',
  skipped: 'badge badge-skipped',
  not_available: 'badge badge-muted',
  scraping: 'badge badge-processing',
  scraped: 'badge badge-downloaded',
  ready_for_upload: 'badge badge-uploaded',
  completed: 'badge badge-uploaded',
}

export function StatusBadge({ status }: Props) {
  const className = statusMap[status] ?? 'badge badge-muted'
  return <span className={className}>{status.replaceAll('_', ' ')}</span>
}