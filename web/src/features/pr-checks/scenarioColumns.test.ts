import { describe, expect, test } from 'vitest'

import type { ScenarioRow } from './api'
import { scenarioColumns } from './scenarioColumns'

const SCALE = 0.67

const ROW: ScenarioRow = {
  scenario: 'reschedule_flight_change-08',
  base_pass_rate: 0.93,
  head_pass_rate: 0.26,
  n: 4,
}

function ids(narrow: boolean): readonly string[] {
  return scenarioColumns(SCALE, narrow).map((column) => column.id)
}

describe('scenarioColumns', () => {
  test('the wide table carries every measurement', () => {
    expect(ids(false)).toEqual(['scenario', 'delta', 'base', 'head', 'n'])
  })

  test('the narrow table keeps the change, which is what the table is read for', () => {
    // Assert — a row that is only a name and a coloured bar states nothing a
    // reader can quote; the change is the column that must survive.
    expect(ids(true)).toContain('delta')
  })

  test('the narrow table pairs base and head instead of dropping them', () => {
    // Arrange / Act
    const columns = scenarioColumns(SCALE, true)
    const pair = columns.find((column) => column.id === 'pass')

    // Assert
    expect(pair).toBeDefined()
    expect(ids(true)).not.toContain('base')
    expect(ids(true)).not.toContain('head')
  })

  test('the run count is the first thing dropped', () => {
    expect(ids(true)).not.toContain('n')
    expect(ids(false)).toContain('n')
  })

  test('sorting still works on every narrow column', () => {
    // A column a reader can see but not sort by is a regression against the
    // wide table, where all of them sort.
    for (const column of scenarioColumns(SCALE, true)) {
      expect(column.sortValue).toBeTypeOf('function')
      expect(column.sortValue?.(ROW)).toBeDefined()
    }
  })
})
