import { RewindLoop } from '@/components/rewind/RewindLoop'
import { useTheme } from '@/design/theme'
import { PageHeader } from '@/pages/PageHeader'

import { ChartsSection } from './ChartsSection'
import { DataSection } from './DataSection'
import { GallerySection } from './GallerySection'
import { PrimitivesSection } from './PrimitivesSection'
import { PanelsSection, StatesSection } from './StatesSection'
import { TokensSection } from './TokensSection'

export function GalleryPage() {
  const { theme } = useTheme()
  return (
    <>
      <PageHeader
        label={`gallery · ${theme}`}
        title="Design gallery"
        description="Every token, primitive, state and chart in the current theme. All values on this page are illustrative, not measurements."
      />
      <div className="flex flex-col gap-12">
        <GallerySection
          id="signature"
          index="01"
          title="Rewind to k"
          description="The product in one loop: record, fail, rewind, replace one thing, re-run, blame."
        >
          <RewindLoop />
        </GallerySection>
        <GallerySection
          id="tokens"
          index="02"
          title="Tokens"
          description="Generated from src/design/tokens.ts. Colour is semantic or it is not there."
        >
          <TokensSection />
        </GallerySection>
        <GallerySection
          id="primitives"
          index="03"
          title="Primitives"
          description="Small parts with fixed rules: outcomes carry glyphs, blame carries a number, estimates carry intervals."
        >
          <PrimitivesSection />
        </GallerySection>
        <GallerySection
          id="panels"
          index="04"
          title="Panels"
          description="Radius and elevation vary together, so a screen never reads as a grid of identical cards."
        >
          <PanelsSection />
        </GallerySection>
        <GallerySection
          id="data"
          index="05"
          title="Tables and code"
          description="Dense rows, tabular numerals, literal machine text."
        >
          <DataSection />
        </GallerySection>
        <GallerySection
          id="states"
          index="06"
          title="States"
          description="Loading, empty and error are designed views, not afterthoughts."
        >
          <StatesSection />
        </GallerySection>
        <GallerySection
          id="charts"
          index="07"
          title="Charts"
          description="The eleven Bklit charts behind the chart theme bridge. Cyan measures, violet judges, slate is the control."
        >
          <ChartsSection />
        </GallerySection>
      </div>
    </>
  )
}
