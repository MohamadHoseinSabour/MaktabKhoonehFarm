import React from 'react'

type Props = {
  value: number
}

export function ProgressBar({ value }: Props) {
  const safe = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0))
  return (
    <div className="progress-wrap" role="progressbar" aria-valuenow={safe} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-fill" style={{ width: `${safe}%` }} />
      <span className="progress-label">{safe.toFixed(1)}%</span>
    </div>
  )
}