"""Target CSV schema and the tag-name conversion dictionary.

The target columns are the ones of the [cpi].[dbo].[foodChainPrices] table
(consumer_price_index/Untitled5.ipynb, try_or_none()).

Chains do not use the same tag names. Observed variants (data/20261110-1100):
    PriceUpdateDate | PriceUpdateTime
    ManufacturerName | ManufactureName
    ManufacturerItemDescription | ManufactureItemDescription
    bIsWeighted | BisWeighted | blsWeighted (lower-case L, Wolt)
    ChainId | ChainID, StoreId | StoreID, SubChainId | SubChainID (header, not exported)
Older files also used ItemNm, UnitMeasure, itemStatus (from the notebook's rename dict).
Matching is case-insensitive.
"""
import re

COLUMNS = [
    "priceupdatedate", "itemcode", "itemtype", "itemname",
    "manufacturername", "manufacturecountry", "manufactureritemdescription",
    "unitqty", "quantity", "bisweighted", "unitofmeasure", "qtyinpackage",
    "itemprice", "unitofmeasureprice", "allowdiscount", "itemstatus",
    "filename", "chain", "DateInserted",
]

# target column -> source tags, in priority order (the first non-empty one wins)
ALIASES = {
    "priceupdatedate": ["PriceUpdateDate", "PriceUpdateTime"],
    "itemcode": ["ItemCode"],
    "itemtype": ["ItemType"],
    "itemname": ["ItemName", "ItemNm"],
    "manufacturername": ["ManufacturerName", "ManufactureName"],
    "manufacturecountry": ["ManufactureCountry"],
    "manufactureritemdescription": ["ManufacturerItemDescription", "ManufactureItemDescription"],
    "unitqty": ["UnitQty"],
    "quantity": ["Quantity"],
    "bisweighted": ["bIsWeighted", "BisWeighted", "blsWeighted"],
    "unitofmeasure": ["UnitOfMeasure", "UnitMeasure"],
    "qtyinpackage": ["QtyInPackage"],
    "itemprice": ["ItemPrice"],
    "unitofmeasureprice": ["UnitOfMeasurePrice"],
    "allowdiscount": ["AllowDiscount"],
    "itemstatus": ["ItemStatus"],
}

# item tags that exist in the files but are not part of the target schema
IGNORED = {"lastsaledatetime", "lastupdatedate", "lastupdatetime", "itemid"}

# column -> max length (SQL varchar sizes). filename (varchar(50)) is not cut here because
# csv_to_sql parses chain / store / timestamp from the full name.
MAX_LENGTH = {
    "itemname": 125,
    "manufacturername": 50,
    "manufacturecountry": 25,
    "manufactureritemdescription": 125,
    "unitqty": 25,
    "unitofmeasure": 25,
    "qtyinpackage": 25,
    "chain": 25,
}

# columns where this value means "missing"
UNKNOWN = "לא ידוע"
UNKNOWN_TO_EMPTY = {"quantity", "unitofmeasureprice"}

KNOWN_TAGS = {alias.lower() for aliases in ALIASES.values() for alias in aliases} | IGNORED

# line breaks inside a value (and the spaces around them) become one space: one record = one line
_LINE_BREAK = re.compile(r"\s*[\r\n]+\s*")


def convert_item(item, filename, chain, date_inserted):
    """Map one parsed <Item> (tag -> text) to a row in COLUMNS order."""
    lower = {key.lower(): value for key, value in item.items()}
    row = []
    for column in COLUMNS:
        if column == "filename":
            value = filename
        elif column == "chain":
            value = chain
        elif column == "DateInserted":
            value = date_inserted
        else:
            value = next((lower[a.lower()] for a in ALIASES[column] if lower.get(a.lower())), "")
            value = _LINE_BREAK.sub(" ", value)
            if column in UNKNOWN_TO_EMPTY and value == UNKNOWN:
                value = ""
        if column in MAX_LENGTH:
            value = value[:MAX_LENGTH[column]]
        row.append(value)
    return row
