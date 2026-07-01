import { create } from 'zustand'
import type { CallStatus } from '@/types'

type CallStoreState = {
  callStatus: CallStatus
  callId: string | null
}

type CallStoreActions = {
  setCallStatus: (status: CallStatus) => void
  setCallId: (id: string | null) => void
  reset: () => void
}

type CallStore = CallStoreState & CallStoreActions

export const useCallStore = create<CallStore>()((set) => ({
  callStatus: 'idle',
  callId: null,

  setCallStatus: (status) => set({ callStatus: status }),
  setCallId: (id) => set({ callId: id }),
  reset: () => set({ callStatus: 'idle', callId: null }),
}))
