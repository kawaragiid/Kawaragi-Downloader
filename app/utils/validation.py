import re

def is_valid_url(url: str) -> bool:
    """Memvalidasi URL dengan cepat menggunakan regex (tanpa freeze)."""
    # Regex generik untuk memvalidasi bentuk URL
    url_regex = re.compile(
        r'^(https?://)?(www\.)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(/.*)?$'
    )
    return bool(url_regex.match(url))