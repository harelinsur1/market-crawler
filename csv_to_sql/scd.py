"""SQL Server side of the SCD type 2 load: table definitions and the per-chain merge.

Business key : chainid, subchainid, storeid (parsed from filename), itemcode.
Tracked      : TRACKED columns below (hashed into rowhash); a different hash closes the
               current version and opens a new one. priceupdatedate / filename / chain /
               DateInserted are stored with each version but do not create a new version by themselves.
Removed items: items that disappear from a store that IS in the load are closed with
               isdeleted = 1 (changed items are closed with isdeleted = 0). Stores that
               are missing from the load (failed download) are left untouched.
"""
import csv
import re

from crawler.filename import parse_filename
from xml_to_csv.schema import COLUMNS

# target column -> (sql type, CSV column); text is cut to the varchar length
TYPED = [
    ("priceupdatedate", "datetime2(0)", "priceupdatedate"),
    ("itemtype", "smallint", "itemtype"),
    ("itemname", "varchar(125)", "itemname"),
    ("manufacturername", "varchar(50)", "manufacturername"),
    ("manufacturecountry", "varchar(25)", "manufacturecountry"),
    ("manufactureritemdescription", "varchar(125)", "manufactureritemdescription"),
    ("unitqty", "varchar(25)", "unitqty"),
    ("quantity", "float", "quantity"),
    ("bisweighted", "smallint", "bisweighted"),
    ("unitofmeasure", "varchar(25)", "unitofmeasure"),
    ("qtyinpackage", "varchar(25)", "qtyinpackage"),
    ("itemprice", "float", "itemprice"),
    ("unitofmeasureprice", "float", "unitofmeasureprice"),
    ("allowdiscount", "smallint", "allowdiscount"),
    ("itemstatus", "smallint", "itemstatus"),
    ("filename", "varchar(50)", "filename"),
    ("chain", "varchar(25)", "chain"),
    ("DateInserted", "date", "DateInserted"),
]

TRACKED = [
    "itemtype", "itemname", "manufacturername", "manufacturecountry",
    "manufactureritemdescription", "unitqty", "quantity", "bisweighted", "unitofmeasure",
    "qtyinpackage", "itemprice", "unitofmeasureprice", "allowdiscount", "itemstatus",
]

KEY = ["chainid", "subchainid", "storeid", "itemcode"]

_IDENTIFIER = re.compile(r"^\w+$")


def quote_name(*parts):
    """[db].[schema].[table]; only plain identifiers are accepted."""
    for part in parts:
        if not _IDENTIFIER.match(part):
            raise SystemExit("invalid SQL identifier: %r" % part)
    return ".".join("[%s]" % part for part in parts)


def check_header(header, csv_path):
    """Case-insensitive, so CSVs written with the older PascalCase header still load."""
    if [h.lower() for h in header or []] != [c.lower() for c in COLUMNS]:
        raise SystemExit("unexpected CSV header in %s" % csv_path)


def _expr(sql_type, column):
    if sql_type.startswith("varchar"):
        return "LEFT(s.[%s], %s)" % (column, sql_type[8:-1])
    return "TRY_CONVERT(%s, s.[%s])" % (sql_type, column)


def create_target(cursor, target, table):
    columns = ",\n    ".join("%s %s NULL" % (name, sql_type) for name, sql_type, _ in TYPED)
    cursor.execute("""
IF OBJECT_ID(N'%(target)s', N'U') IS NULL
BEGIN
CREATE TABLE %(target)s (
    chainid varchar(13) NOT NULL,
    subchainid varchar(10) NOT NULL,
    storeid varchar(10) NOT NULL,
    itemcode bigint NOT NULL,
    %(columns)s,
    rowhash binary(32) NOT NULL,
    validfrom datetime2(0) NOT NULL,
    validto datetime2(0) NULL,
    iscurrent bit NOT NULL,
    isdeleted bit NOT NULL CONSTRAINT [DF_%(table)s_isdeleted] DEFAULT 0,
    CONSTRAINT [PK_%(table)s] PRIMARY KEY CLUSTERED (chainid, subchainid, storeid, itemcode, validfrom)
);
CREATE UNIQUE NONCLUSTERED INDEX [UX_%(table)s_current] ON %(target)s
    (chainid, subchainid, storeid, itemcode) INCLUDE (rowhash) WHERE iscurrent = 1;
END
IF COL_LENGTH(N'%(target)s', 'isdeleted') IS NULL
    ALTER TABLE %(target)s ADD isdeleted bit NOT NULL
        CONSTRAINT [DF_%(table)s_isdeleted] DEFAULT 0;
IF COL_LENGTH(N'%(target)s', 'DateInserted') IS NULL
    ALTER TABLE %(target)s ADD DateInserted date NULL;""" % {"target": target, "table": table, "columns": columns})


def create_staging(cursor, staging):
    columns = ", ".join("[%s] nvarchar(%d) NULL" % (name, 200 if name == "filename" else 1000)
                        for name in COLUMNS)
    cursor.execute("IF OBJECT_ID(N'%s', N'U') IS NOT NULL DROP TABLE %s" % (staging, staging))
    cursor.execute("CREATE TABLE %s (%s)" % (staging, columns))


