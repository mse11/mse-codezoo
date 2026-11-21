# CodeZoo pilot kit

Everything needed to run a first pilot: 5–8 children aged 8–12, about 30 minutes each, on real devices. The pilot is the gate of phases 1–6 in [IMPLEMENTATION_PLAN.md](../../IMPLEMENTATION_PLAN.md); its results tell us whether CodeZoo works for children before more content is built.

| File | For | Use it |
| --- | --- | --- |
| [parent-letter.md](parent-letter.md) / [parent-letter.sk.md](parent-letter.sk.md) | Parents | Before the pilot: what happens, what is recorded, consent form |
| [facilitator-guide.md](facilitator-guide.md) | Whoever runs the session | Before and during: setup, what to say, when (not) to help |
| [observation-sheet.md](observation-sheet.md) | The facilitator | During: one sheet per child, printed |
| [device-checklist.md](device-checklist.md) | The facilitator | Before: every device through the device check |
| [teacher-app.md](teacher-app.md) | Teachers | Starting the classroom hub without installing Python |

## How data flows

1. A grown-up turns on **Take part in a pilot** (Grown-ups area, or the teacher's screen in a class). From then on CodeZoo records the pilot metrics on that computer. Nothing is recorded before that, or in private mode.
2. The child plays. A few questions come before and after each of modules 1–5. Once a day, a solved level asks "Would you like to play again?" with five smileys.
3. After the pilot, the grown-up presses **Export pilot data**. The screen lists what the file holds. The file is saved only after they tick "I agree".
4. They send the file to the project maintainer by hand (for example by email). CodeZoo never sends anything itself.
5. The maintainer merges the files:

   ```bash
   uv run codezoo pilot report codezoo-pilot-*.json -o pilot-report.md
   ```

   The report shows every pilot metric next to its target. After the report is made, the raw files are deleted and only the report is kept (see the parent letter).

## What the export holds

A random pilot id per player (like `P-7KX3MQ`) and an age band; per level: tries, solved or not, stars, and hints shown before solving; per module: right answers before and after; minutes to the first star; how many errors the page saw; the smileys; the kinds of mistakes (for example "loops that never stop").

It holds **no** names, pictures, programs, typed text, device names or addresses. With a small pilot, people can still sometimes be recognised from such data, so the files are handled as personal data.

## Before the first pilot (maintainer)

- [ ] Fill in the contact details in both parent letters (they are placeholders on purpose)
- [ ] Decide the retention period and write it into the letters (default in the letters: raw files deleted within 30 days of the report)
- [ ] Have a teacher review the concept-check questions (`mse_codezoo/content/checks.json`, marked `"reviewed": false`)
- [ ] Run the device check on every pilot device
