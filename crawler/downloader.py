import logging
import os
import re

from .platforms import RemoteFile
from .platforms.base import DEFAULT_TIMEOUT

log = logging.getLogger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(name: str) -> str:
    """Remote names are untrusted - keep a plain file name with no path parts."""
    cleaned = _UNSAFE.sub("_", os.path.basename(name.replace("\\", "/")))
    return cleaned.lstrip(".") or "unnamed"


def download(remote: RemoteFile, target_dir: str) -> str:
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, safe_name(remote.name))
    if os.path.exists(path):
        log.debug("exists, skipping %s", path)
        return path

    platform = remote.platform
    url = platform.resolve_url(remote)
    tmp_path = path + ".part"
    with platform.session.get(url, stream=True, timeout=DEFAULT_TIMEOUT) as resp:
        resp.raise_for_status()
        with open(tmp_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                fh.write(chunk)
    os.replace(tmp_path, path)
    return path
