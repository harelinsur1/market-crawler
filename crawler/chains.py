"""Registry of chains and the portal each one publishes its price files on.

The official list of chain portals is
https://www.gov.il/he/pages/cpfta_prices_regulations (protected by Cloudflare, so it
is maintained here by hand). To add a chain, add an entry using the matching platform.
"""
from typing import Callable, Dict

from .platforms import (
    Bina,
    Carrefour,
    Cerberus,
    HaziHinam,
    Platform,
    Shufersal,
    SuperPharm,
    Wolt,
)

_CERBERUS_USERS = {
    "Rami Levy": ("RamiLevi", ""),
    "Osher Ad": ("osherad", ""),
    "Yohananof": ("yohananof", ""),
    "Tiv Taam": ("TivTaam", ""),
    "Dor Alon": ("doralon", ""),
    "Keshet Teamim": ("Keshet", ""),
    "Fresh Market": ("freshmarket", ""),
    "Stop Market": ("Stop_Market", ""),
    "Politzer": ("politzer", ""),
    "Salach Dabach": ("SalachD", "12345"),
    "Paz (Yellow)": ("Paz_bo", "paz468"),
    "Super Yuda": ("yuda_ho", "Yud@147"),
    "Super Cofix": ("SuperCofixApp", ""),
    "Super Dosh": ("superdosh", ""),
}

_BINA_SUBDOMAINS = {
    "King Store": "kingstore",
    "Maayan 2000": "maayan2000",
    "Zol VeBegadol": "zolvebegadol",
    "Super Bareket": "superbareket",
    "Shuk HaIr": "shuk-hayir",
    "Shefa Birkat Hashem": "shefabirkathashem",
    "Good Pharm": "goodpharm",
    "KT Shivuk": "ktshivuk",
    "Paz (Bina)": "paz",
    "City Market Kiryat Gat": "citymarketkiryatgat",
    "City Market Givatayim": "citymarketgivatayim",
}


def _build() -> Dict[str, Callable[[], Platform]]:
    chains = {}  # type: Dict[str, Callable[[], Platform]]
    for name, (user, password) in _CERBERUS_USERS.items():
        chains[name] = lambda n=name, u=user, p=password: Cerberus(n, u, p)
    for name, sub in _BINA_SUBDOMAINS.items():
        chains[name] = lambda n=name, s=sub: Bina(n, s)
    chains["Shufersal"] = lambda: Shufersal("Shufersal")
    chains["Carrefour"] = lambda: Carrefour("Carrefour")
    chains["Super-Pharm"] = lambda: SuperPharm("Super-Pharm")
    chains["Hazi Hinam"] = lambda: HaziHinam("Hazi Hinam")
    chains["Wolt"] = lambda: Wolt("Wolt")
    return chains


CHAINS = _build()
