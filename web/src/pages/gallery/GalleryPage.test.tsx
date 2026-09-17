import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { TooltipProvider } from '@/components/primitives/Tooltip'

import { GalleryPage } from './GalleryPage'

const INSTALLED_BKLIT_CHARTS = 11
const CHART_LOAD_TIMEOUT_MS = 15_000

describe('GalleryPage', () => {
  test(
    'renders every section and mounts one demo per installed Bklit chart',
    async () => {
      document.documentElement.setAttribute('data-theme', 'dark')
      const { container } = render(
        <TooltipProvider>
          <GalleryPage />
        </TooltipProvider>,
      )
      expect(screen.getByRole('heading', { level: 1, name: 'Design gallery' })).toBeInTheDocument()
      expect(
        screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent),
      ).toEqual(
        expect.arrayContaining([
          'Rewind to k',
          'Tokens',
          'Primitives',
          'Panels',
          'Tables and code',
          'States',
          'Charts',
        ]),
      )
      expect(screen.getByText('gallery · dark')).toBeInTheDocument()
      await waitFor(
        () =>
          expect(container.querySelectorAll('#charts [data-variant="chart"] figure')).toHaveLength(
            INSTALLED_BKLIT_CHARTS,
          ),
        { timeout: CHART_LOAD_TIMEOUT_MS },
      )
    },
    CHART_LOAD_TIMEOUT_MS + 5_000,
  )
})
