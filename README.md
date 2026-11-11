# market-crawler

Downloads the latest `PriceFull` file of every store, published at or before the last 11:00
(today 11:00 if already past it, otherwise yesterday 11:00, local time).
Chain portals are listed on https://www.gov.il/he/pages/cpfta_prices_regulations
(Cloudflare-protected, so the list is maintained by hand in [resources/chains.csv](resources/chains.csv);
`python scripts/check_gov_chains.py` reports differences from gov.il).

## Setup

Requires Python 3.8+. Run all commands from the project folder:

```powershell
cd c:\Users\johny\Desktop\market-crawler
pip install -r requirements.txt
```

## Usage

```powershell
python -m crawler --list-only      # dry run: list the files that would be downloaded and save them to a CSV
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
| `python -m crawler --list-timeout 120` | max seconds to wait for all chain listings; slower chains are skipped and reported as failed (default 900; Shufersal is slow and needs several minutes) |
| `python -m crawler -v` | verbose logging |
| `python -m crawler --list-only --list-file list.csv` | save the `--list-only` list to a custom path |

Options can be combined, e.g. `python -m crawler --chains "rami levy" --cutoff "2026-11-09 11:00" --list-only`.

### Output

Files are saved to `data\<yyyymmdd-HHMM>\<chain id>_<chain name>\<file name>`, for example
`data\20261109-1100\7290058140886_Rami-Levy\PriceFull7290058140886-001-001-20261109-001001.gz`.
Each file is then extracted into a folder with the same name (without `.gz`), e.g.
`...\7290058140886_Rami-Levy\PriceFull7290058140886-001-001-20261109-001001\PriceFull7290058140886-001-001-20261109-001001.xml`.
Existing files and folders are skipped, so it is safe to run again.

Each chain's listing line shows its English and Hebrew names and its chain id(s), and the
run ends with a summary: total time, chains scanned (ok / failed), PriceFull files listed,
stores selected and files downloaded (failed).

The exit code is `0` on success and `1` if any chain or download failed. A failing portal
(e.g. Shufersal timing out) is logged and does not stop the other chains.

## Convert XML files to CSV per chain (`xml_to_csv`)

Converts every extracted PriceFull XML file of a run into one CSV per chain folder,
`data\<run>\<chain folder>\full_prices_<run>.csv`, with the columns of the final
price table:
`priceupdatedate, itemcode, itemtype, itemname, manufacturername, manufacturecountry,
manufactureritemdescription, unitqty, quantity, bisweighted, unitofmeasure, qtyinpackage,
itemprice, unitofmeasureprice, allowdiscount, itemstatus, filename, chain, DateInserted`.
`DateInserted` is the time of the `xml_to_csv` run, formatted `2018-10-26 05:42:00`.

```powershell
python -m xml_to_csv                        # latest data\<yyyymmdd-HHMM> folder
python -m xml_to_csv 20261110-1100          # a specific run folder
python -m xml_to_csv.inspect_schema         # report the tag names used by each chain
```

| command | explanation |
|---------|-------------|
| `python -m xml_to_csv 20261110-1100` | run folder under `--data` (default: the latest one) |
| `python -m xml_to_csv --data D:\prices` | data root (default `data`) |
| `python -m xml_to_csv --workers 4` | parallel parser processes (default: number of CPUs) |
| `python -m xml_to_csv.inspect_schema --sample 0` | inspect all files instead of 5 per chain |

Chains do not use the same tag names (e.g. `PriceUpdateDate` / `PriceUpdateTime`,
`ManufacturerName` / `ManufactureName`, `bIsWeighted` / `BisWeighted` / `blsWeighted`).
The conversion dictionary is `ALIASES` in [xml_to_csv/schema.py](xml_to_csv/schema.py)
(case-insensitive, first non-empty tag wins). Text is cut to the SQL varchar sizes (`itemname` /
`manufactureritemdescription` 125, `manufacturername` 50, `manufacturecountry`, `unitqty`,
`unitofmeasure`, `qtyinpackage`, `chain` 25), line breaks inside a value become a space (one record =
one line) and
`לא ידוע` in `quantity` / `unitofmeasureprice` becomes empty. `filename` is the downloaded file
name without extension, `chain` is the English chain name from `file_list.csv`. Item tags that are
not mapped are listed at the end of the run so new variants can be added to the dictionary.

## Load the CSVs into SQL Server as SCD type 2 (`csv_to_sql`)

Loads the chain CSVs `data\<run>\<chain folder>\full_prices_<run>.csv` one chain at a time into
`[cpi].[dbo].[foodChainPricesScd]` on `PCH80041449\MSSQLSERVER01`
(Windows authentication, `ODBC Driver 17 for SQL Server`). Only changes are written, so the table
holds the full price history without storing every item of every day.

```powershell
python -m csv_to_sql                        # latest data\<run>\<chain folder>\full_prices_<run>.csv
python -m csv_to_sql 20261110-1100          # a specific run folder (or a CSV path)
```

| command | explanation |
|---------|-------------|
| `python -m csv_to_sql D:\prices.csv` | a single CSV path instead of a run folder |
| `python -m csv_to_sql --data D:\prices` | data root used to find the run folder (default `data`) |
| `python -m csv_to_sql --server localhost\SQLEXPRESS` | SQL Server (default `PCH80041449\MSSQLSERVER01`) |
| `python -m csv_to_sql --database cpi` | database (default `cpi`) |
| `python -m csv_to_sql --schema dbo` | schema (default `dbo`) |
| `python -m csv_to_sql --table myPrices` | SCD table (default `foodChainPricesScd`; staging table is `<table>_upload`, e.g. `foodChainPricesScd_upload`) |
| `python -m csv_to_sql --driver "ODBC Driver 18 for SQL Server"` | ODBC driver (default `ODBC Driver 17 for SQL Server`) |
| `python -m csv_to_sql --method odbc` | stream rows from this machine with `fast_executemany` instead of `BULK INSERT` (default `bulk`; use `odbc` if SQL Server cannot read the file) |
| `python -m csv_to_sql --method odbc --batch-size 50000` | rows per batch for `--method odbc` (default 100000) |
| `python -m csv_to_sql --keep-staging` | keep the `<table>_upload` staging table of the last chain for debugging (default: dropped after every chain) |

With no options the target is `[cpi].[dbo].[foodChainPricesScd]` on `PCH80041449\MSSQLSERVER01`;
the table and its indexes are created on the first run.

How it stays fast and light with millions of rows — for each chain (folders with the same chain id,
e.g. `7290055700007_Carrefour` and `7290055700007_Keshet-Teamim`, are loaded together):
1. `BULK INSERT` (server-side, minimally logged) of the chain's CSV into the staging table `foodChainPricesScd_upload`.
2. The staging table is clustered by `filename`; file names are parsed once per file into
   `chainid, subchainid, storeid` (the business key with `itemcode`).
3. Merge in one transaction per chain id, then drop the staging table before the next chain.
   Every row has a SHA-256 `rowhash` of the tracked columns, compared
   with the current version through a filtered index (`iscurrent = 1`), so unchanged rows are never written.
   - hash differs: the current version is closed (`validto`, `iscurrent = 0`, `isdeleted = 0`) and a new version inserted
   - item no longer published by a store that is in the load: closed with `isdeleted = 1`
   - store missing from the load (failed download): left untouched

`validfrom` is the CSV's `DateInserted` (also stored per version in the `DateInserted date` column).
Changes in `priceupdatedate`, `filename` or `chain` alone do not
create a new version (see `TRACKED` in [csv_to_sql/scd.py](csv_to_sql/scd.py)). Duplicate items per store
keep the row of the latest file; non-numeric item codes are skipped (`itemcode` is `bigint`, as in
`foodChainPrices`). Re-running the same CSV changes nothing, so a failed run can be restarted;
loading a CSV older than the last load is refused.

Current prices: `SELECT * FROM cpi.dbo.foodChainPricesScd WHERE iscurrent = 1`.
Prices on a date: `WHERE validfrom <= @d AND (validto > @d OR validto IS NULL)`.
Removed items: `WHERE isdeleted = 1` (`validto` = when the item disappeared). If the item comes back
later it gets a new version with `iscurrent = 1`.

## Chains

The chains are read from [resources/chains.csv](resources/chains.csv)
(`chain_code, name_en, name_he_gov, name_he_over, platform, key, display_name, branches`).
The English name is used by `--chains` / `--list-chains` and in the `chain` column of the list CSV.
To add a chain, add a row whose `platform` is one of the portals below and whose `key` is the
portal's account / subdomain.

| English                | עברית                | chain code    | platform   | key                 | branches |
|------------------------|----------------------|---------------|------------|---------------------|---------:|
| King Store             | קינג סטור            | 7290058108879 | bina       | kingstore           | 48  |
| Maayan 2000            | מעיין אלפיים         | 7290058159628 | bina       | maayan2000          | 38  |
| Good Pharm             | גוד פארם             | 7290058197699 | bina       | goodpharm           | 83  |
| Carrefour              | קרפור                | 7290055700007 | carrefour  | carrefour           | 203 |
| Dor Alon               | דור אלון             | 7290492000005 | cerberus   | doralon             | 158 |
| Wolt                   | וולט מרקט            | 7290058249350 | wolt       | wolt                | 37  |
| Victory                | ויקטורי              | 7290696200003 | laib       | victory             | 70  |
| Zol VeBegadol          | זול ובגדול           | 7290058173198 | bina       | zolvebegadol        | 70  |
| H. Cohen               | ח. כהן               | 7290455000004 | laib       | hcohen              | 5   |
| Tiv Taam               | טיב טעם              | 7290873255550 | cerberus   | tivtaam             | 54  |
| Mahsanei HaShuk        | מחסני השוק           | 7290661400001 | laib       | mshuk               | 71  |
| Hazi Hinam             | חצי חינם             | 7290700100008 | hazihinam  | hazihinam           | 13  |
| Yohananof              | יוחננוף              | 7290803800003 | cerberus   | yohananof           | 49  |
| Osher Ad               | אושר עד              | 7290103152017 | cerberus   | osherad             | 24  |
| Netiv HaChesed         | נתיב החסד — סופר חסד | 7290058160839 | netivhesed | netivhesed          | 91  |
| Salach Dabach          | סאלח דבאח            | 7290526500006 | cerberus   | salachd             | 6   |
| Super Sapir            | סופר ספיר            | 7290058156016 | bina       | supersapir          | 102 |
| Super-Pharm            | סופר-פארם            | 7290172900007 | superpharm | superpharm          | 307 |
| City Market Kiryat Gat | סיטי מרקט קריית גת   | 7290058266241 | bina       | citymarketkiryatgat | 31  |
| City Market            | סיטי מרקט            | 7290000000003 | citymarket | citymarket          | 31  |
| Stop Market            | סטופ מרקט            | 7290639000004 | cerberus   | stop_market         | 12  |
| Of VeHodu Bareket      | עוף והודו ברקת       | 7290875100001 | bina       | superbareket        | 15  |
| Politzer               | פוליצר               | 7291059100008 | cerberus   | politzer            | 8   |
| Paz Yellow             | פז — יילו            | 7290644700005 | cerberus   | paz_bo              | 244 |
| Super Yuda             | פז — סופר יודה       | 7290058177776 | cerberus   | yuda_ho             | 28  |
| Fresh Market           | פז — פרשמרקט         | 7290876100000 | cerberus   | freshmarket         | 47  |
| KT Mishnat Yosef       | קיי.טי. — משנת יוסף  | 5144744100002 | kt         | kt                  | 1   |
| KT Shivuk              | קיי.טי. יבוא ושיווק  | 7290058289400 | bina       | ktshivuk            | 4   |
| Keshet Teamim          | קשת טעמים            | 7290785400000 | cerberus   | keshet              | 28  |
| Rami Levy              | רמי לוי              | 7290058140886 | cerberus   | ramilevi            | 99  |
| Shufersal              | שופרסל               | 7290027600007 | shufersal  | shufersal           | 430 |
| Shuk HaIr              | שוק העיר             | 7290058148776 | bina       | shuk-hayir          | 26  |
| Shefa Birkat Hashem    | שפע ברכת השם         | 7290058134977 | bina       | shefabirkathashem   | 22  |

Chain codes are as listed on gov.il; the code in the downloaded file names can differ
(e.g. Keshet Teamim also publishes as 7290785400000, City Market Kiryat Gat as 7290058288090).

## Portals

Each portal is one class in [crawler/platforms](crawler/platforms) with its own download handler
(`download()`); chains on the same portal share it.

| platform (CSV) | class       | site                              | download handler |
|----------------|-------------|-----------------------------------|------------------|
| cerberus       | Cerberus    | url.retail.publishedprices.co.il (key = user name) | GET with the logged-in session |
| bina           | Bina        | `<key>.binaprojects.com`          | `Download.aspx` returns the real URL, then GET |
| laib           | Laibcatalog | laibcatalog.co.il (victory, hcohen, mshuk) | direct GET |
| netivhesed     | NetivHesed  | app.netiv-hesed.com               | direct GET |
| carrefour      | Carrefour   | prices.carrefour.co.il            | direct GET |
| superpharm     | SuperPharm  | prices.super-pharm.co.il          | direct GET |
| hazihinam      | HaziHinam   | shop.hazi-hinam.co.il/Prices      | direct GET |
| wolt           | Wolt        | wm-gateway.wolt.com/isr-prices    | direct GET |
| shufersal      | Shufersal   | prices.shufersal.co.il            | direct GET |
| citymarket     | CityMarket  | www.citymarket-shops.co.il        | direct GET |
| kt             | KT          | list-files.w5871031-kt.workers.dev | direct GET |