def index_staging(cursor, staging):
    """Cluster the loaded rows by filename so every chain is read with a range seek."""
    cursor.execute("CREATE CLUSTERED INDEX ix_filename ON %s (filename)" % staging)


def bulk_insert(cursor, staging, csv_path):
    """Server-side load: SQL Server reads the file itself (fastest, the file must be readable
    by the SQL Server service account)."""
    cursor.execute("""
BULK INSERT %s FROM '%s'
WITH (FORMAT = 'CSV', CODEPAGE = '65001', FIRSTROW = 2, TABLOCK)""" % (staging, csv_path.replace("'", "''")))


def odbc_insert(cursor, staging, csv_path, batch_size, progress):
    """Client-side load with fast_executemany, streamed in batches (no pandas, constant memory)."""
    sql = "INSERT INTO %s VALUES (%s)" % (staging, ", ".join("?" * len(COLUMNS)))
    cursor.fast_executemany = True
    total = 0
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        check_header(next(reader, None), csv_path)
        batch = []
        for row in reader:
            batch.append([value or None for value in row])
            if len(batch) >= batch_size:
                cursor.executemany(sql, batch)
                total += len(batch)
                batch = []
                progress(total)
        if batch:
            cursor.executemany(sql, batch)
            total += len(batch)
    return total


def load_files(cursor, staging):
    """#files: filename -> chainid/subchainid/storeid/timestamp (parsed in Python once per file).
    Returns the file names that could not be parsed."""
    names = [row[0] for row in cursor.execute("SELECT DISTINCT filename FROM %s" % staging)]
    rows, bad = [], []
    for name in names:
        info = parse_filename(name or "")
        if info is None:
            bad.append(name)
        else:
            rows.append((name, info.chain_id, info.sub_chain, info.store_id, info.timestamp))
    cursor.execute("""
CREATE TABLE #files (
    filename nvarchar(200) NOT NULL PRIMARY KEY, chainid varchar(13) NOT NULL,
    subchainid varchar(10) NOT NULL, storeid varchar(10) NOT NULL, filets datetime2(0) NOT NULL)""")
    if rows:
        cursor.fast_executemany = True
        cursor.executemany("INSERT INTO #files VALUES (?, ?, ?, ?, ?)", rows)
    return bad


def merge_chain(cursor, target, staging, chain_id, valid_from):
    """SCD2 merge of one chain. Returns (source rows, changed, removed, inserted)."""
    hash_input = ", NCHAR(31), ".join("ISNULL(s.[%s], N'')" % c for c in TRACKED)
    typed = ",\n        ".join("%s AS %s" % (_expr(t, c), n) for n, t, c in TYPED)
    columns = ", ".join(KEY + [n for n, _, _ in TYPED] + ["rowhash"])
    if not chain_id.isdigit():  # inlined: a parameterized SELECT INTO #src would drop #src on return
        raise ValueError("bad chain id %r" % chain_id)
    cursor.execute("""
SELECT %(columns)s INTO #src FROM (
    SELECT f.chainid, f.subchainid, f.storeid, k.itemcode,
        %(typed)s,
        k.rowhash,
        ROW_NUMBER() OVER (PARTITION BY f.subchainid, f.storeid, k.itemcode
                           ORDER BY f.filets DESC, k.rowhash) AS rn
    FROM %(staging)s s
    JOIN #files f ON f.filename = s.filename
    CROSS APPLY (SELECT TRY_CONVERT(bigint, s.itemcode) AS itemcode,
                        CAST(HASHBYTES('SHA2_256', CONCAT(%(hash_input)s)) AS binary(32)) AS rowhash) k
    WHERE f.chainid = '%(chain_id)s' AND k.itemcode IS NOT NULL
) x WHERE rn = 1""" % {"columns": columns, "typed": typed, "staging": staging,
                       "hash_input": hash_input, "chain_id": chain_id})
    source = cursor.rowcount
    cursor.execute("CREATE UNIQUE CLUSTERED INDEX ix ON #src (subchainid, storeid, itemcode)")

    join = " AND ".join("t.%s = s.%s" % (c, c) for c in KEY)
    cursor.execute("""
UPDATE t SET validto = ?, iscurrent = 0
FROM %s t JOIN #src s ON %s
WHERE t.iscurrent = 1 AND t.rowhash <> s.rowhash""" % (target, join), valid_from)
    changed = cursor.rowcount

    cursor.execute("""
UPDATE t SET validto = ?, iscurrent = 0, isdeleted = 1
FROM %s t
WHERE t.iscurrent = 1 AND t.chainid = ?
  AND EXISTS (SELECT 1 FROM #src s WHERE s.subchainid = t.subchainid AND s.storeid = t.storeid)
  AND NOT EXISTS (SELECT 1 FROM #src s WHERE %s)""" % (target, join), valid_from, chain_id)
    removed = cursor.rowcount

    cursor.execute("""
INSERT INTO %s (%s, validfrom, validto, iscurrent)
SELECT %s, ?, NULL, 1 FROM #src s
WHERE NOT EXISTS (SELECT 1 FROM %s t WHERE t.iscurrent = 1 AND %s)""" % (
        target, columns, ", ".join("s." + c for c in columns.split(", ")), target, join), valid_from)
    inserted = cursor.rowcount

    cursor.execute("DROP TABLE #src")
    return source, changed, removed, inserted
