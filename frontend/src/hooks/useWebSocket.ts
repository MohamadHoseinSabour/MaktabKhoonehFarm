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

    let disposed = false
    const socket = new WebSocket(url)
    socketRef.current = socket

    socket.onopen = () => {
      if (disposed) return
      setConnected(true)
      socket.send('subscribe')
    }

    socket.onclose = () => {
      if (disposed) return
      setConnected(false)
    }

    socket.onmessage = (event) => {
      if (disposed) return
      try {
        const payload = JSON.parse(event.data)
        setMessages((prev) => [payload, ...prev].slice(0, 300))
      } catch {
        // Ignore malformed messages from external proxies.
      }
    }

    return () => {
      disposed = true
      socketRef.current = null
      setConnected(false)
      if (socket.readyState === WebSocket.CONNECTING) {
        socket.addEventListener(
          'open',
          () => {
            socket.close(1000, 'component-unmounted')
          },
          { once: true }
        )
        return
      }
      if (socket.readyState === WebSocket.OPEN) {
        socket.close(1000, 'component-unmounted')
      }
    }
  }, [url])

  return { connected, messages }
}
