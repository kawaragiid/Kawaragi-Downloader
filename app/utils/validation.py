import re

def is_valid_url(url: str) -> bool:
    """Memvalidasi URL dengan cepat menggunakan regex (tanpa freeze)."""
    if not url:
        return False
    url = url.strip()
    url_regex = re.compile(
        r'^(https?://)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(:\d+)?(/.*)?$',
        re.IGNORECASE
    )
    return bool(url_regex.match(url))