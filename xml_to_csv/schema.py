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

COLUMNS = [
    "PriceUpdateDate", "ItemCode", "ItemType", "ItemName",
    "ManufacturerName", "ManufactureCountry", "ManufacturerItemDescription",
    "UnitQty", "Quantity", "bIsWeighted", "UnitOfMeasure", "QtyInPackage",
    "ItemPrice", "UnitOfMeasurePrice", "AllowDiscount", "ItemStatus",
    "filename", "chain", "DateInserted",
]

# target column -> source tags, in priority order (the first non-empty one wins)
ALIASES = {
    "PriceUpdateDate": ["PriceUpdateDate", "PriceUpdateTime"],
    "ItemCode": ["ItemCode"],
    "ItemType": ["ItemType"],
    "ItemName": ["ItemName", "ItemNm"],
    "ManufacturerName": ["ManufacturerName", "ManufactureName"],
    "ManufactureCountry": ["ManufactureCountry"],
    "ManufacturerItemDescription": ["ManufacturerItemDescription", "ManufactureItemDescription"],
    "UnitQty": ["UnitQty"],
    "Quantity": ["Quantity"],
    "bIsWeighted": ["bIsWeighted", "BisWeighted", "blsWeighted"],
    "UnitOfMeasure": ["UnitOfMeasure", "UnitMeasure"],
    "QtyInPackage": ["QtyInPackage"],
    "ItemPrice": ["ItemPrice"],
    "UnitOfMeasurePrice": ["UnitOfMeasurePrice"],
    "AllowDiscount": ["AllowDiscount"],
    "ItemStatus": ["ItemStatus"],
}

# item tags that exist in the files but are not part of the target schema
IGNORED = {"lastsaledatetime", "lastupdatedate", "lastupdatetime", "itemid"}

# column -> max length (SQL column sizes)
MAX_LENGTH = {
    "ManufacturerName": 50,
    "ManufactureCountry": 25,
    "ManufacturerItemDescription": 125,
}

# columns where this value means "missing"
UNKNOWN = "לא ידוע"
UNKNOWN_TO_EMPTY = {"Quantity", "UnitOfMeasurePrice"}

KNOWN_TAGS = {alias.lower() for aliases in ALIASES.values() for alias in aliases} | IGNORED


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
            if column in UNKNOWN_TO_EMPTY and value == UNKNOWN:
                value = ""
            if column in MAX_LENGTH:
                value = value[:MAX_LENGTH[column]]
        row.append(value)
    return row
