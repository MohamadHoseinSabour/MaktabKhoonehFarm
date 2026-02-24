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

const statusFa: Record<string, string> = {
  pending: 'در انتظار',
  downloading: 'در حال دانلود',
  downloaded: 'دانلود شده',
  processing: 'در حال پردازش',
  processed: 'پردازش شده',
  uploading: 'درحال آپلود',
  uploaded: 'آپلود شده',
  error: 'خطا',
  skipped: 'رد شده',
  not_available: 'ناموجود',
  scraping: 'در حال استخراج',
  scraped: 'استخراج شده',
  ready_for_upload: 'آماده آپلود',
  completed: 'تکمیل شده',
}

export function StatusBadge({ status }: Props) {
  const className = statusMap[status] ?? 'badge badge-muted'
  const label = statusFa[status] ?? status.replaceAll('_', ' ')
  return <span className={className}>{label}</span>
}