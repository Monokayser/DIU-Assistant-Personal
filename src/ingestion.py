from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import urllib.request


ALLOWED_HOSTS = {
    "daffodilvarsity.edu.bd",
    "www.daffodilvarsity.edu.bd",
    "admission.daffodilvarsity.edu.bd",
    "research.daffodilvarsity.edu.bd",
    "news.daffodilvarsity.edu.bd",
    "alumni.daffodilvarsity.edu.bd",
    "parents.daffodilvarsity.edu.bd",
    "it.daffodilvarsity.edu.bd",
    "webbackend.daffodilvarsity.edu.bd",
}
PRIMARY_OFFICIAL_HOST = "daffodilvarsity.edu.bd"
DEFAULT_MAX_PAGES = 1000
DEFAULT_FETCH_TIMEOUT_SECONDS = 8
AUTHORITATIVE_EXTERNAL_URLS = {
    "https://www.timeshighereducation.com/world-university-rankings/daffodil-international-university-diu",
    "https://www.topuniversities.com/universities/daffodil-international-university",
    "https://en.wikipedia.org/wiki/Daffodil_International_University",
}
APPROVED_SOURCE_URLS = [
    "https://daffodilvarsity.edu.bd/",
    "https://www.facebook.com/daffodilvarsity.edu.bd/",
    "https://www.topuniversities.com/universities/daffodil-international-university",
    "https://www.timeshighereducation.com/world-university-rankings/daffodil-international-university-diu",
    "https://en.wikipedia.org/wiki/Daffodil_International_University",
]
CURATED_APPROVED_CHUNKS = [
    {
        "id": "authoritative-diu-homepage-2026-0",
        "url": "https://daffodilvarsity.edu.bd/",
        "title": "Daffodil International University Official Homepage",
        "text": (
            "Approved DIU source. The official Daffodil International University homepage says DIU is shaping futures with a global vision and is ranked among the world's best, proudly #1 in Bangladesh. "
            "The homepage states the university vision: becoming a globally recognized center of excellence through innovative, learner-centric, technology-driven education and impactful research. "
            "It highlights global impact rankings, including Global Top-20 in SDG 4 and Top-40 in SDG 8, and lists 38 programs, 6 faculties, and undergraduate and graduate pathways. "
            "It also presents DIU scholarship programs as a way to turn ambition into achievement."
        ),
    },
    {
        "id": "authoritative-diu-facebook-2026-0",
        "url": "https://www.facebook.com/daffodilvarsity.edu.bd/",
        "title": "Daffodil International University Official Facebook Page",
        "text": (
            "Approved DIU social source. The official Daffodil International University Facebook page can be used as an official DIU social channel for current public notices, campus announcements, events, and social updates. "
            "For permanent policies, fees, admissions requirements, program details, and eligibility rules, prefer the official DIU website or DIU subdomains when available. "
            "Use the Facebook page mainly for fresh announcements or public social updates when search grounding supplies it."
        ),
    },
    {
        "id": "authoritative-qs-topuniversities-diu-2026-0",
        "url": "https://www.topuniversities.com/universities/daffodil-international-university",
        "title": "Daffodil International University : Rankings, Fees & Courses Details | TopUniversities",
        "text": (
            "Approved ranking source. QS TopUniversities lists Daffodil International University as one of the top private not-for-profit universities in Dhaka, Bangladesh. "
            "The QS profile ranks DIU #1001-1200 in QS World University Rankings 2026, #301-350 in QS WUR Ranking by Subject, #=484 in QS Sustainability Ranking, and #=221 in Asian University Rankings. "
            "QS also lists the QS World University Rankings trend as #1201-1400 in 2024, #1201-1400 in 2025, and #1001-1200 in 2026. "
            "QS student and staff figures on the profile include total students 17,085, international students 559, and total faculty staff 770."
        ),
    },
    {
        "id": "authoritative-times-higher-education-diu-2026-0",
        "url": "https://www.timeshighereducation.com/world-university-rankings/daffodil-international-university-diu",
        "title": "Daffodil International University (DIU) | World University Rankings | THE",
        "text": (
            "Approved ranking source. Times Higher Education lists Daffodil International University (DIU) in Savar, Bangladesh and marks it as Ranked and Sustainability Impact Rated. "
            "THE lists DIU at 801-1000th in World University Rankings 2026. "
            "The THE profile also lists subject rankings for 2026: Business and Economics 601-800th, Medical and Health 301-400th, Computer Science 601-800th, Engineering 601-800th, and Life Sciences 601-800th. "
            "It lists Social Sciences 2025 at 401-500th. In THE Impact Rankings 2025, DIU is listed at 101-200th overall, with Quality Education 19th, No Poverty =36th, Zero Hunger 53rd, Decent Work and Economic Growth =33rd, and Reduced Inequalities 60th."
        ),
    },
    {
        "id": "authoritative-wikipedia-diu-overview-2026-0",
        "url": "https://en.wikipedia.org/wiki/Daffodil_International_University",
        "title": "Daffodil International University - Wikipedia",
        "text": (
            "Approved supplementary background source. Wikipedia describes Daffodil International University (DIU) as a private research university in Bangladesh, established on 24 January 2002. "
            "The article locates DIU at Daffodil Smart City, Birulia, Savar, Dhaka-1216, Bangladesh, and lists the campus as 360 acres. "
            "Its infobox includes ranking snapshots: QS World 1001-1200 (2026), THE World 801-1000 (2026), QS Asia 221 (2026), THE Business and Economics 601-800 (2026), THE Clinical and Health 301-400 (2026), THE Computer Science 601-800 (2026), and THE Engineering 601-800 (2026). "
            "Use this page as supplementary overview evidence, not as the highest authority for official DIU policies or rankings when DIU, QS, or THE source pages are available."
        ),
    },
]
SITEMAP_URLS = [
    f"https://{host}/sitemap.xml"
    for host in sorted(ALLOWED_HOSTS)
    if host != "www.daffodilvarsity.edu.bd"
]
SEED_URLS = [
    "https://daffodilvarsity.edu.bd/",
    "https://www.timeshighereducation.com/world-university-rankings/daffodil-international-university-diu",
    "https://www.topuniversities.com/universities/daffodil-international-university",
    "https://en.wikipedia.org/wiki/Daffodil_International_University",
    "https://daffodilvarsity.edu.bd/rankings",
    "https://daffodilvarsity.edu.bd/faculties",
    "https://daffodilvarsity.edu.bd/programs?isUndergraduate=true",
    "https://daffodilvarsity.edu.bd/programs?isPostgraduate=true",
    "https://daffodilvarsity.edu.bd/scholarship",
    "https://daffodilvarsity.edu.bd/tuition-fee-calculator",
    "https://daffodilvarsity.edu.bd/admission-contact",
    "https://admission.daffodilvarsity.edu.bd/",
    "https://research.daffodilvarsity.edu.bd/",
    "https://news.daffodilvarsity.edu.bd/",
    "https://alumni.daffodilvarsity.edu.bd/",
    "https://daffodilvarsity.edu.bd/department/mct",
    "https://daffodilvarsity.edu.bd/department/mct/admission-eligibility",
    "https://webbackend.daffodilvarsity.edu.bd/department/mct",
    "https://webbackend.daffodilvarsity.edu.bd/department/mct/program/bsc-in-mct",
]
SKIP_PATH_KEYWORDS = {
    "/article/copyright",
    "/article/security",
    "/article/traffic",
    "/privacy",
    "/report",
    "/subscribe",
    "/login",
    "/signin",
    "/register",
    "/feed",
}
PRIORITY_PATH_KEYWORDS = {
    "admission",
    "program",
    "faculty",
    "scholarship",
    "tuition",
    "research",
    "news",
    "contact",
    "campus",
    "student",
    "faq",
    "about",
    "ranking",
}
SKIP_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".zip",
    ".mp4",
    ".mp3",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
)


class VisibleContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.links: list[str] = []
        self.text_parts: list[str] = []
        self._current_tag = ""
        self._suppress_stack: list[str] = []
        self._collect_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag.lower()
        attributes = dict(attrs)
        if self._current_tag == "script" and str(attributes.get("type") or "").lower() == "application/ld+json":
            self._collect_json_ld = True
            return
        if self._current_tag in {"script", "style", "noscript", "svg"}:
            self._suppress_stack.append(self._current_tag)
        if self._current_tag == "a":
            href = attributes.get("href")
            if href:
                self.links.append(href.strip())
        if self._current_tag == "meta":
            name = str(attributes.get("name") or attributes.get("property") or "").lower()
            content = str(attributes.get("content") or "").strip()
            if content and name in {"description", "keywords", "og:title", "og:description"}:
                self.text_parts.append(content)
        for attr_name in ("alt", "title", "aria-label"):
            value = str(attributes.get(attr_name) or "").strip()
            if value:
                self.text_parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        closing = tag.lower()
        if closing == "script" and self._collect_json_ld:
            self._collect_json_ld = False
            extracted = _extract_json_text("".join(self._json_ld_parts))
            if extracted:
                self.text_parts.append(extracted)
            self._json_ld_parts = []
            return
        if self._suppress_stack and self._suppress_stack[-1] == closing:
            self._suppress_stack.pop()
        if closing in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "br"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._collect_json_ld:
            self._json_ld_parts.append(data)
            return
        if self._suppress_stack:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._current_tag == "title" and not self.title:
            self.title = cleaned
        elif self._current_tag in {
            "title",
            "h1",
            "h2",
            "h3",
            "h4",
            "p",
            "li",
            "span",
            "a",
            "strong",
            "em",
            "div",
        }:
            self.text_parts.append(cleaned)

    def get_text(self) -> str:
        lines = [line.strip() for line in "".join(self.text_parts).splitlines()]
        return "\n".join(line for line in lines if len(line) > 1)


