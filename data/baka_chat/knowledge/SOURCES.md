# Source Registry

This directory starts with original summaries, not copied commercial text. The
runtime manifest marks their authority as `curated_canon_summary` or `fanon`.

Use these source classes when expanding the library:

1. Official game scripts, character settings, manuals, endings, and readme
   files from legally owned Touhou Project games.
2. Official publications written or supervised by ZUN, with work, volume,
   chapter, language, and edition recorded.
3. Official music CD stories and track comments.
4. ZUN interviews with publisher, date, interviewer, and full context.
5. Official Touhou Yomoyama News and Shanghai Alice announcements.
6. Reference wikis only as indexes. Verify important claims against a higher
   authority source before marking them canonical.

Official starting points verified on 2026-07-17:

- https://www16.big.or.jp/~zun/
- https://touhou-project.news/
- https://touhou-project.news/guideline/
- https://touhou-project.news/titles/
- https://touhou-project.news/news/13976/
- https://store.steampowered.com/app/3671710/__Fossilized_Wonders/
- https://www.kadokawa.co.jp/product/322508000622/

For every added file, add a `manifest.json` entry with `authority`, `work`,
`citation`, `tags`, and `priority`. Keep fan translations and fanon explicitly
labelled; do not place them in an official source class.
