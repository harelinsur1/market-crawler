"""Compare the chain list on gov.il with resources/chains.csv and print the differences.

Usage (from the project folder):
    python gov_chains_check/check_gov_chains.py [--headless] [--timeout 90]

The result is also saved as an RTL HTML report in gov_chains_check/report/.
Exit code is 0 when the lists match, 1 when there are differences.
"""
import argparse
import csv
import html
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Set

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://www.gov.il/he/pages/cpfta_prices_regulations"
CHAINS_CSV = Path(__file__).resolve().parent.parent / "resources" / "chains.csv"
REPORT_DIR = Path(__file__).resolve().parent / "report"
# Group rows on gov.il whose links cell lists several sub-chains. Each sub-chain found in that cell
# is compared as "<group> - <sub-chain>" (the same form is used in name_he_gov in chains.csv).
SUB_CHAINS = {'פז קמעונאות ואנרגיה בע"מ': ["יילו", "סופר יודה", "פרשמרקט"]}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>השוואת רשתות מול gov.il - {date}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 2em; direction: rtl; }}
  table {{ border-collapse: collapse; margin-bottom: 1.5em; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 10px; text-align: right; }}
  th {{ background: #f0f0f0; }}
  .added {{ color: #1a7f37; }}
  .removed {{ color: #cf222e; }}
  .ok {{ color: #1a7f37; font-weight: bold; }}
</style>
</head>
<body>
<h1>השוואת רשתות מול gov.il</h1>
<p>תאריך: {date}<br>
מקור: <a href="{url}">{url}</a><br>
נמצאו {gov_count} רשתות ב-gov.il, {csv_count} ב-{csv_name}</p>
{body}
</body>
</html>
"""


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
            entries = [name]
            if name in SUB_CHAINS:
                links = normalize(cells[1].text)
                # Fall back to the group name if no sub-chain is found, so the change shows up in the report.
                entries = ["{} - {}".format(name, s) for s in SUB_CHAINS[name] if s in links] or [name]
            for entry in entries:
                if entry and entry not in names:
                    names.append(entry)
        return names
    finally:
        driver.quit()


def load_csv_chains() -> Set[str]:
    with CHAINS_CSV.open(encoding="utf-8", newline="") as f:
        return {normalize(row["name_he_gov"]) for row in csv.DictReader(f) if row["name_he_gov"].strip()}


def name_list(title: str, names: List[str], css: str) -> str:
    rows = "".join("<tr><td>{}</td><td>{}</td></tr>\n".format(i, html.escape(n))
                   for i, n in enumerate(names, 1))
    return ("<h2 class=\"{}\">{} ({})</h2>\n<table>\n<tr><th>#</th><th>שם</th></tr>\n{}</table>\n"
            .format(css, title, len(names), rows))


def write_report(gov: List[str], known: Set[str], added: List[str], removed: List[str]) -> Path:
    now = datetime.now()
    if added or removed:
        body = ""
        if added:
            body += name_list("קיימות ב-gov.il ולא ב-chains.csv", added, "added")
        if removed:
            body += name_list("קיימות ב-chains.csv ולא ב-gov.il", removed, "removed")
    else:
        body = "<p class=\"ok\">אין הבדלים.</p>\n"
    body += name_list("כל הרשתות ב-gov.il", gov, "")

    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / "gov_chains_{}.html".format(now.strftime("%Y%m%d-%H%M%S"))
    path.write_text(HTML_TEMPLATE.format(
        date=now.strftime("%d/%m/%Y %H:%M"), url=URL, gov_count=len(gov), csv_count=len(known),
        csv_name=CHAINS_CSV.name, body=body), encoding="utf-8")
    return path


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
    print("HTML report saved to {}".format(write_report(gov, known, added, removed)))

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
