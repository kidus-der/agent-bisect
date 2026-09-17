import { createMemoryHistory } from '@tanstack/react-router'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { App } from './App'
import { createAppRouter } from './router'

function mockMeta(simulated: boolean | 'offline'): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => {
      if (simulated === 'offline') return Promise.reject(new TypeError('Failed to fetch'))
      const meta = { simulated, data_source: simulated ? 'fixture' : 'real' }
      const data = {
        ...meta,
        package_version: '0.1.0',
        tau2_commit: 'abc',
        agent_model: 'model-a',
        user_model: 'model-u',
        generated_at: '2026-09-17',
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data, error: null, meta }),
      })
    }),
  )
}

function renderAt(path: string): void {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }))
  render(<App router={router} />)
}

afterEach(() => vi.unstubAllGlobals())

describe('AppShell', () => {
  test('renders the five destinations, a skip link and the current page', async () => {
    mockMeta(true)
    renderAt('/runs')
    expect(await screen.findByRole('heading', { level: 1, name: 'Runs' })).toBeInTheDocument()
    const nav = screen.getAllByRole('navigation', { name: 'Primary' })[0]
    if (!nav) throw new Error('expected a primary nav')
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Overview', 'Runs', 'Benchmark', 'Live', 'PR checks'])
    expect(within(nav).getByRole('link', { name: 'Runs' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main')
  })

  test('flags simulated data from /api/meta, and shows the designed empty state', async () => {
    mockMeta(true)
    renderAt('/runs')
    expect(await screen.findByTestId('simulated-flag')).toHaveTextContent(/Simulated data/i)
    expect(
      await screen.findByText('bisect record --domain airline --tasks 0-19'),
    ).toBeInTheDocument()
  })

  test('does not flag recorded data as simulated', async () => {
    mockMeta(false)
    renderAt('/')
    expect(await screen.findByText(/Recorded/)).toBeInTheDocument()
    expect(screen.queryByTestId('simulated-flag')).toBeNull()
  })

  test('shows an error state with retry when the API is unreachable', async () => {
    mockMeta('offline')
    renderAt('/benchmark')
    expect(await screen.findByRole('alert')).toHaveTextContent(/Cannot reach the Bisect server/)
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByText('API offline')).toBeInTheDocument()
  })

  test('run detail takes its id from the route', async () => {
    mockMeta(true)
    renderAt('/runs/run-041')
    expect(await screen.findByRole('heading', { level: 1, name: 'run-041' })).toBeInTheDocument()
    expect(await screen.findByText('bisect blame run-041 --top 3 --n 8')).toBeInTheDocument()
  })

  test('unknown routes get the designed not-found state inside the shell', async () => {
    mockMeta(true)
    renderAt('/nope')
    expect(await screen.findByText('Nothing is recorded at this address')).toBeInTheDocument()
    expect(screen.getAllByRole('navigation', { name: 'Primary' }).length).toBeGreaterThan(0)
  })

  test('Ctrl+K opens the palette; typing and Enter navigates by keyboard alone', async () => {
    mockMeta(true)
    const user = userEvent.setup()
    renderAt('/')
    await screen.findByRole('heading', { level: 1, name: 'Overview' })
    await user.keyboard('{Control>}k{/Control}')
    const dialog = await screen.findByRole('dialog', { name: 'Command palette' })
    expect(within(dialog).getByRole('combobox')).toHaveFocus()
    await user.keyboard('bench{Enter}')
    expect(await screen.findByRole('heading', { level: 1, name: 'Benchmark' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  test('the palette can toggle the theme', async () => {
    mockMeta(true)
    const user = userEvent.setup()
    document.documentElement.setAttribute('data-theme', 'dark')
    renderAt('/')
    await user.click(await screen.findByRole('button', { name: 'Open command palette' }))
    await user.keyboard('toggle theme{Enter}')
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })

  test('the theme toggle button names the theme it switches to', async () => {
    mockMeta(true)
    const user = userEvent.setup()
    document.documentElement.setAttribute('data-theme', 'dark')
    renderAt('/')
    await user.click(await screen.findByRole('button', { name: 'Switch to light theme' }))
    expect(await screen.findByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(window.localStorage.getItem('bisect.theme')).toBe('light')
  })
})
