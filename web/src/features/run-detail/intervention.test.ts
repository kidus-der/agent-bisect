import { describe, expect, it } from 'vitest'

import { interventionSummary } from './intervention'

describe('interventionSummary', () => {
  it('names the one field the intervention replaced', () => {
    // Arrange
    const diff = {
      step_idx: 7,
      original_tool_result: { reservation_id: 'NM1VX1', status: 'confirmed', origin: 'JFK' },
      replaced_tool_result: { reservation_id: 'ZFA04Y', status: 'confirmed', origin: 'JFK' },
    }

    // Act / Assert
    expect(interventionSummary(diff)).toEqual({
      field: 'reservation_id',
      before: 'NM1VX1',
      after: 'ZFA04Y',
    })
  })

  it('reports a field the intervention added', () => {
    const diff = {
      step_idx: 3,
      original_tool_result: { status: 'ok' },
      replaced_tool_result: { status: 'ok', error: 'tool_error' },
    }

    expect(interventionSummary(diff)).toEqual({
      field: 'error',
      before: 'absent',
      after: 'tool_error',
    })
  })

  it('is null when nothing was replaced', () => {
    const same = { reservation_id: 'NM1VX1' }
    expect(
      interventionSummary({
        step_idx: 7,
        original_tool_result: same,
        replaced_tool_result: { ...same },
      }),
    ).toBeNull()
  })

  it('is null when there is no intervention at all', () => {
    expect(interventionSummary(null)).toBeNull()
  })
})
