# ISU figure skating coaching data

This repo scrapes coaching and choreography information for active figure skaters from the International Skating Union (ISU) results site and stores it in a single CSV file.

## Files

- `scraper.py` – downloads the ISU bio pages for all four disciplines (`pairs`, `men`, `women`, `dance`), parses the HTML, and extracts:

  - skater name
  - coach
  - choreographer
  - discipline (category)  
    It only keeps skaters whose bio includes the current active season string, then writes a cleaned table to `data.csv`.

- `data.csv` – the generated dataset with the columns:

  - `Category`
  - `Skater`
  - `Coach`
  - `Choreographer`

- `autoupdate.sh` – helper script to:
  1. `git pull`
  2. run `python3 scraper.py`
  3. commit and push changes if `data.csv` was updated (commit message: `ISU: automated update`)
