import re
import logging
import sqlite3
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; PinPointDealFinder/1.0; "
    "+https://github.com/Alanrunsit/PinPoint_FBLA)"
)
REQUEST_TIMEOUT = 15

DISCOUNT_PATTERN = re.compile(
    r"(\d{1,3}\s*%\s*off"
    r"|\$\d+(?:\.\d{2})?\s*off"
    r"|buy\s+\d+\s+get\s+\d+(?:\s+free)?"
    r"|free\s+\w+(?:\s+\w+)?"
    r"|save\s+(?:\d+\s*%|\$\d+)"
    r"|half\s+(?:off|price)"
    r"|bogo)",
    re.IGNORECASE,
)

COUPON_PATTERN = re.compile(
    r"(?:code|coupon|promo(?:\s*code)?)[:\s]+([A-Z0-9]{3,20})",
    re.IGNORECASE,
)

DEAL_KEYWORDS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\d+\s*%\s*off",
        r"\$\d+\s*off",
        r"save\s+\d+",
        r"buy\s+\d+\s+get",
        r"free\s+\w+",
        r"\bsale\b",
        r"special\s+offer",
        r"limited\s+time",
        r"\bpromo(?:tion)?\b",
        r"\bcoupon\b",
        r"\bdiscount(?:ed)?\b",
        r"deal\s+of",
        r"use\s+code",
        r"\bhappy\s+hour\b",
        r"\bearly\s+bird\b",
        r"loyalty\s+(?:program|reward)",
        r"first\s+(?:time|visit)",
        r"new\s+(?:client|customer|patient)\s+(?:special|offer|discount)",
        r"complimentary",
        r"introductory\s+(?:rate|offer|price)",
    ]
]


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_page(url):
    """Fetch raw HTML from *url*. Returns text or ``None`` on failure."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _score_text(text):
    """Return (score, discount_match, coupon_match) for a text chunk."""
    score = 0
    for kw in DEAL_KEYWORDS:
        if kw.search(text):
            score += 1
    discount_match = DISCOUNT_PATTERN.search(text)
    coupon_match = COUPON_PATTERN.search(text)
    if discount_match:
        score += 2
    if coupon_match:
        score += 2
    return score, discount_match, coupon_match


def extract_deals_from_html(html, business_name):
    """Parse *html* and return a list of deal dicts."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    deals = []
    seen_texts = []
    seen_discounts = set()

    elements = soup.find_all(
        ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "span", "div", "a", "td"],
    )

    for elem in elements:
        text = elem.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        if not text or len(text) < 12 or len(text) > 500:
            continue

        score, discount_match, coupon_match = _score_text(text)
        if score < 2:
            continue

        normalized = text.lower().strip()
        is_dup = False
        cur_words = set(normalized.split())
        for prev, prev_words in seen_texts:
            if normalized in prev or prev in normalized:
                is_dup = True
                break
            overlap = cur_words & prev_words
            smaller = min(len(cur_words), len(prev_words))
            if smaller and len(overlap) / smaller > 0.6:
                is_dup = True
                break
        if is_dup:
            continue
        seen_texts.append((normalized, cur_words))

        discount_text = (
            discount_match.group(1).strip() if discount_match else "Special Offer"
        )

        discount_key = discount_text.lower()
        if discount_key in seen_discounts:
            continue
        seen_discounts.add(discount_key)

        coupon_code = coupon_match.group(1).upper() if coupon_match else None
        title = f"{business_name} — {discount_text}"
        if len(title) > 120:
            title = title[:117] + "..."

        deals.append(
            {
                "title": title,
                "description": text[:300],
                "discount_text": discount_text,
                "coupon_code": coupon_code,
                "score": score,
            }
        )

    deals.sort(key=lambda d: d["score"], reverse=True)
    return deals[:3]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_scraper(db_path):
    """Scrape every business website and upsert deals into the database."""
    logger.info("Deal scraper starting at %s", datetime.now().isoformat())

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        businesses = conn.execute(
            "SELECT id, name, website_url FROM businesses "
            "WHERE website_url IS NOT NULL AND website_url != ''"
        ).fetchall()

        logger.info("Found %d businesses with websites", len(businesses))

        conn.execute("UPDATE deals SET active = 0 WHERE source = 'scraped'")
        conn.commit()

        expiry = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        scraped_count = 0

        for biz in businesses:
            biz_id, biz_name, url = biz["id"], biz["name"], biz["website_url"]
            logger.info("Scraping %s (%s)", biz_name, url)

            html = fetch_page(url)
            if not html:
                continue

            found_deals = extract_deals_from_html(html, biz_name)
            if not found_deals:
                logger.info("  No deals found for %s", biz_name)
                continue

            for deal in found_deals:
                conn.execute(
                    "INSERT INTO deals "
                    "(business_id, title, description, discount_text, "
                    " coupon_code, expiry_date, source, active, scraped_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'scraped', 1, CURRENT_TIMESTAMP)",
                    (
                        biz_id,
                        deal["title"],
                        deal["description"],
                        deal["discount_text"],
                        deal["coupon_code"],
                        expiry,
                    ),
                )
                scraped_count += 1

            conn.commit()

        logger.info("Scraper finished. Inserted %d scraped deals.", scraped_count)
        return scraped_count

    except Exception:
        logger.exception("Scraper error")
        conn.rollback()
        return 0
    finally:
        conn.close()
