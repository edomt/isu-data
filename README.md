# ISU figure skating coaching data

This repo scrapes coaching and choreography information for active figure skaters from the International Skating Union (ISU) results site and stores it in a single CSV file.

## Files

- `scraper.py` – downloads the ISU bio pages for all four disciplines (`pairs`, `men`, `women`, `dance`), parses the HTML, and extracts:

  - skater name
  - coach
  - choreographer
  - discipline (category)

  A skater counts as active if their bio mentions the current season, which is derived automatically from the date: the season string flips every November 1, once most of the field has competed in the new season (bios only mention a season after the skater's first event in it, so flipping on the official July 1 season start would empty the dataset). Bios are fetched concurrently (8 workers, with retries), and a shrink guard refuses to overwrite `data.csv` if a scrape would lose more than 40% of its rows.

- `data.csv` – the generated dataset with the columns:

  - `Category`
  - `Skater`
  - `Coach`
  - `Choreographer`

- `.github/workflows/autoupdate.yml` – GitHub Actions workflow that runs the scraper every Saturday, commits `data.csv` when it changed (commit message: `ISU: automated update`), and always commits a `last_run.txt` timestamp so the scheduled workflow never trips GitHub's 60-day inactivity auto-disable.

Run locally with `uv run scraper.py`.
