| Stage | Count |
|---|---|
| base runs attempted | 173 |
| stable (>= 0.75 over 4 re-runs) | 57 |
| unstable | 16 |
| candidates tried | 167 |
| candidates: not flipped (faulted pass > 0.25) | 149 |
| candidates: repeated call before k (rejected) | 7 |
| candidates: infrastructure-lost | 118 |
| kept (faulted pass <= 0.25 at N=4) | 18 |

**Manifest sizes**

| Manifest | Items | Dev | Test |
|---|---|---|---|
| strict (primary; P3 gate evaluated on this) | 18 | 6 | 12 |
| extended (secondary; faulted pass <= 0.50, post hoc) | 26 | 9 | 17 |
| flaky world (unsplit; bounded, infra-limited attempt) | 3 | — | — |

**Strata (strict manifest)**

| Domain / fault type | Position | n |
|---|---|---|
| airline / missing_field | middle | 1 |
| airline / stale_record | early | 1 |
| airline / tool_error | early | 1 |
| airline / tool_error | late | 1 |
| airline / tool_error | middle | 2 |
| retail / missing_field | early | 1 |
| retail / missing_field | middle | 1 |
| retail / stale_record | early | 1 |
| retail / stale_record | middle | 1 |
| retail / tool_error | early | 4 |
| retail / tool_error | middle | 1 |
| retail / wrong_value | early | 3 |
