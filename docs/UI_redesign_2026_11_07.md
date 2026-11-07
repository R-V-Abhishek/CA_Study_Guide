# Interface redesign, 2026-11-07

Applies to both web apps (`web/apps/student`, `web/apps/curator`). They share one design layer in
`web/packages/workspace/tokens.css`, so the look changes in both at once.

## Why

The previous interface was a sage-green palette with a serif display face over a humanist sans, every
section in the same rounded white card, and a light sidebar that looked like the page it sat beside.
Nothing in it said "accounting", and the question reader, the screen used longest, had no reading
measure and a header that did not align with its own text column.

## Direction: a ledger

The subject is chartered-accountancy exam preparation, so the visual vocabulary is the ledger book.

| Device | Where it appears | What it means |
| --- | --- | --- |
| Red double margin rule | Left edge of every content screen, sign-in panel, brand mark | The page margin of a ledger |
| Double underline | Section headings (`h2`), question header, answer block | A total or a closed section |
| Single heavy rule under table headings | `th` | Column heads |
| Red left rule on the answer | Revealed answers, selected question part | Marking-ink correction |
| Dark navy rail | Sidebar, mobile tab bar, reader toolbar | Fixed navigation stays apart from the reading surface |

Palette (tokens in `tokens.css`, light and dark):

- Paper `#F1F3F7` / `#0D1220`, surface `#FFFFFF` / `#151C2E`
- Ink `#121A2E` / `#E7EBF5`
- Ink blue accent `#2438A8` / `#9DB0FF` for actions and links
- Margin red `#C23A2C` / `#FF8A7A` for the margin rule, the current location and review counts
- Success, warning and error keep their own greens, ambers and reds

Type: Bricolage Grotesque for headings and large figures, IBM Plex Sans for everything else, with
tabular figures for marks, minutes and dates. Both are self-hosted variable fonts
(`web/packages/workspace/fonts/README.md` lists source and hashes). Radius is 4px everywhere.

## What changed, in build order

1. Shared base: tokens, type, buttons, tables, dialogs, rail shell for both apps, dark-rail navigation dialogs.
2. Question reader: aligned header with a double rule, 720px reading measure, underline tabs, red-ruled answer,
   dark toolbar. The outline now wraps below the text on a narrow canvas instead of squeezing the question
   into a sliver (found by the 200% zoom test).
3. Today: "Continue studying" leads, sections are ruled not boxed, the progress count is a large figure,
   the waiting-for-review notice has a red top rule.
4. Papers, Syllabus, Progress, Plan, Revision, Questions, Profile and the curator pages take the new base
   through shared classes (cards, rows, tabs, tables, controls).

Legacy Tailwind colour utilities are still remapped to the tokens in `tokens.css`; removing them means
rewriting utility classes in about 40 files and is not part of this change.

## Not changed

Routes, data contracts, keyboard behaviour, accessibility roles and the demo-mode switch are unchanged.
