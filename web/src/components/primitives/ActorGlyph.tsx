import { Bot, Gavel, type LucideIcon, User, Wrench } from 'lucide-react'

import { cn } from '@/lib/utils'

export type Actor = 'agent' | 'user' | 'tool' | 'evaluator'

interface ActorGlyphProps {
  readonly actor: Actor
  readonly size?: 'sm' | 'md'
  /** Show the actor name next to the glyph; otherwise it is the accessible name only. */
  readonly showLabel?: boolean
  readonly className?: string
}

const ACTOR_ICONS: Readonly<Record<Actor, LucideIcon>> = {
  agent: Bot,
  user: User,
  tool: Wrench,
  evaluator: Gavel,
}
const ACTOR_LABELS: Readonly<Record<Actor, string>> = {
  agent: 'Agent',
  user: 'User',
  tool: 'Tool',
  evaluator: 'Evaluator',
}

/** Who acted at a step. Shape carries the meaning; the glyph stays neutral. */
export function ActorGlyph({ actor, size = 'md', showLabel = false, className }: ActorGlyphProps) {
  const Icon = ACTOR_ICONS[actor]
  const label = ACTOR_LABELS[actor]
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-ink-muted', className)}>
      <span
        role="img"
        aria-label={showLabel ? undefined : label}
        aria-hidden={showLabel ? true : undefined}
        className={cn(
          'inline-flex items-center justify-center rounded-step border border-line-strong bg-elevated',
          size === 'sm' ? 'size-5' : 'size-6',
        )}
      >
        <Icon aria-hidden="true" className={size === 'sm' ? 'size-3' : 'size-3.5'} />
      </span>
      {showLabel ? <span className="text-small">{label}</span> : null}
    </span>
  )
}
