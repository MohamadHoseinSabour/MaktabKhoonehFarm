'use client'

import { useEffect, useRef, useState } from 'react'

export function useWebSocket(url: string | null) {
  const [messages, setMessages] = useState<Record<string, unknown>[]>([])
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!url) {
      return
    }

    const socket = new WebSocket(url)
    socketRef.current = socket

    socket.onopen = () => {
      setConnected(true)
      socket.send('subscribe')
    }

    socket.onclose = () => {
      setConnected(false)
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        setMessages((prev) => [payload, ...prev].slice(0, 300))
      } catch {
        // Ignore malformed messages from external proxies.
      }
    }

    return () => {
      socket.close()
    }
  }, [url])

  return { connected, messages }
}