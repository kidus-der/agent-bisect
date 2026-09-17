import { useCallback, useEffect, useRef, useState } from 'react'

export type CopyStatus = 'idle' | 'copied' | 'failed'

const RESET_AFTER_MS = 1600

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Clipboard can be denied (permissions, insecure context); the caller shows "failed".
    return false
  }
}

interface UseCopyResult {
  readonly status: CopyStatus
  readonly copy: (text: string) => Promise<void>
}

export function useCopy(): UseCopyResult {
  const [status, setStatus] = useState<CopyStatus>('idle')
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const copy = useCallback(async (text: string): Promise<void> => {
    const ok = await copyText(text)
    setStatus(ok ? 'copied' : 'failed')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setStatus('idle'), RESET_AFTER_MS)
  }, [])

  return { status, copy }
}
