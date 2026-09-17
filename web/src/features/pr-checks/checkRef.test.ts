import { describe, expect, test } from 'vitest'

import { checkBadge, scenarioDelta } from './checkRef'

describe('checkBadge', () => {
  test('is the pull request number when the gate ran on one', () => {
    expect(checkBadge(1000)).toBe('#1000')
  })

  test('is nothing at all when the gate compared two refs', () => {
    // Assert — a real gate run compares git refs, which need not be a pull
    // request. The check's own title already reads "base_ref → head_ref", so
    // the badge is omitted rather than filled with a placeholder number.
    expect(checkBadge(null)).toBeNull()
  })
})

describe('scenarioDelta', () => {
  test('is the change between the two refs', () => {
    expect(scenarioDelta({ base_pass_rate: 0.9, head_pass_rate: 0.3, n: 4, scenario: 'a' })).toBe(
      0.9 * -1 + 0.3,
    )
  })

  test('is null for a scenario that is new in head', () => {
    // There is no base run to compare against, and 0.3 - 0 = +30 points would
    // be an invented improvement.
    expect(
      scenarioDelta({ base_pass_rate: null, head_pass_rate: 0.3, n: 4, scenario: 'a' }),
    ).toBeNull()
  })
})
