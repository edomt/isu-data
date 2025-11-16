import os
import requests

from bs4 import BeautifulSoup
import pandas as pd


CATEGORIES = ["pairs", "men", "women", "dance"]  # Pages to parse
ACTIVE_SEASON = "25/26"  # If this string is in the page, then the skater is active

# Determine script dir
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
OUTPUT_FILE = "data.csv"


def get_skater_list(category):
    url = f"http://www.isuresults.com/bios/fsbios{category}.htm"
    page = requests.get(url)
    soup = BeautifulSoup(page.content, "html.parser")
    skater_list = soup.find_all("a", href=True)
    return skater_list


def scrape_flx_format(soup):
    # find all class flx2
    flx2 = soup.find_all(class_="flx2")

    # identify index of first flx2 whose text contains "Coach", else return None
    coach_index = next((i for i, x in enumerate(flx2) if "Coach" in x.text), None)
    # if coach_index is None, coach = None
    if coach_index is None:
        coach = None
    else:
        coach = flx2[coach_index].find_next_sibling("td").text

    # identify index of first flx2 whose text contains "Choreographer", else return None
    choreographer_index = next(
        (i for i, x in enumerate(flx2) if "Choreographer" in x.text), None
    )
    # if choreographer_index is None, choreographer = None
    if choreographer_index is None:
        choreographer = None
    else:
        choreographer = flx2[choreographer_index].find_next_sibling("td").text

    # check if any td has ACTIVE_SEASON in text
    active = any(ACTIVE_SEASON in td.text for td in soup.find_all("td"))

    df = pd.DataFrame(
        {
            "coach": coach,
            "choreographer": choreographer,
            "active": active,
        },
        index=[0],
    )
    return df


def scrape_skater(skater):
    # print(skater.text)
    if "fsbios" in skater["href"]:
        return None
    soup = BeautifulSoup(requests.get(skater["href"]).content, "html.parser")

    # If soup has class flx4, then scrape flx format
    if soup.find(class_="flx4"):
        return scrape_flx_format(soup).assign(skater=skater.text)
    else:
        return None


def clean_dataframe(df):
    # Title-case all fields when string
    df = df.map(lambda x: x.title() if isinstance(x, str) else x)

    # Only keep rows where active is True, then drop active column
    df = df[df["active"]]
    df = df.drop(columns=["active"])

    # Only keep rows with either coach or choreographer
    df = df[~df["coach"].isnull() | ~df["choreographer"].isnull()]

    # Capitalize columns
    df.columns = df.columns.str.capitalize()

    # Sort and reorder
    df = df.sort_values(by=["Category", "Skater"])
    df = df[["Category", "Skater", "Coach", "Choreographer"]]

    return df


def main():
    data = []
    for category in CATEGORIES:
        print(category)
        skaters = get_skater_list(category)
        for skater in skaters:
            skater_info = scrape_skater(skater)
            if skater_info is not None:
                skater_info["category"] = category
            data.append(skater_info)

    df = pd.concat(data).pipe(clean_dataframe)
    df.to_csv(os.path.join(SCRIPT_DIR, OUTPUT_FILE), index=False)


if __name__ == "__main__":
    main()
