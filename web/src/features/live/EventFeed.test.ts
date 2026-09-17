import { describe, expect, test } from 'vitest'

import { parseEventMessage } from './EventFeed'

describe('parseEventMessage', () => {
  test('lifts the simulated marker and the phase out of the message', () => {
    // Arrange / Act
    const parsed = parseEventMessage('simulated: blame batch 29827420 progressed')

    // Assert
    expect(parsed).toEqual({
      simulated: true,
      phase: 'blame',
      detail: 'batch 29827420 progressed',
    })
  })

  test('reads a real (unsimulated) message the same way', () => {
    expect(parseEventMessage('eval batch 41 progressed')).toEqual({
      simulated: false,
      phase: 'eval',
      detail: 'batch 41 progressed',
    })
  })

  test('leaves a message it does not recognise entirely alone', () => {
    // Arrange — nothing is invented for a shape the server has not used before.
    const message = 'rate limiter tripped; backing off for 4s'

    // Act / Assert
    expect(parseEventMessage(message)).toEqual({
      simulated: false,
      phase: null,
      detail: message,
    })
  })

  test('does not mistake a one-word message for a phase', () => {
    expect(parseEventMessage('reconnected').phase).toBeNull()
  })
})
