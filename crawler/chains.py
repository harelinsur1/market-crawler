"""Registry of chains and the portal each one publishes its price files on.

The chains are read from resources/chains.csv, built from the official list on
https://www.gov.il/he/pages/cpfta_prices_regulations (Cloudflare-protected, so it is
maintained by hand; gov_chains_check/check_gov_chains.py reports differences) and the platform keys
on https://www.over.org.il/projects/prices?tab=chains.
To add a chain, add a row whose `platform` is one of _PLATFORMS and whose `key` is the
portal's account / subdomain.
"""
import csv
import functools
import os
from typing import Callable, Dict, Tuple

from .platforms import (
    KT,
    Bina,
    Carrefour,
    Cerberus,
    CityMarket,
    HaziHinam,
    Laibcatalog,
    NetivHesed,
    Platform,
    Shufersal,
    SuperPharm,
    Wolt,
)

CHAINS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "resources", "chains.csv")

# Cerberus accounts that need a password; the others log in with an empty one.
_CERBERUS_PASSWORDS = {
    "salachd": "12345",
    "paz_bo": "paz468",
    "yuda_ho": "Yud@147",
}

# platform column -> factory taking the CSV row
_PLATFORMS = {
    # <key>.binaprojects.com. citymarketkiryatgat publishes both City Market Kiryat Gat
    # chain ids (7290058266241 and 7290058288090).
    "bina": lambda row: Bina(row["name_en"], row["key"]),
    "carrefour": lambda row: Carrefour(row["name_en"]),
    # url.retail.publishedprices.co.il; the key is the (case-insensitive) user name.
    "cerberus": lambda row: Cerberus(row["name_en"], row["key"],
                                     _CERBERUS_PASSWORDS.get(row["key"], "")),
    "citymarket": lambda row: CityMarket(row["name_en"]),
    "hazihinam": lambda row: HaziHinam(row["name_en"]),
    "kt": lambda row: KT(row["name_en"]),
    # laibcatalog.co.il/<victory|hcohen|mshuk>/index.html; the API is keyed by chain id.
    "laib": lambda row: Laibcatalog(row["name_en"], row["chain_code"]),
    "netivhesed": lambda row: NetivHesed(row["name_en"]),
    "shufersal": lambda row: Shufersal(row["name_en"]),
    "superpharm": lambda row: SuperPharm(row["name_en"]),
    "wolt": lambda row: Wolt(row["name_en"]),
}  # type: Dict[str, Callable[[Dict[str, str]], Platform]]


def _load(path: str) -> Tuple[Dict[str, Callable[[], Platform]], Dict[str, str]]:
    chains = {}  # type: Dict[str, Callable[[], Platform]]
    hebrew = {}  # type: Dict[str, str]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            name = row["name_en"]
            factory = _PLATFORMS.get(row["platform"])
            if factory is None:
                raise ValueError("%s: unknown platform %r for %s" % (path, row["platform"], name))
            if name in chains:
                raise ValueError("%s: duplicate chain name %r" % (path, name))
            chains[name] = functools.partial(factory, row)
            hebrew[name] = row["display_name"] or row["name_he_over"]
    return chains, hebrew


CHAINS, HEBREW_NAMES = _load(CHAINS_CSV)