@dataclass
class PageData:
    url: str
    title: str
    text: str
    links: list[str]


def build_site_index(
    base_url: str,
    output_path: str | Path,
    *,
    max_pages: int | None = None,
    request_delay: float = 0.15,
    include_sitemaps: bool = True,
) -> dict:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_budget = max_pages if max_pages is not None else _env_int("DIU_SITE_MAX_PAGES", DEFAULT_MAX_PAGES)
    pages = crawl_site(
        base_url,
        max_pages=page_budget,
        request_delay=request_delay,
        include_sitemaps=include_sitemaps,
    )
    chunks: list[dict] = []
    for page in pages:
        chunks.extend(_page_to_chunks(page))
    chunks.extend(_missing_curated_chunks(chunks))
    page_entries = [
        {"url": page.url, "title": page.title, "text_preview": page.text[:240]}
        for page in pages
    ] + _missing_curated_pages(pages)

    payload = {
        "metadata": {
            "base_url": base_url,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "crawl_budget_pages": page_budget,
            "include_sitemaps": include_sitemaps,
            "approved_sources": APPROVED_SOURCE_URLS,
            "source_policy": (
                "Official DIU pages are preferred for institutional facts; "
                "QS TopUniversities and Times Higher Education are preferred for rankings; "
                "Wikipedia is supplementary background."
            ),
            "pages_count": len(page_entries),
            "chunks_count": len(chunks),
        },
        "pages": page_entries,
        "chunks": chunks,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["metadata"]


def crawl_site(
    base_url: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    request_delay: float = 0.15,
    include_sitemaps: bool = True,
) -> list[PageData]:
    sitemap_urls = discover_sitemap_urls() if include_sitemaps else []
    initial_urls = [base_url, *SEED_URLS, *sitemap_urls]
    queue: deque[str] = deque(_normalize_url(url) for url in initial_urls if _normalize_url(url))
    visited: set[str] = set()
    pages: list[PageData] = []
    queued: set[str] = set(queue)

    while queue and len(pages) < max_pages:
        url = _normalize_url(queue.popleft())
        if not url or url in visited or not _is_allowed_url(url):
            continue
        visited.add(url)

        page = fetch_page(url)
        if not page or len(page.text) < 180:
            continue
        pages.append(page)

        if not _should_follow_links(url):
            time.sleep(request_delay)
            continue

        prioritized_links = sorted(
            (
                _normalize_url(urljoin(url, href))
                for href in page.links
            ),
            key=_url_priority_score,
            reverse=True,
        )
        for next_url in prioritized_links:
            if (
                next_url
                and next_url not in visited
                and next_url not in queued
                and _is_allowed_url(next_url)
            ):
                queue.append(next_url)
                queued.add(next_url)

        time.sleep(request_delay)

    return pages


def discover_sitemap_urls(*, max_urls: int = 5000) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    sitemap_queue: deque[tuple[str, int]] = deque((url, 0) for url in SITEMAP_URLS)

    while sitemap_queue and len(found) < max_urls:
        sitemap_url, depth = sitemap_queue.popleft()
        if sitemap_url in seen or depth > 3:
            continue
        seen.add(sitemap_url)

        content = _fetch_sitemap_xml(sitemap_url)
        if not content:
            continue

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            continue

        for loc in root.findall(".//{*}loc"):
            value = (loc.text or "").strip()
            if not value:
                continue
            normalized = _normalize_url(value)
            if not normalized:
                continue
            if normalized.lower().endswith(".xml"):
                sitemap_queue.append((normalized, depth + 1))
            elif _is_allowed_url(normalized):
                found.append(normalized)
                if len(found) >= max_urls:
                    break

    return list(dict.fromkeys(found))


def _fetch_sitemap_xml(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; DIUCampusAssistant/1.0)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_env_int("DIU_FETCH_TIMEOUT_SECONDS", DEFAULT_FETCH_TIMEOUT_SECONDS)) as response:
            content_type = response.headers.get("Content-Type", "")
            if "xml" not in content_type and "text/plain" not in content_type:
                return ""
            return response.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def fetch_page(url: str) -> PageData | None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DIUCampusAssistant/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_env_int("DIU_FETCH_TIMEOUT_SECONDS", DEFAULT_FETCH_TIMEOUT_SECONDS)) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return None
            raw_html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    parser = VisibleContentParser()
    try:
        parser.feed(raw_html)
    except Exception:
        return None

    title = parser.title or urlparse(url).path.strip("/") or "DIU page"
    text = _clean_text(parser.get_text())
    return PageData(url=url, title=title, text=text, links=parser.links)


