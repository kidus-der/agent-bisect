/** Writes src/design/tokens.generated.css from the typed tokens. Run by predev/prebuild/pretest. */
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { buildTokensCss } from '../src/design/tokens-css.ts'

const OUTPUT_PATH = fileURLToPath(new URL('../src/design/tokens.generated.css', import.meta.url))

try {
  writeFileSync(OUTPUT_PATH, buildTokensCss(), 'utf8')
  process.stdout.write(`tokens: wrote ${OUTPUT_PATH}\n`)
} catch (error) {
  const reason = error instanceof Error ? error.message : String(error)
  process.stderr.write(`tokens: failed to write ${OUTPUT_PATH}: ${reason}\n`)
  process.exitCode = 1
}
