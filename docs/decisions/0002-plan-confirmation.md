# 0002 — Plan confirmation handling

- **Date:** 2026-09-17 01:55 MDT
- **Context:** the run was launched through `/ecc:plan`, whose template says to wait for user confirmation before writing code. The run prompt itself says "Don't wait for the user", "Begin now", and lists the first three actions.
- **Decision:** the prompt is the first source of truth (§1) and is the more specific instruction, so its "begin now" is taken as the confirmation. The plan is the prompt's own phase table (P0–P8), mirrored in `docs/LOOP_STATE.md`.
- **Safety:** stop conditions in §10 still apply; nothing destructive or paid is done without asking.
