import { useNavigate } from 'react-router-dom'
import { useCallback } from 'react'

type NavigateFn = ReturnType<typeof useNavigate>

/**
 * View Transitions API destekliyorsa animasyonlu geçiş,
 * yoksa normal navigate.
 */
export function useViewTransition() {
  const navigate = useNavigate()

  const vtNavigate: NavigateFn = useCallback(
    (to: any, opts?: any) => {
      if ('startViewTransition' in document) {
        ;(document as any).startViewTransition(() => navigate(to, opts))
      } else {
        navigate(to, opts)
      }
    },
    [navigate]
  )

  return vtNavigate
}
