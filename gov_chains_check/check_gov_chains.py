"""Compare the chain list on gov.il with resources/chains.csv and print the differences.

Usage (from the project folder):
    python gov_chains_check/check_gov_chains.py [--headless] [--timeout 90]

Exit code is 0 when the lists match, 1 when there are differences.
"""
import argparse
import csv
import re
import sys
from pathlib import Path
from typing import List, Set

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://www.gov.il/he/pages/cpfta_prices_regulations"
CHAINS_CSV = Path(__file__).resolve().parent.parent / "resources" / "chains.csv"


def normalize(text: str) -> str:
    text = text.replace("\u05f4", '"').replace("\u05f3", "'").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def table_rows(driver: webdriver.Chrome) -> list:
    """Rows of the retailers table: a name cell followed by a cell with price links."""
    rows = []
    for row in driver.find_elements(By.CSS_SELECTOR, "table tr"):
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 2 and cells[1].find_elements(By.TAG_NAME, "a"):
            rows.append(cells)
    return rows


def fetch_gov_chains(headless: bool, timeout: int) -> List[str]:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--lang=he-IL")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(URL)
        try:
            # Also gives time for the Cloudflare check to pass.
            WebDriverWait(driver, timeout).until(lambda d: table_rows(d))
        except TimeoutException:
            sys.exit("Timed out waiting for the chains table on {} "
                     "(Cloudflare may have blocked the browser; try without --headless).".format(URL))
        names = []  # type: List[str]
        for cells in table_rows(driver):
            name = normalize(cells[0].text)
            if name and name not in names:
                names.append(name)
        return names
    finally:
        driver.quit()


def load_csv_chains() -> Set[str]:
    with CHAINS_CSV.open(encoding="utf-8", newline="") as f:
        return {normalize(row["name_he_gov"]) for row in csv.DictReader(f) if row["name_he_gov"].strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true", help="run Chrome without a window")
    parser.add_argument("--timeout", type=int, default=90, help="seconds to wait for the page (default 90)")
    args = parser.parse_args()

    gov = fetch_gov_chains(args.headless, args.timeout)
    known = load_csv_chains()
    print("Found {} chains on gov.il, {} in {}".format(len(gov), len(known), CHAINS_CSV.name))

    added = [n for n in gov if n not in known]
    removed = sorted(known - set(gov))

    if not added and not removed:
        print("No differences.")
        return 0
    if added:
        print("\nOn gov.il but not in chains.csv ({}):".format(len(added)))
        for name in added:
            print("  + " + name)
    if removed:
        print("\nIn chains.csv but not on gov.il ({}):".format(len(removed)))
        for name in removed:
            print("  - " + name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
