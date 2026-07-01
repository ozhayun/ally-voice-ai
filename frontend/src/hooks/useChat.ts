import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/services/api'
import { useAgentStore } from '@/store/agentStore'

export function useChat() {
  const sessionId = useAgentStore((s) => s.sessionId)
  const addMessage = useAgentStore((s) => s.addMessage)
  const setConfig = useAgentStore((s) => s.setConfig)

  const mutation = useMutation({
    mutationFn: (message: string) => api.sendMessage(message, sessionId),
    onMutate: (message) => {
      addMessage({ role: 'user', content: message })
    },
    onSuccess: (data) => {
      addMessage({
        role: 'assistant',
        content: data.reply,
        config: data.config ?? undefined,
      })
      if (data.config && data.vapi_assistant_id) {
        setConfig(data.config, data.vapi_assistant_id)
      }
    },
    onError: () => {
      toast.error('Failed to send message. Please try again.')
    },
  })

  return mutation
}
