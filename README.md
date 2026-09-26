# ISU figure skating coaching data

Coaches and choreographers of active figure skaters, scraped weekly from the International Skating Union (ISU) results site into a single CSV file.

## Data

`data.csv` has one row per active skater (or pair / ice dance team):

| Column | Content |
|---|---|
| `Category` | Men, Women, Pairs or Dance |
| `Skater` | Skater or team name |
| `Coach` | Current coach(es) |
| `Choreographer` | Current choreographer(s) |

Skaters whose bio lists neither a coach nor a choreographer are left out.

## How it works

`scraper.py` collects skaters from each discipline's list page and from the ISU season's best lists for this season and last, then reads each skater's bio page.

A skater counts as active if any of these shows them competing recently (seasons start July 1):

1. a result in the bio's championship table (Olympics, Worlds, Europeans, Four Continents, World Juniors, nationals) this season or last;
2. a score on the season's best list this season or last (adds Grand Prix, Junior Grand Prix and Challenger events);
3. an event on the skater's Competition Results page named with this calendar year or last (adds smaller international events).

The third check needs a second page per skater, so it only runs when the first two miss. Because event names carry a year but no date, a skater can stay listed for up to about a year after they stop competing.

Pages are fetched in parallel, with retries; a page that keeps failing is skipped for that run. The scraper refuses to overwrite `data.csv` if the new version would lose more than 40% of its rows.

## Running

```sh
uv run scraper.py
```

A full run takes about 5–7 minutes.

## Automation

`.github/workflows/autoupdate.yml` runs the scraper every Saturday and commits `data.csv` when it changes. It also commits a `last_run.txt` timestamp every time, so GitHub never disables the schedule for inactivity. The Python version is pinned in `.python-version`.

## Tests

```sh
uv run pytest                   # everything
uv run pytest test_scraper.py   # offline only
```

- `test_scraper.py` runs the scraper against fake pages shaped like the real ones, with no network.
- `test_live.py` checks that the real site still looks the way the scraper expects, using a fixed sample of skaters.

The tests run locally, not on GitHub.
