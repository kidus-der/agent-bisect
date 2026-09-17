/**
 * The token used for "the part that is not spent yet" — the budget gauge's
 * unfilled ticks and the headroom ring's track.
 *
 * Both are data marks: they are what shows the remaining portion, so WCAG
 * 1.4.11 asks for 3:1 against the card they sit on. `line` (≈1.2:1 on white)
 * and `line-strong` (≈1.7:1) are hairline tokens and do not reach it. From-tape
 * slate does, in both themes, and means exactly the right thing: nothing has
 * happened here yet.
 */
import { roleColour } from '@/components/chart-theme/chartTheme'
import type { RoleName } from '@/design/tokens'

export const REMAINING_MARK_ROLE: RoleName = 'tape'

export const REMAINING_MARK = roleColour(REMAINING_MARK_ROLE)
