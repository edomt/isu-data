"""Live check against isuresults.com: does the site still look the way scraper.py reads it?

The offline tests use fake pages, so they can't notice a site redesign. These tests fetch
real pages and check the parts the scraper relies on are still there. The sample is fixed:
the 2026 Olympic champions, whose pages will stay up for good, and skaters born in
2010-2012, most of whom should keep competing for years. The checks are written to keep
passing season after season; if one fails, the site changed, not the calendar.
"""

import re
from datetime import UTC, datetime

import pytest
import scraper

BIO = f"{scraper.BASE_URL}/isufs{{}}.htm"

CHAMPIONS = [
    ("men", "Mikhail SHAIDOROV", "00104418"),
    ("women", "Alysa LIU", "00103196"),
    ("pairs", "Riku MIURA / Ryuichi KIHARA", "00108196"),
    # Not linked from the dance list page, which the ISU stopped updating in July 2024.
    ("dance", "Laurence FOURNIER BEAUDRY / Guillaume CIZERON", "00123484"),
]
YOUNG = [
    ("women", "Sumika KANAZAWA", "00123908"),  # born 2012
    ("women", "Subeen JEONG", "00123986"),  # born 2012
    ("men", "Jaewook CHUNG", "00120395"),  # born 2010
    ("men", "Sena TAKAHASHI", "00120844"),  # born 2010
]
SAMPLE = CHAMPIONS + YOUNG


def results_on(url: str) -> set[str]:
    return scraper.seasons_with_results(scraper.fetch(url))


@pytest.fixture(scope="module")
def links() -> dict[str, list[tuple[str, str]]]:
    return {category: scraper.bio_links(category) for category in scraper.CATEGORIES}


@pytest.fixture(scope="module")
def rule() -> scraper.ActiveRule:
    return scraper.active_rule(datetime.now(UTC).date())


@pytest.mark.parametrize("category", scraper.CATEGORIES)
def test_list_page_links_to_bios(links, category):
    got = links[category]
    bio_urls = [url for _, url in got if re.search(r"/bios/isufs\d+\.htm$", url)]
    assert len(bio_urls) > 0.9 * len(got), f"{category}: most links should be bios, got {got[:5]}"
    assert all(name.strip() for name, _ in got[:20]), f"{category}: links should carry the skater name"


@pytest.mark.parametrize(("category", "name", "bio_id"), [s for s in SAMPLE if s[0] != "dance"], ids=lambda v: str(v))
def test_list_page_links_sample_skater(links, category, name, bio_id):
    assert (name, BIO.format(bio_id)) in links[category], f"{name} missing from the {category} list"


@pytest.mark.parametrize("category", scraper.CATEGORIES)
def test_last_seasons_best_list_is_up(category):
    """Last season's list is complete by now; if it comes back empty, the URL pattern changed."""
    start = scraper.season_start_year(datetime.now(UTC).date()) - 1
    got = scraper.season_best_bios(category, start)
    assert len(got) > 30, f"{category}: only {len(got)} skaters on {scraper._season(start)}'s season's best list"


def test_season_best_lists_include_the_champions(rule):
    """All four won in Milan in February 2026, so they're on the 25/26 lists."""
    if "25/26" in rule.seasons:
        missing = [name for _, name, bio_id in CHAMPIONS if BIO.format(bio_id) not in rule.season_best]
        assert not missing, f"not on the season's best lists: {missing}"
    else:  # from July 2027 the rule no longer looks at 25/26: check the list directly
        bios = set().union(*(scraper.season_best_bios(c, 2025) for c in scraper.CATEGORIES))
        assert all(BIO.format(bio_id) in bios for _, _, bio_id in CHAMPIONS)


@pytest.mark.parametrize(("category", "name", "bio_id"), SAMPLE, ids=[s[1] for s in SAMPLE])
def test_bio_still_parses(category, name, bio_id):
    url = BIO.format(bio_id)
    always_active = scraper.ActiveRule((), frozenset({url}), 9999)  # this test is about the layout only
    row = scraper.scrape_bio(name, url, always_active)
    assert row, f"{name}: scrape_bio found no new-format bio at {url} (name block class 'flx4')"
    assert row["skater"] == name
    assert row["coach"] and row["coach"].strip(), f"{name}: no coach (label class 'flx2', value in the next cell)"
    assert row["choreographer"] and row["choreographer"].strip(), f"{name}: no choreographer"
    assert "Former" not in row["coach"]


@pytest.mark.parametrize(("category", "name", "bio_id"), CHAMPIONS, ids=[s[1] for s in CHAMPIONS])
def test_champion_results_table_and_page(category, name, bio_id):
    """Holds for good: the table always shows their last eight seasons, and the Olympics stay listed."""
    url = BIO.format(bio_id)
    assert results_on(url), f"{name}: no results found in the championship table on {url}"
    year = scraper.latest_event_year(url)
    assert year is not None and year >= 2026, f"{name}: Competition Results page gave {year}, expected 2026 or later"


def test_young_skaters_count_as_active(rule):
    """Juniors do quit, so this only needs half of them: most of them stopping at once would
    mean the rule is broken, not that they retired."""
    urls = {name: BIO.format(bio_id) for _, name, bio_id in YOUNG}
    active = [name for name, url in urls.items() if scraper.is_active(url, scraper.fetch(url), rule)]
    assert len(active) >= len(YOUNG) // 2, f"only {active} count as active under {rule.seasons}"
