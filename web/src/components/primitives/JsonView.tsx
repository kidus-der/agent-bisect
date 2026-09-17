import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { CopyButton } from './CopyButton'
import { InstrumentLabel } from './InstrumentLabel'

export type JsonValue =
  string | number | boolean | null | readonly JsonValue[] | { readonly [key: string]: JsonValue }

interface JsonViewProps {
  readonly value: JsonValue
  readonly label?: string
  readonly className?: string
}

const INDENT = '  '

function isJsonObject(value: JsonValue): value is { readonly [key: string]: JsonValue } {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Neutral-only syntax tones: keys carry the weight, punctuation recedes. No decorative hues. */
function renderValue(value: JsonValue, depth: number): ReactNode {
  if (value === null) return <span className="text-ink-muted italic">null</span>
  if (typeof value === 'string')
    return <span className="text-ink-muted">{JSON.stringify(value)}</span>
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span className="font-medium text-ink">{String(value)}</span>
  }
  const pad = INDENT.repeat(depth + 1)
  const closePad = INDENT.repeat(depth)
  if (isJsonObject(value)) {
    const entries = Object.entries(value)
    if (entries.length === 0) return <span className="text-ink-muted">{'{}'}</span>
    return (
      <>
        <span className="text-ink-muted">{'{'}</span>
        {entries.map(([key, child], index) => (
          <span key={key}>
            {'\n'}
            {pad}
            <span className="text-ink">{JSON.stringify(key)}</span>
            <span className="text-ink-muted">: </span>
            {renderValue(child, depth + 1)}
            {index < entries.length - 1 ? <span className="text-ink-muted">,</span> : null}
          </span>
        ))}
        {'\n'}
        {closePad}
        <span className="text-ink-muted">{'}'}</span>
      </>
    )
  }
  const items = value as readonly JsonValue[]
  if (items.length === 0) return <span className="text-ink-muted">[]</span>
  return (
    <>
      <span className="text-ink-muted">[</span>
      {items.map((child, index) => (
        // Array positions are the identity of JSON array items.
        <span key={index}>
          {'\n'}
          {pad}
          {renderValue(child, depth + 1)}
          {index < items.length - 1 ? <span className="text-ink-muted">,</span> : null}
        </span>
      ))}
      {'\n'}
      {closePad}
      <span className="text-ink-muted">]</span>
    </>
  )
}

export function JsonView({ value, label, className }: JsonViewProps) {
  return (
    <figure className={cn('min-w-0 rounded-chart border border-line bg-ground', className)}>
      <figcaption className="flex h-9 items-center justify-between border-b border-line pr-1 pl-3">
        <InstrumentLabel>{label ?? 'json'}</InstrumentLabel>
        <CopyButton text={JSON.stringify(value, null, 2)} subject={label ?? 'JSON'} />
      </figcaption>
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be keyboard reachable (axe: scrollable-region-focusable) */}
      <pre tabIndex={0} className="overflow-x-auto p-3 font-mono text-small leading-[1.6]">
        <code>{renderValue(value, 0)}</code>
      </pre>
    </figure>
  )
}
