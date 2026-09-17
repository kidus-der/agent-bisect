import { describe, expect, test } from 'vitest'

import {
  INSTANT,
  delayedSpring,
  layoutIds,
  springTransition,
  springs,
  staggerVariants,
} from './motion'

describe('motion presets', () => {
  test('match direction.md §4', () => {
    expect(springs.snap).toEqual({ stiffness: 500, damping: 34, mass: 0.7 })
    expect(springs.settle).toEqual({ stiffness: 260, damping: 28, mass: 1 })
    expect(springs.glide).toEqual({ stiffness: 160, damping: 22, mass: 1.1 })
    expect(springs.drift).toEqual({ stiffness: 90, damping: 18, mass: 1.3 })
    expect(springs.ticker).toEqual({ stiffness: 210, damping: 26, mass: 0.9 })
  })

  test('a spring transition is a spring, never a duration', () => {
    expect(springTransition('glide', false)).toEqual({ type: 'spring', ...springs.glide })
  })

  test('reduced motion turns every transition into an instant state change', () => {
    expect(springTransition('drift', true)).toBe(INSTANT)
    expect(INSTANT).toEqual({ duration: 0 })
  })

  test('reduced motion removes the stagger and the enter offset', () => {
    const reduced = staggerVariants('settle', 0.06, true)
    expect(reduced.container.shown).toEqual({ transition: INSTANT })
    expect(reduced.item.hidden).toEqual({ opacity: 1, y: 0 })
  })

  test('full motion staggers children and enters with transform + opacity only', () => {
    const full = staggerVariants('settle', 0.06, false)
    expect(full.container.shown).toEqual({ transition: { staggerChildren: 0.06 } })
    expect(Object.keys(full.item.hidden ?? {}).sort()).toEqual(['opacity', 'y'])
  })

  test('shared-layout ids are stable per run', () => {
    expect(layoutIds.runIdChip('run-041')).toBe('run-run-041-id')
    expect(layoutIds.runBlameStripe('a')).not.toBe(layoutIds.runBlameStripe('b'))
  })
})

describe('delayedSpring', () => {
  test('carries the delay on the named spring', () => {
    expect(delayedSpring('settle', false, 0.4)).toMatchObject({ type: 'spring', delay: 0.4 })
  })

  test('drops the delay entirely under reduced motion', () => {
    // Arrange / Act / Assert — a delayed instant change is still a wait.
    expect(delayedSpring('settle', true, 0.4)).toEqual(INSTANT)
  })
})
