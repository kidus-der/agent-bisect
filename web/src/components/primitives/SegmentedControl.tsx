import { motion } from 'motion/react'
import { useId } from 'react'

import { layoutIds, useSpringTransition } from '@/design/motion'
import { cn } from '@/lib/utils'

export interface SegmentOption<T extends string> {
  readonly value: T
  readonly label: string
}

interface SegmentedControlProps<T extends string> {
  readonly options: ReadonlyArray<SegmentOption<T>>
  readonly value: T
  readonly onChange: (value: T) => void
  /** Accessible name for the group. */
  readonly label: string
  /** `sm` for a secondary control beside a primary one (direction.md §4). */
  readonly size?: 'sm' | 'md'
  /**
   * `segment` is one bordered control with a sliding indicator, `pills` a row
   * of separate chips, `tabs` an underlined row with no box at all. Two
   * controls on one page should not share a treatment, or they read as one
   * system (direction.md §4).
   */
  readonly variant?: 'segment' | 'pills' | 'tabs'
  readonly className?: string
}

/** A radio group drawn as one control; native radios give arrow-key navigation for free. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  size = 'md',
  variant = 'segment',
  className,
}: SegmentedControlProps<T>) {
  const pills = variant === 'pills'
  const tabs = variant === 'tabs'
  const boxed = !pills && !tabs
  const groupId = useId()
  const transition = useSpringTransition('snap')
  return (
    <fieldset
      className={cn(
        'inline-flex',
        pills && 'gap-1',
        tabs && 'gap-3 border-b border-line',
        boxed && 'rounded-control border border-line bg-ground p-0.5',
        className,
      )}
    >
      <legend className="sr-only">{label}</legend>
      {options.map((option) => {
        const checked = option.value === value
        return (
          <label
            key={option.value}
            className={cn(
              'relative inline-flex cursor-pointer items-center font-medium',
              pills && 'rounded-pill border',
              tabs && 'rounded-none border-b-2 pb-1',
              boxed && 'rounded-[4px]',
              size === 'sm' ? 'h-6 px-2.5 text-[12px]' : 'h-7 px-3 text-small',
              tabs && 'px-0',
              'has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus',
              pills && (checked ? 'border-ink-muted bg-elevated' : 'border-line'),
              tabs && (checked ? '-mb-px border-ink' : 'border-transparent'),
              checked ? 'text-ink' : 'text-ink-muted hover:text-ink',
            )}
          >
            <input
              type="radio"
              name={groupId}
              value={option.value}
              checked={checked}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {checked && boxed ? (
              <motion.span
                layoutId={layoutIds.segmentIndicator(groupId)}
                transition={transition}
                className="absolute inset-0 rounded-[4px] border border-line-strong bg-elevated"
              />
            ) : null}
            <span className="relative">{option.label}</span>
          </label>
        )
      })}
    </fieldset>
  )
}
