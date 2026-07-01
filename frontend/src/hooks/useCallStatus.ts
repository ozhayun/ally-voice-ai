import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useCallStore } from '@/store/callStore'
import { api } from '@/services/api'
import type { CallStatus } from '@/types'

const TERMINAL: CallStatus[] = ['ended', 'failed', 'error']

export function useCallStatus(callId: string | null) {
  const setCallStatus = useCallStore((s) => s.setCallStatus)
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!callId) return
    const es = new EventSource(`/api/calls/status/${callId}`)
    es.onmessage = (e: MessageEvent) => {
      const data = JSON.parse(e.data as string) as { status: CallStatus }
      setCallStatus(data.status)
      if (TERMINAL.includes(data.status)) {
        es.close()
        // Directly tell backend to create a log for this call (works even if webhook/SSE missed it)
        void api.syncCallLog(callId).catch(() => null)
        // Refresh logs and agents after giving backend time to fetch from Vapi
        setTimeout(() => {
          void queryClient.invalidateQueries({ queryKey: ['callLogs'] })
          void queryClient.invalidateQueries({ queryKey: ['agents'] })
        }, 6000)
      }
    }
    es.onerror = () => {
      setCallStatus('error')
      es.close()
      // Still try to sync even on SSE error (backend restart, network blip)
      void api.syncCallLog(callId).catch(() => null)
      setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ['callLogs'] })
        void queryClient.invalidateQueries({ queryKey: ['agents'] })
      }, 6000)
    }
    return () => es.close()
  }, [callId, setCallStatus, queryClient])
}
