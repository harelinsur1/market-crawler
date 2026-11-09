# market-crawler

Downloads the latest `PriceFull` file of every store, published at or before the last 11:00
(today 11:00 if already past it, otherwise yesterday 11:00, local time).
Chain portals are listed on https://www.gov.il/he/pages/cpfta_prices_regulations
(Cloudflare-protected, so the list is maintained by hand in [crawler/chains.py](crawler/chains.py)).

## Setup

Requires Python 3.8+. Run all commands from the project folder:

```powershell
cd c:\Users\johny\Desktop\market-crawler
pip install -r requirements.txt
```

## Usage

```powershell
python -m crawler --list-only      # dry run: print the files that would be downloaded and save them to a CSV
python -m crawler                  # download them
```

Recommended first step: run `--list-only` to see what is found before downloading.
The list is saved to `data\<yyyymmdd-HHMM>\file_list.csv` with the columns
`chain, chain_id, sub_chain, store_id, timestamp, file_name`. Use `--list-file <path>` to save it elsewhere.

### Options

| command | explanation |
|---------|-------------|
| `python -m crawler --list-chains` | print the names of all configured chains |
| `python -m crawler --chains rami carrefour` | only chains whose name contains one of the words (case-insensitive) |
| `python -m crawler --cutoff "2026-11-09 11:00"` | use a specific cutoff instead of the last 11:00 |
| `python -m crawler --cutoff-hour 14` | change the default cutoff hour (last 14:00) |
| `python -m crawler --out D:\prices` | output folder (default `data`) |
| `python -m crawler --workers 4` | number of parallel downloads (default 8) |
| `python -m crawler -v` | verbose logging |
| `python -m crawler --list-only --list-file list.csv` | save the `--list-only` list to a custom path |

Options can be combined, e.g. `python -m crawler --chains "rami levy" --cutoff "2026-11-09 11:00" --list-only`.

### Output

Files are saved to `data\<yyyymmdd-HHMM>\<chain id>\<file name>`, for example
`data\20261109-1100\7290058140886\PriceFull7290058140886-001-001-20261109-001001.gz`.
Existing files are skipped, so it is safe to run again.

The exit code is `0` on success and `1` if any chain or download failed. A failing portal
(e.g. Shufersal timing out) is logged and does not stop the other chains.

## Portals

| platform    | site                              |
|-------------|-----------------------------------|
| Cerberus    | url.retail.publishedprices.co.il  |
| Bina        | kingstore, maayan2000, zolvebegadol, superbareket, shuk-hayir, shefabirkathashem, goodpharm, ktshivuk, paz, citymarketkiryatgat, citymarketgivatayim `.binaprojects.com` |
| Carrefour   | prices.carrefour.co.il            |
| Super-Pharm | prices.super-pharm.co.il          |
| Hazi Hinam  | shop.hazi-hinam.co.il/Prices      |
| Wolt        | wm-gateway.wolt.com/isr-prices    |
| Shufersal   | prices.shufersal.co.il            |