def _page_to_chunks(page: PageData, *, max_chars: int = 950) -> list[dict]:
    paragraphs = [p.strip() for p in page.text.splitlines() if len(p.strip()) > 45]
    if not paragraphs:
        return []

    chunks: list[dict] = []
    current = ""
    chunk_index = 0

    for paragraph in paragraphs:
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(
                {
                    "id": f"{_slugify(page.title)}-{chunk_index}",
                    "url": page.url,
                    "title": page.title,
                    "text": current.strip(),
                }
            )
            chunk_index += 1
        current = paragraph

    if current:
        chunks.append(
            {
                "id": f"{_slugify(page.title)}-{chunk_index}",
                "url": page.url,
                "title": page.title,
                "text": current.strip(),
            }
        )

    return chunks


def _clean_text(text: str) -> str:
    lines = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if len(line) < 3:
            continue
        if line.lower() in seen:
            continue
        seen.add(line.lower())
        lines.append(line)
    return "\n".join(lines)


def _extract_json_text(raw_json: str) -> str:
    try:
        parsed = json.loads(raw_json)
    except Exception:
        return ""

    values: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in {"name", "headline", "description", "articlebody", "text", "address", "email", "telephone"}:
                    walk(child)
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            cleaned = " ".join(value.split()).strip()
            if len(cleaned) >= 3:
                values.append(cleaned)

    walk(parsed)
    return "\n".join(dict.fromkeys(values))


def _missing_curated_chunks(chunks: list[dict]) -> list[dict]:
    existing_ids = {str(chunk.get("id") or "") for chunk in chunks}
    return [dict(chunk) for chunk in CURATED_APPROVED_CHUNKS if chunk["id"] not in existing_ids]


def _missing_curated_pages(pages: list[PageData]) -> list[dict]:
    existing_urls = {page.url.rstrip("/") for page in pages}
    missing_pages: list[dict] = []
    for chunk in CURATED_APPROVED_CHUNKS:
        if chunk["url"].rstrip("/") in existing_urls:
            continue
        missing_pages.append(
            {
                "url": chunk["url"],
                "title": chunk["title"],
                "text_preview": chunk["text"][:240],
            }
        )
    return missing_pages


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if any(keyword in parsed.path.lower() for keyword in SKIP_PATH_KEYWORDS):
        return ""
    if parsed.fragment:
        parsed = parsed._replace(fragment="")
    normalized = parsed.geturl().rstrip("/")
    if normalized.endswith(SKIP_EXTENSIONS):
        return ""
    return normalized


def _is_allowed_url(url: str) -> bool:
    if url.rstrip("/") in AUTHORITATIVE_EXTERNAL_URLS:
        return True
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_HOSTS:
        return False
    if any(parsed.path.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    return True


def _should_follow_links(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc in ALLOWED_HOSTS


def _url_priority_score(url: str) -> tuple[int, int, int]:
    lowered = url.lower()
    keyword_hits = sum(1 for keyword in PRIORITY_PATH_KEYWORDS if keyword in lowered)
    official_home_bonus = 1 if urlparse(url).netloc == PRIMARY_OFFICIAL_HOST else 0
    shorter_bonus = max(0, 120 - len(lowered))
    return keyword_hits, official_home_bonus, shorter_bonus


def _slugify(text: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in text)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:64] or "page"
