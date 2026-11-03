import { Wallet } from 'lucide-react'

/** Neutral PayPal integration marker (wordmark text + generic icon; no PayPal logo artwork). */
export function PayPalMark({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const box = size === 'lg' ? 'h-12 w-12 rounded-2xl' : size === 'sm' ? 'h-6 w-6 rounded-md' : 'h-9 w-9 rounded-xl'
  const icon = size === 'lg' ? 'h-6 w-6' : size === 'sm' ? 'h-3.5 w-3.5' : 'h-4.5 w-4.5'
  return (
    <span className={`inline-flex shrink-0 items-center justify-center bg-[#003087] text-white ${box}`} aria-hidden>
      <Wallet className={icon} />
    </span>
  )
}
