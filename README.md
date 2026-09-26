# ISU figure skating coaching data

This repo scrapes coaching and choreography information for active figure skaters from the International Skating Union (ISU) results site and stores it in a single CSV file.

## Files

- `scraper.py` – downloads the ISU bio pages for all four disciplines (`pairs`, `men`, `women`, `dance`), parses the HTML, and extracts:

  - skater name
  - coach
  - choreographer
  - discipline (category)

  No single ISU page says whether a skater still competes, so a skater counts as active if any of these shows them competing recently (seasons start July 1):

  1. a result in their bio's championship table (Olympics, Worlds, Europeans, Four Continents, World Juniors, nationals) this season or last;
  2. a score on the ISU season's best list this season or last, which adds Grand Prix, Junior Grand Prix and Challenger events;
  3. an event on their Competition Results page named with this calendar year or last, which adds smaller internationals. Only checked when 1 and 2 both miss, since it costs a second page per skater.

  The bio's heading row of season labels says nothing on its own: it shows eight seasons whether or not the skater competed in them.

  Checked by hand against 55 skaters looked up online (September 2026): out of 40 skaters from the previous `data.csv`, this rule wrongly kept 3 who had stopped (all three last competed in January 2025, at an event named "2025") and wrongly dropped 1 who only skates at club events the ISU site doesn't list. The previous rule (season headings) wrongly kept 5, some retired for years.

  Bios are fetched concurrently (8 workers, with retries; a page that keeps failing is skipped), and a shrink guard refuses to overwrite `data.csv` if a scrape would lose more than 40% of its rows. A full run takes about 6–7 minutes.

- `data.csv` – the generated dataset with the columns:

  - `Category`
  - `Skater`
  - `Coach`
  - `Choreographer`

- `.github/workflows/autoupdate.yml` – GitHub Actions workflow that runs the scraper every Saturday, commits `data.csv` when it changed (commit message: `ISU: automated update`), and always commits a `last_run.txt` timestamp so the scheduled workflow never trips GitHub's 60-day inactivity auto-disable.

Run locally with `uv run scraper.py`.

## Tests

- `test_scraper.py` – offline tests with fake pages shaped like the real ones: season flip, retries when the server drops a page, skipping a bio that keeps failing, parsing, and the shrink guard.
- `test_live.py` – checks the real site still looks the way the scraper reads it, on a fixed sample: the 2026 Olympic champions and a few skaters born in 2010–2012.

`uv run pytest` runs both (about 10 seconds); `uv run pytest test_scraper.py` runs only the offline ones. They run on your machine only, not on GitHub.
