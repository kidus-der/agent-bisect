import { formatPercent, wilsonInterval } from '@/lib/stats'
import { cn } from '@/lib/utils'

import type { FaultType, HeatmapCell, MethodName } from './api'
import { FAULT_TYPE_LABELS, methodLabel } from './methods'

interface HeatmapTableProps {
  readonly faultTypes: readonly FaultType[]
  readonly methods: readonly MethodName[]
  readonly cellAt: (fault: FaultType, method: MethodName) => HeatmapCell | undefined
  readonly caption: string
  /** Visually hidden when the matrix is on screen; this stays the accessible path. */
  readonly hidden: boolean
}

/**
 * The matrix as a real table. Always in the DOM: the coloured grid is decorative
 * (`aria-hidden`) and this is what a screen reader, a text search or a copy-paste
 * actually gets. It also carries the Wilson interval and n, which do not fit in a cell.
 */
export function HeatmapTable({ faultTypes, methods, cellAt, caption, hidden }: HeatmapTableProps) {
  return (
    <div className={cn(hidden ? 'sr-only' : 'min-w-0 overflow-x-auto')}>
      <table className="w-full border-separate border-spacing-0 text-left">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="h-9 border-b border-line px-3 label-instrument font-medium">
              fault type
            </th>
            {methods.map((method) => (
              <th
                key={method}
                scope="col"
                className="h-9 border-b border-line px-3 text-right label-instrument font-medium whitespace-nowrap"
              >
                {methodLabel(method)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {faultTypes.map((fault) => (
            <tr key={fault}>
              <th
                scope="row"
                className="border-b border-line px-3 py-2 text-small font-medium whitespace-nowrap text-ink"
              >
                {FAULT_TYPE_LABELS[fault]}
              </th>
              {methods.map((method) => {
                const cell = cellAt(fault, method)
                const interval = cell ? wilsonInterval(cell.accuracy, cell.n) : null
                return (
                  <td
                    key={method}
                    className="border-b border-line px-3 py-2 text-right num text-small whitespace-nowrap"
                  >
                    {cell ? (
                      <>
                        <span className="text-ink">{formatPercent(cell.accuracy)}</span>{' '}
                        <span className="text-ink-muted">
                          {interval
                            ? `[${formatPercent(interval.low)}, ${formatPercent(interval.high)}]`
                            : ''}{' '}
                          n={cell.n}
                        </span>
                      </>
                    ) : (
                      <span className="text-ink-muted">not measured</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
