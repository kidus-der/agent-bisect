import { ChevronDown } from 'lucide-react'
import { useId } from 'react'

import { cn } from '@/lib/utils'

import { ANY } from './datasetFilters'

export interface FilterOption {
  readonly value: string
  readonly label: string
}

interface FilterSelectProps {
  readonly label: string
  readonly value: string
  readonly options: readonly FilterOption[]
  readonly onChange: (value: string) => void
  /** Label for the pass-through "no filter" entry, e.g. `all fault types`. */
  readonly anyLabel: string
  readonly className?: string
}

/**
 * A native select, restyled. Native gives keyboard support, type-ahead and the
 * platform picker on a phone for free; nothing here needs a custom listbox.
 */
export function FilterSelect({
  label,
  value,
  options,
  onChange,
  anyLabel,
  className,
}: FilterSelectProps) {
  const selectId = useId()
  const active = value !== ANY
  return (
    <div className={cn('flex min-w-0 flex-col gap-1', className)}>
      <label htmlFor={selectId} className="label-instrument">
        {label}
      </label>
      <div className="relative">
        <select
          id={selectId}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={cn(
            'h-8 w-full cursor-pointer appearance-none rounded-control border bg-ground py-0 pr-7 pl-2.5 text-small text-ink',
            active ? 'border-measure/50' : 'border-line',
          )}
        >
          <option value={ANY}>{anyLabel}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 text-ink-muted"
        />
      </div>
    </div>
  )
}
