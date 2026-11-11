"""Generate a Swagger (OpenAPI 3) file and a Postman collection for every domain the crawler calls.

    python -m api_docs

Writes api_docs/<domain>/openapi.json and api_docs/<domain>/postman_collection.json.
Chains come from resources/chains.csv, so re-run after editing it. Domains shared by several
chains (binaprojects.com, publishedprices.co.il, laibcatalog.co.il) get one Postman folder per
chain; in Swagger the chain is picked from the server list / request examples.

Postman: every folder is a chain of requests (list -> download) that pass the file name/url
through collection variables, so "Run folder" works. Leave the `date` variable empty to use
today, or set it as YYYY-MM-DD.
"""
import csv
import json
import os
from typing import Dict, List

from crawler.chains import _CERBERUS_PASSWORDS, CHAINS_CSV

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
POSTMAN_SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
EXAMPLE_DATE = "2026-11-11"


# --------------------------------------------------------------------------- chains

def _load_chains() -> Dict[str, List[Dict[str, str]]]:
    by_platform = {}  # type: Dict[str, List[Dict[str, str]]]
    with open(CHAINS_CSV, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            by_platform.setdefault(row["platform"], []).append(row)
    return by_platform


def _chain_title(row: Dict[str, str]) -> str:
    return "%s (%s)" % (row["name_en"], row["chain_code"])


def _chain_label(row: Dict[str, str]) -> str:
    return "%s - %s" % (_chain_title(row), row["display_name"] or row["name_he_over"])


# --------------------------------------------------------------------------- OpenAPI helpers

def _openapi(title: str, description: str, servers: List[Dict], paths: Dict,
             schemas: Dict = None, security_schemes: Dict = None) -> Dict:
    doc = {
        "openapi": "3.0.3",
        "info": {"title": title, "version": "1.0.0", "description": description},
        "servers": servers,
        "paths": paths,
    }
    components = {}
    if schemas:
        components["schemas"] = schemas
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    return doc


def _server(url: str, description: str = "") -> Dict:
    return {"url": url, "description": description} if description else {"url": url}


def _param(name: str, where: str, description: str, example=None, required: bool = True,
           schema: Dict = None, examples: Dict = None) -> Dict:
    param = {"name": name, "in": where, "required": required or where == "path",
             "description": description, "schema": schema or {"type": "string"}}
    if example is not None:
        param["example"] = example
    if examples:
        param["examples"] = examples
    return param


def _form(properties: Dict, examples: Dict = None) -> Dict:
    media = {"schema": {"type": "object", "properties": properties,
                        "required": list(properties)}}
    if examples:
        media["examples"] = examples
    return {"required": True, "content": {"application/x-www-form-urlencoded": media}}


def _html(description: str) -> Dict:
    return {"200": {"description": description,
                    "content": {"text/html": {"schema": {"type": "string"}}}}}


def _json(description: str, schema: Dict) -> Dict:
    return {"200": {"description": description,
                    "content": {"application/json": {"schema": schema}}}}


def _binary(description: str = "The price file (gzip-compressed XML).") -> Dict:
    return {"200": {"description": description,
                    "content": {"application/octet-stream": {
                        "schema": {"type": "string", "format": "binary"}}}}}


def _ref(name: str) -> Dict:
    return {"$ref": "#/components/schemas/" + name}


def _array_of(name: str) -> Dict:
    return {"type": "array", "items": _ref(name)}


def _obj(**properties) -> Dict:
    return {"type": "object", "properties": properties}


def _s(example=None, **extra) -> Dict:
    schema = {"type": "string"}
    if example is not None:
        schema["example"] = example
    schema.update(extra)
    return schema


def _date_param(name: str, fmt: str = "YYYY-MM-DD", example: str = EXAMPLE_DATE) -> Dict:
    return _param(name, "query", "Publication day (%s)." % fmt, example)


def _file_name_param(example: str) -> Dict:
    return _param("fileName", "path", "File name as returned by the listing.", example)


# --------------------------------------------------------------------------- Postman helpers

# Sets {{date}} (YYYY-MM-DD), {{dateCompact}} (YYYYMMDD) and {{dateDmy}} (DD/MM/YYYY).
_DATE_SCRIPT = [
    "// {{date}} = collection variable (YYYY-MM-DD) or today when empty.",
    "const pad = n => String(n).padStart(2, '0');",
    "const now = new Date();",
    "const iso = pm.collectionVariables.get('date')"
    " || `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;",
    "const [y, m, d] = iso.split('-');",
    "pm.variables.set('date', iso);",
    "pm.variables.set('dateCompact', y + m + d);",
    "pm.variables.set('dateDmy', `${d}/${m}/${y}`);",
]


def _script(listen: str, lines: List[str]) -> Dict:
    return {"listen": listen, "script": {"type": "text/javascript", "exec": lines}}


def _request(name: str, method: str, url: str, description: str = "", form: List = None,
             tests: List[str] = None) -> Dict:
    request = {"method": method, "header": [], "url": url}
    if description:
        request["description"] = description
    if form is not None:
        request["body"] = {"mode": "urlencoded", "urlencoded": [
            {"key": key, "value": value, "type": "text"} for key, value in form]}
    item = {"name": name, "request": request,
            # Several portals serve broken certificate chains.
            "protocolProfileBehavior": {"strictSSL": False}}
    if tests:
        item["event"] = [_script("test", tests)]
    return item


def _folder(name: str, items: List[Dict], description: str = "") -> Dict:
    folder = {"name": name, "item": items}
    if description:
        folder["description"] = description
    return folder


def _collection(name: str, description: str, items: List[Dict], variables: List[str]) -> Dict:
    return {
        "info": {"name": name, "description": description, "schema": POSTMAN_SCHEMA},
        "event": [_script("prerequest", _DATE_SCRIPT)],
        "variable": [{"key": "date", "value": "",
                      "description": "YYYY-MM-DD; empty = today"}]
                    + [{"key": key, "value": ""} for key in variables],
        "item": items,
    }


def _save_first_match(regex: str, assignments: List, what: str = "a PriceFull file") -> List[str]:
    """Test script: run a JS regex on the HTML response and store groups in variables."""
    return [
        "const m = pm.response.text().match(%s);" % regex,
        "pm.test('found %s', () => pm.expect(m).to.not.equal(null));" % what,
        "if (m) {",
    ] + ["    pm.collectionVariables.set('%s', %s);" % (key, value) for key, value in assignments] + [
        "}",
    ]


def _save_first_json(items_expr: str, predicate: str, assignments: List) -> List[str]:
    """Test script: find the first PriceFull item in a JSON response and store its fields."""
    return [
        "const item = (%s).find(%s);" % (items_expr, predicate),
        "pm.test('found a PriceFull file', () => pm.expect(item).to.not.equal(undefined));",
        "if (item) {",
    ] + ["    pm.collectionVariables.set('%s', %s);" % (key, value) for key, value in assignments] + [
        "}",
    ]


_DOWNLOAD_NOTE = "Use \"Send and Download\" to save the file."


def _download(url: str) -> Dict:
    return _request("Download file", "GET", url, _DOWNLOAD_NOTE)


# --------------------------------------------------------------------------- domains

def bina(chains: List[Dict[str, str]]):
    description = (
        "Bina Projects portals: every chain has its own subdomain `<key>.binaprojects.com` "
        "with the same API. Pick the chain in the server list.\n\n"
        "Flow: `POST /MainIO_Hok.aspx` (list a day's files) -> `GET /Download.aspx?FileNm=` "
        "(returns the real file url `SPath`) -> `GET /Download/{fileName}`.\n\n"
        "`citymarketkiryatgat` publishes both City Market Kiryat Gat chain ids "
        "(7290058266241 and 7290058288090)."
    )
    sample = "PriceFull7290058108879-000-001-20261111-051139.GZ"
    servers = [_server("https://%s.binaprojects.com" % row["key"], _chain_label(row))
               for row in chains]
    paths = {
        "/MainIO_Hok.aspx": {"post": {
            "summary": "List the files published on a day",
            "requestBody": _form({
                "WStore": _s("", description="Store number; empty = all stores."),
                "WDate": _s(EXAMPLE_DATE, format="date", description="Day (YYYY-MM-DD)."),
                "WFileType": _s("4", description="File type; 4 = PriceFull (used by the crawler)."),
            }),
            "responses": _json("Files of the day (all types; the crawler keeps `FileNm` "
                               "starting with `PriceFull`).", _array_of("BinaFile")),
        }},
        "/Download.aspx": {"get": {
            "summary": "Resolve the download url of a file",
            "parameters": [_param("FileNm", "query", "File name from the listing.", sample)],
            "responses": _json("One item with the real file url.", {
                "type": "array", "items": _obj(SPath=_s(
                    "https://kingstore.binaprojects.com/Download/" + sample, format="uri"))}),
        }},
        "/Download/{fileName}": {"get": {
            "summary": "Download a file (the `SPath` url)",
            "parameters": [_file_name_param(sample)],
            "responses": _binary(),
        }},
    }
    schemas = {"BinaFile": _obj(
        FileNm=_s(sample), Company=_s("1"), Store=_s("1 Um al-Fahm"),
        TypeFile=_s(description="File type label (Hebrew)."), TypeExpFile=_s("gz"),
        DateFile=_s("05:12 11/11/2026", description="HH:MM DD/MM/YYYY"),
        PathLogo=_s(), Reshet=_s(),
    )}
    folders = []
    for row in chains:
        base = "https://%s.binaprojects.com" % row["key"]
        folders.append(_folder(_chain_title(row), [
            _request("List PriceFull files", "POST", base + "/MainIO_Hok.aspx",
                     form=[("WStore", ""), ("WDate", "{{date}}"), ("WFileType", "4")],
                     tests=_save_first_json("pm.response.json()",
                                            "f => (f.FileNm || '').startsWith('PriceFull')",
                                            [("fileName", "item.FileNm")])),
            _request("Resolve download url", "GET", base + "/Download.aspx?FileNm={{fileName}}",
                     tests=["const url = pm.response.json()[0].SPath;",
                            "pm.test('got SPath', () => pm.expect(url).to.be.a('string'));",
                            "pm.collectionVariables.set('fileUrl', url);"]),
            _download("{{fileUrl}}"),
        ], _chain_label(row)))
    return ("binaprojects.com",
            _openapi("Bina Projects price portals", description, servers, paths, schemas),
            _collection("binaprojects.com", description, folders, ["fileName", "fileUrl"]))


def cerberus(chains: List[Dict[str, str]]):
    base = "https://url.retail.publishedprices.co.il"
    table = "\n".join("| %s | %s | `%s` | `%s` |" % (
        row["name_en"], row["chain_code"], row["key"], _CERBERUS_PASSWORDS.get(row["key"], ""))
        for row in chains)
    description = (
        "Cerberus web client shared by many chains; each chain is a user account.\n\n"
        "Flow: `GET /login` (session cookie `cftpSID` + `csrftoken` meta tag) -> "
        "`POST /login/user` (redirects to `/file`, whose page has a new `csrftoken`) -> "
        "`POST /file/json/dir` (list files) -> `GET /file/d/{fileName}`.\n"
        "Some accounts (e.g. Super Yuda) keep their files in a subfolder.\n\n"
        "| chain | chain id | username | password |\n|---|---|---|---|\n" + table
    )
    sample = "PriceFull7290058140886-001-001-20261111-001011.gz"
    login_examples = {
        row["key"]: {"summary": _chain_title(row), "value": {
            "username": row["key"], "password": _CERBERUS_PASSWORDS.get(row["key"], ""),
            "csrftoken": "<csrftoken from GET /login>", "Submit": "Sign in"}}
        for row in chains
    }
    cookie = [{"cftpSID": []}]
    paths = {
        "/login": {"get": {
            "summary": "Login page",
            "description": "Sets the `cftpSID` cookie; the page has "
                           "`<meta name=\"csrftoken\" content=\"...\">`.",
            "responses": _html("Login page."),
        }},
        "/login/user": {"post": {
            "summary": "Log in as a chain",
            "requestBody": _form({
                "username": _s("ramilevi"), "password": _s(""),
                "csrftoken": _s(description="Token from the login page."),
                "Submit": _s("Sign in"),
            }, login_examples),
            "responses": {
                "302": {"description": "Success: redirect to `/file`."},
                "200": {"description": "Failure: the login page is shown again.",
                        "content": {"text/html": {"schema": {"type": "string"}}}},
            },
        }},
        "/file": {"get": {
            "summary": "File manager page",
            "description": "Contains the `csrftoken` to use with `/file/json/dir`.",
            "security": cookie,
            "responses": _html("File manager page."),
        }},
        "/file/json/dir": {"post": {
            "summary": "List a folder",
            "security": cookie,
            "requestBody": _form({
                "sEcho": _s("1"), "iDisplayStart": _s("0"), "iDisplayLength": _s("100000"),
                "sSearch": _s("PriceFull", description="Name filter; empty = everything."),
                "mDataProp_1": _s("fname"),
                "cd": _s("/", description="Folder: `/` or `/<subfolder>`."),
                "csrftoken": _s(description="Token from the `/file` page."),
            }),
            "responses": _json("DataTables response.", _ref("DirResponse")),
        }},
        "/file/d/{fileName}": {"get": {
            "summary": "Download a file from the root folder",
            "security": cookie,
            "parameters": [_file_name_param(sample)],
            "responses": _binary(),
        }},
        "/file/d/{folder}/{fileName}": {"get": {
            "summary": "Download a file from a subfolder",
            "security": cookie,
            "parameters": [_param("folder", "path", "Subfolder name."), _file_name_param(sample)],
            "responses": _binary(),
        }},
    }
    schemas = {
        "DirResponse": _obj(aaData={"type": "array", "items": _ref("DirRow")}),
        "DirRow": _obj(
            DT_RowId=_s(sample), fname=_s(sample), name=_s(sample), value=_s(sample),
            type=_s("file", enum=["file", "folder"]), typeLabel=_s("file"),
            ftime=_s("11/11/2026 00:20"), time=_s("2026-11-10T22:20:52Z", format="date-time"),
            size={"type": "integer", "example": 1002771}, icon=_s("compress.png"),
        ),
    }
    security_schemes = {"cftpSID": {"type": "apiKey", "in": "cookie", "name": "cftpSID"}}
    csrf = _save_first_match(r"""/name="csrftoken" content="([^"]+)"/""",
                             [("csrftoken", "m[1]")], "the csrftoken")
    dir_form = [("sEcho", "1"), ("iDisplayStart", "0"), ("iDisplayLength", "100000"),
                ("mDataProp_1", "fname"), ("csrftoken", "{{csrftoken}}")]
    folders = []
    for row in chains:
        password = _CERBERUS_PASSWORDS.get(row["key"], "")
        folders.append(_folder(_chain_title(row), [
            _request("Login page", "GET", base + "/login", tests=csrf),
            _request("Login", "POST", base + "/login/user",
                     form=[("username", row["key"]), ("password", password),
                           ("csrftoken", "{{csrftoken}}"), ("Submit", "Sign in")],
                     tests=["pm.test('logged in', () => pm.expect(pm.response.text())"
                            ".to.not.include('name=\"username\"'));"] + csrf),
            _request("List root folder", "POST", base + "/file/json/dir",
                     "Picks the root, or the first subfolder when the root has no PriceFull files.",
                     form=dir_form + [("sSearch", ""), ("cd", "/")],
                     tests=["const rows = pm.response.json().aaData || [];",
                            "const inRoot = rows.some(r => r.type === 'file'"
                            " && (r.fname || '').startsWith('PriceFull'));",
                            "const sub = rows.find(r => r.type === 'folder');",
                            "pm.collectionVariables.set('folder',"
                            " !inRoot && sub ? sub.fname : '');"]),
            _request("List PriceFull files", "POST", base + "/file/json/dir",
                     form=dir_form + [("sSearch", "PriceFull"), ("cd", "/{{folder}}")],
                     tests=_save_first_json(
                         "pm.response.json().aaData || []",
                         "r => r.type === 'file' && (r.fname || '').startsWith('PriceFull')",
                         [("filePath", "(pm.collectionVariables.get('folder')"
                                       " ? pm.collectionVariables.get('folder') + '/' : '')"
                                       " + item.fname")])),
            _download(base + "/file/d/{{filePath}}"),
        ], _chain_label(row)))
    return ("url.retail.publishedprices.co.il",
            _openapi("Cerberus (publishedprices.co.il) price portal", description,
                     [_server(base)], paths, schemas, security_schemes),
            _collection("url.retail.publishedprices.co.il", description, folders,
                        ["csrftoken", "folder", "filePath"]))


def laibcatalog(chains: List[Dict[str, str]]):
    base = "https://laibcatalog.co.il/webapi"
    description = (
        "laibcatalog.co.il portals (`laibcatalog.co.il/<chain>/index.html`). The API is keyed "
        "by chain id and ignores dates (returns the chain's whole current catalog).\n\n"
        "Chains: " + ", ".join(_chain_label(row) for row in chains)
    )
    codes = [row["chain_code"] for row in chains]
    examples = {row["key"]: {"summary": _chain_title(row), "value": row["chain_code"]}
                for row in chains}
    sample = "PriceFull7290696200003-001-001-20261111-051146.gz"
    paths = {
        "/api/getfiles": {"get": {
            "summary": "List a chain's files",
            "parameters": [_param("edi", "query", "Chain id.", schema=_s(enum=codes),
                                  examples=examples)],
            "responses": _json("All current files (Price, PriceFull, Promo, Stores...).",
                               _array_of("LaibFile")),
        }},
        "/{chainId}/{fileName}": {"get": {
            "summary": "Download a file",
            "parameters": [_param("chainId", "path", "Chain id.", schema=_s(enum=codes),
                                  examples=examples),
                           _file_name_param(sample)],
            "responses": _binary(),
        }},
    }
    schemas = {"LaibFile": _obj(
        branchNumber={"type": "integer", "example": 1}, fileName=_s(sample),
        fileType=_s("promo"), fileDate=_s("2026-11-11 05:11:46"), fileSize=_s("28.64 KB"),
    )}
    folders = [_folder(_chain_title(row), [
        _request("List files", "GET", base + "/api/getfiles?edi=" + row["chain_code"],
                 tests=_save_first_json("pm.response.json()",
                                        "f => (f.fileName || '').startsWith('PriceFull')",
                                        [("fileName", "item.fileName")])),
        _download("%s/%s/{{fileName}}" % (base, row["chain_code"])),
    ], _chain_label(row)) for row in chains]
    return ("laibcatalog.co.il",
            _openapi("laibcatalog.co.il price portals", description, [_server(base)], paths,
                     schemas),
            _collection("laibcatalog.co.il", description, folders, ["fileName"]))


def carrefour(chains: List[Dict[str, str]]):
    base = "https://prices.carrefour.co.il"
    description = (
        "Carrefour / Yeinot Bitan / Mega portal (by U-CODE). Chains: "
        + ", ".join(_chain_label(row) for row in chains) + ".\n\n"
        "The day page embeds `const path = 'YYYYMMDD';` and `const files = [{\"name\": ...}];`; "
        "files are downloaded from `/{path}/{fileName}`."
    )
    sample = "PriceFull7290055700007-001-002-20261111-051004.gz"
    paths = {
        "/": {"get": {
            "summary": "Files page of a day",
            "parameters": [_date_param("date", "YYYYMMDD", EXAMPLE_DATE.replace("-", ""))],
            "responses": _html("HTML with the embedded `path` and `files` JS variables."),
        }},
        "/{path}/{fileName}": {"get": {
            "summary": "Download a file",
            "parameters": [_param("path", "path", "The page's `path` (YYYYMMDD).", "20261111"),
                           _file_name_param(sample)],
            "responses": _binary(),
        }},
    }
    items = [
        _request("List PriceFull files", "GET", base + "/?date={{dateCompact}}", tests=[
            "const html = pm.response.text();",
            "const path = html.match(/const path = '(\\d{8})';/);",
            "const files = html.match(/const files = (\\[[\\s\\S]*?\\]);/);",
            "pm.test('found the file list', () => pm.expect(path && files).to.be.ok);",
            "const item = files && JSON.parse(files[1]).find(f => f.name.startsWith('PriceFull'));",
            "pm.test('found a PriceFull file', () => pm.expect(item).to.not.equal(undefined));",
            "if (item) {",
            "    pm.collectionVariables.set('path', path[1]);",
            "    pm.collectionVariables.set('fileName', item.name);",
            "}",
        ]),
        _download(base + "/{{path}}/{{fileName}}"),
    ]
    return ("prices.carrefour.co.il",
            _openapi("Carrefour price portal", description, [_server(base)], paths),
            _collection("prices.carrefour.co.il", description, items, ["path", "fileName"]))


def citymarket(chains: List[Dict[str, str]]):
    base = "https://www.citymarket-shops.co.il"
    description = (
        "City Market portal - paged HTML table filtered by day. Chains: "
        + ", ".join(_chain_label(row) for row in chains) + ".\n\n"
        "File names are shown without extension; downloads are `.xml.gz`. "
        "The last page number is in the `?p=N` pager links."
    )
    paths = {
        "/": {"get": {
            "summary": "Files table page",
            "parameters": [
                _param("p", "query", "Page number (1-based).", 1, schema={"type": "integer"}),
                _param("t", "query", "File type; 1 = prices.", "1"),
                _param("f", "query", "1 = full files only.", "1"),
                _date_param("d"),
            ],
            "responses": _html("Table rows: `<td>PriceFull...</td> ... "
                               "href=\"/downloadFile/{fileId}\"`."),
        }},
        "/downloadFile/{fileId}": {"get": {
            "summary": "Download a file",
            "parameters": [_param("fileId", "path", "File id (GUID) from the table.",
                                  "98d44c9d-c498-4821-944f-8684df95eec4")],
            "responses": _binary(),
        }},
    }
    items = [
        _request("List PriceFull files", "GET", base + "/?p=1&t=1&f=1&d={{date}}",
                 tests=_save_first_match(
                     r"""/<td>\s*(PriceFull[^<\s]+)\s*<\/td>[\s\S]*?href="(\/downloadFile\/[^"]+)"/""",
                     [("fileName", "m[1] + '.xml.gz'"), ("fileUrl", "'%s' + m[2]" % base)])),
        _download("{{fileUrl}}"),
    ]
    return ("www.citymarket-shops.co.il",
            _openapi("City Market price portal", description, [_server(base)], paths),
            _collection("www.citymarket-shops.co.il", description, items,
                        ["fileName", "fileUrl"]))


def hazihinam(chains: List[Dict[str, str]]):
    base = "https://shop.hazi-hinam.co.il"
    blob = "https://hazihinamprod01.blob.core.windows.net"
    description = (
        "Hazi Hinam portal - paged HTML table. Chains: "
        + ", ".join(_chain_label(row) for row in chains) + ".\n\n"
        "Links point to Azure blob storage (`%s/regulatories/`). The next page exists while "
        "the page has a `href=\"?p=N+1&...\"` link." % blob
    )
    sample = "PriceFull7290700100008-000-219-20261111-151420.gz"
    paths = {
        "/Prices": {"get": {
            "summary": "Files table page",
            "parameters": [
                _param("p", "query", "Page number (1-based).", 1, schema={"type": "integer"}),
                _param("s", "query", "Store filter; empty = all.", "", required=False),
                _param("f", "query", "Free-text filter; empty = none.", "", required=False),
                _param("t", "query", "File type; 1 = prices (Price and PriceFull).", "1"),
                _date_param("d"),
            ],
            "responses": _html("Table with absolute download links."),
        }},
        "/regulatories/{fileName}": {
            "servers": [_server(blob, "Azure blob storage")],
            "get": {"summary": "Download a file",
                    "parameters": [_file_name_param(sample)],
                    "responses": _binary()},
        },
    }
    items = [
        _request("List PriceFull files", "GET", base + "/Prices?p=1&s=&f=&t=1&d={{date}}",
                 tests=_save_first_match(r"""/href="(https?:\/\/[^"]+\/(PriceFull[^"\/]+))"/""",
                                         [("fileUrl", "m[1]")])),
        _download("{{fileUrl}}"),
    ]
    return ("shop.hazi-hinam.co.il",
            _openapi("Hazi Hinam price portal", description, [_server(base)], paths),
            _collection("shop.hazi-hinam.co.il", description, items, ["fileUrl"]))


def kt(chains: List[Dict[str, str]]):
    base = "https://list-files.w5871031-kt.workers.dev"
    storage = "https://kt-prices.s3.eu-central-003.backblazeb2.com"
    description = (
        "KT feed (Cloudflare worker) - one JSON list of every published file with a direct url "
        "(Backblaze B2 storage). Ignores dates. Chains: "
        + ", ".join(_chain_label(row) for row in chains) + "."
    )
    sample = "PriceFull5144744100002-001-001-20261111-000001.xml.gz"
    paths = {
        "/": {"get": {
            "summary": "List all files",
            "responses": _json("Every published file.", _array_of("KTFile")),
        }},
        "/{fileName}": {
            "servers": [_server(storage, "Backblaze B2 storage")],
            "get": {"summary": "Download a file (the item's `url`)",
                    "parameters": [_file_name_param(sample)],
                    "responses": _binary()},
        },
    }
    schemas = {"KTFile": _obj(
        type=_s("PriceFull"), name=_s(sample), url=_s(storage + "/" + sample, format="uri"),
        end_time={"type": "integer", "format": "int64", "example": 1802296802914},
        snif={"type": "string", "nullable": True}, date=_s("2026-11-11 00:00:01"),
    )}
    items = [
        _request("List files", "GET", base + "/",
                 tests=_save_first_json("pm.response.json()",
                                        "f => f.type === 'PriceFull' && f.url",
                                        [("fileUrl", "item.url")])),
        _download("{{fileUrl}}"),
    ]
    return ("list-files.w5871031-kt.workers.dev",
            _openapi("KT price feed", description, [_server(base)], paths, schemas),
            _collection("list-files.w5871031-kt.workers.dev", description, items, ["fileUrl"]))


def netivhesed(chains: List[Dict[str, str]]):
    base = "https://app.netiv-hesed.com"
    description = "Netiv HaChesed portal - HTML table per day. Chains: " + ", ".join(
        _chain_label(row) for row in chains) + "."
    sample = "PriceFull7290058160839-002-001-20261111-051729.GZ"
    paths = {
        "/": {"get": {
            "summary": "Files page of a day",
            "parameters": [_date_param("Date")],
            "responses": _html("Table with `href=\"/Prices/Download?fileName=...\"` links."),
        }},
        "/Prices/Download": {"get": {
            "summary": "Download a file",
            "parameters": [_param("fileName", "query", "File name from the page.", sample)],
            "responses": _binary(),
        }},
    }
    items = [
        _request("List PriceFull files", "GET", base + "/?Date={{date}}",
                 tests=_save_first_match(r"""/href="\/Prices\/Download\?fileName=(PriceFull[^"&]+)"/""",
                                         [("fileName", "m[1]")])),
        _download(base + "/Prices/Download?fileName={{fileName}}"),
    ]
    return ("app.netiv-hesed.com",
            _openapi("Netiv HaChesed price portal", description, [_server(base)], paths),
            _collection("app.netiv-hesed.com", description, items, ["fileName"]))


def shufersal(chains: List[Dict[str, str]]):
    base = "https://prices.shufersal.co.il"
    blob = "https://pricesprodpublic.blob.core.windows.net"
    description = (
        "Shufersal portal - paged HTML table (no date filter). Chains: "
        + ", ".join(_chain_label(row) for row in chains) + ".\n\n"
        "Very slow: a page can take ~2 minutes (in Postman set Settings > Request timeout = 0). "
        "The number of pages is in the `page=N` pager links. Links are short-lived signed "
        "(SAS) urls on Azure blob storage `%s/pricefull/`." % blob
    )
    sample = "PriceFull7290027600007-001-001-20261111-032159.gz"
    paths = {
        "/FileObject/UpdateCategory": {"get": {
            "summary": "Files table page",
            "parameters": [
                _param("catID", "query", "Category; 2 = PriceFull.", "2"),
                _param("storeId", "query", "Store; 0 = all.", "0"),
                _param("page", "query", "Page number (1-based).", 1, schema={"type": "integer"}),
            ],
            "responses": _html("Table with signed download links (`&amp;`-escaped)."),
        }},
        "/pricefull/{fileName}": {
            "servers": [_server(blob, "Azure blob storage")],
            "get": {"summary": "Download a file (signed url from the table)",
                    "parameters": [_file_name_param(sample)] + [
                        _param(name, "query", "SAS signature part, copied from the link.")
                        for name in ("sv", "sr", "sig", "se", "sp")],
                    "responses": _binary()},
        },
    }
    items = [
        _request("List PriceFull files", "GET",
                 base + "/FileObject/UpdateCategory?catID=2&storeId=0&page=1",
                 tests=_save_first_match(
                     r"""/href="(https?:\/\/[^"]+\/(PriceFull[^"\/?]+)[^"]*)"/""",
                     [("fileUrl", "m[1].replace(/&amp;/g, '&')")])),
        _download("{{fileUrl}}"),
    ]
    return ("prices.shufersal.co.il",
            _openapi("Shufersal price portal", description, [_server(base)], paths),
            _collection("prices.shufersal.co.il", description, items, ["fileUrl"]))


def superpharm(chains: List[Dict[str, str]]):
    base = "https://prices.super-pharm.co.il"
    description = (
        "Super-Pharm portal - paged MVC grid. Chains: "
        + ", ".join(_chain_label(row) for row in chains) + ".\n\n"
        "Pages = ceil(`data-total-rows` / `mvc-grid-pager-rows` value)."
    )
    sample = "PriceFull7290172900007-000-260-20261111-071626.gz"
    paths = {
        "/": {"get": {
            "summary": "Files grid page",
            "parameters": [
                _param("Category-equals", "query", "File category.", "PriceFull"),
                _date_param("Date-equals", "DD/MM/YYYY", "11/11/2026"),
                _param("page", "query", "Page number (1-based).", 1, schema={"type": "integer"}),
            ],
            "responses": _html("Grid with `href=\"/Download/...\"` links."),
        }},
        "/Download/{fileName}": {"get": {
            "summary": "Download a file",
            "parameters": [_file_name_param(sample),
                           _param("bucketName", "query", "Storage bucket from the link.",
                                  "sp_transparency_output_prod_v2")],
            "responses": _binary(),
        }},
    }
    items = [
        _request("List PriceFull files", "GET",
                 base + "/?Category-equals=PriceFull&Date-equals={{dateDmy}}&page=1",
                 tests=_save_first_match(r"""/href="(\/Download\/(PriceFull[^"?\/]+)[^"]*)"/""",
                                         [("fileUrl", "'%s' + m[1].replace(/&amp;/g, '&')"
                                           % base)])),
        _download("{{fileUrl}}"),
    ]
    return ("prices.super-pharm.co.il",
            _openapi("Super-Pharm price portal", description, [_server(base)], paths),
            _collection("prices.super-pharm.co.il", description, items, ["fileUrl"]))


def wolt(chains: List[Dict[str, str]]):
    base = "https://wm-gateway.wolt.com/isr-prices/public/v1"
    description = "Wolt price feed - static HTML index per day. Chains: " + ", ".join(
        _chain_label(row) for row in chains) + "."
    sample = "PriceFull7290058249350-000-046-20261111-000006.gz"
    paths = {
        "/{date}.html": {"get": {
            "summary": "Index of a day",
            "parameters": [_param("date", "path", "Day (YYYY-MM-DD).", EXAMPLE_DATE)],
            "responses": _html("Relative links `download/{date}/{fileName}`."),
        }},
        "/download/{date}/{fileName}": {"get": {
            "summary": "Download a file",
            "parameters": [_param("date", "path", "Day (YYYY-MM-DD).", EXAMPLE_DATE),
                           _file_name_param(sample)],
            "responses": _binary(),
        }},
    }
    items = [
        _request("List PriceFull files", "GET", base + "/{{date}}.html",
                 tests=_save_first_match(r"""/href="([^"]*?\/(PriceFull[^"\/]+))"/""",
                                         [("fileUrl", "'%s/' + m[1]" % base)])),
        _download("{{fileUrl}}"),
    ]
    return ("wm-gateway.wolt.com",
            _openapi("Wolt price feed", description, [_server(base)], paths),
            _collection("wm-gateway.wolt.com", description, items, ["fileUrl"]))


# platform key in chains.csv -> generator
DOMAINS = {
    "bina": bina,
    "cerberus": cerberus,
    "laib": laibcatalog,
    "carrefour": carrefour,
    "citymarket": citymarket,
    "hazihinam": hazihinam,
    "kt": kt,
    "netivhesed": netivhesed,
    "shufersal": shufersal,
    "superpharm": superpharm,
    "wolt": wolt,
}


def _write(path: str, doc: Dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main() -> None:
    chains = _load_chains()
    missing = set(chains) - set(DOMAINS)
    if missing:
        raise SystemExit("no API docs generator for platform(s): %s" % ", ".join(sorted(missing)))
    for platform, generate in DOMAINS.items():
        domain, openapi, collection = generate(chains.get(platform, []))
        folder = os.path.join(OUT_DIR, domain)
        os.makedirs(folder, exist_ok=True)
        _write(os.path.join(folder, "openapi.json"), openapi)
        _write(os.path.join(folder, "postman_collection.json"), collection)
        print("%-40s %d chain(s)" % (domain, len(chains.get(platform, []))))


if __name__ == "__main__":
    main()
