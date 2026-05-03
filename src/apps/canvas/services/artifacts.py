from __future__ import annotations

import mimetypes
import re
import secrets
from html import escape
from pathlib import Path
from typing import Any


def create_canvas_artifacts(
    output_root: Path,
    *,
    session_id: str,
    question: str,
    answer: str,
    sources: list[dict[str, Any]] | None = None,
    base_path: str = "/api/artifacts",
    require_model_html: bool = False,
) -> list[dict[str, Any]]:
    safe_session = safe_storage_name(session_id)
    session_dir = output_root / safe_session
    session_dir.mkdir(parents=True, exist_ok=True)

    clean_question = _extract_visible_question(question)
    model_html = _extract_html_artifact(answer)
    title = _derive_title(clean_question, answer, model_html=model_html)

    # Always prefer model-generated HTML — the model produces better
    # interactive code than our static templates.
    if model_html:
        html = _normalize_html_document(model_html, title=title)
    elif require_model_html:
        return []
    elif _is_specialist_mode(question) or _wants_interactive_canvas(question):
        html = _build_interactive_canvas(title=title, content=answer, sources=sources or [])
    else:
        html = _build_static_document_canvas(title=title, content=answer)

    html = _inject_canvas_bridge(html)

    artifacts = [
        _write_artifact(
            session_dir,
            session_token=safe_session,
            base_path=base_path,
            label="Canvas",
            filename=f"{_slugify(title)}.html",
            mime_type="text/html",
            kind="workspace",
            title=title,
            content=html.encode("utf-8"),
        )
    ]

    return artifacts


def should_create_canvas_artifacts(question: str, answer: str = "") -> bool:
    normalized_question = str(question or "").lower()
    if not normalized_question.strip():
        return False

    if _wants_interactive_canvas(question):
        return True

    return bool(_extract_html_artifact(answer))


def _wants_interactive_canvas(question: str) -> bool:
    normalized_question = str(question or "").lower()
    if not normalized_question.strip():
        return False

    canvas_signals = (
        "[canvas force unlock]",
        "generate an interactive visual version",
        "visual version",
        "visualization",
        "visualizer",
        "generate canvas",
        "show me visually",
        "interactive version",
        "build a calculator tool",
        "visual wizard",
        "update canvas:",
    )
    return any(signal in normalized_question for signal in canvas_signals)


def _write_artifact(
    session_dir: Path,
    *,
    session_token: str,
    base_path: str,
    label: str,
    filename: str,
    mime_type: str,
    kind: str,
    title: str,
    content: bytes,
) -> dict[str, Any]:
    artifact_id = f"{secrets.token_hex(6)}-{filename}"
    artifact_path = session_dir / artifact_id
    artifact_path.write_bytes(content)
    return {
        "id": artifact_id,
        "label": label,
        "filename": filename,
        "mime_type": mime_type,
        "kind": kind,
        "title": title,
        "size_bytes": len(content),
        "url": f"{base_path.rstrip('/')}/{session_token}/{artifact_id}",
    }


def strip_canvas_code_blocks(answer: str) -> str:
    text = str(answer or "")
    html_artifact = _extract_html_artifact(text)

    stripped = re.sub(r"```[\s\S]*?```", "", text).strip()
    if html_artifact and html_artifact in stripped:
        stripped = stripped.replace(html_artifact, " ")

    stripped = re.sub(r"(?is)<!doctype\s+html[\s\S]*?(?:</html>|$)", " ", stripped)
    stripped = re.sub(r"(?is)<html[\s\S]*?(?:</html>|$)", " ", stripped)
    stripped = re.sub(r"\[canvas force unlock\]", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped or str(answer or "").strip()


def build_canvas_reply_text(question: str, answer: str, *, title: str = "") -> str:
    stripped = strip_canvas_code_blocks(answer)
    compact = re.sub(r"\s+", " ", stripped).strip()

    if compact and not _looks_like_html_artifact(compact) and len(compact) <= 220:
        return compact

    if _is_canvas_update_request(question):
        return "I updated the workspace. Open the canvas to review it."

    return "Here is your workspace. Open the canvas to explore it."


def resolve_artifact_path(output_root: Path, session_token: str, artifact_id: str) -> Path | None:
    safe_session = safe_storage_name(session_token)
    safe_artifact = Path(str(artifact_id or "")).name
    if not safe_artifact or safe_artifact != artifact_id:
        return None

    session_dir = (output_root / safe_session).resolve()
    artifact_path = (session_dir / safe_artifact).resolve()
    if not str(artifact_path).startswith(str(session_dir)):
        return None
    if not artifact_path.exists() or not artifact_path.is_file():
        return None
    return artifact_path


def guess_artifact_mime_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def safe_storage_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", str(value or "").strip()).strip("._") or "item"


def _extract_html_artifact(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return ""

    candidates: list[str] = []
    
    # Standard closed blocks
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(r"```(?:html|HTML|xml)?\s*\n?([\s\S]*?)```", text)
    )
    
    # Handle truncated blocks (start but no end)
    truncated_match = re.search(r"```(?:html|HTML|xml)?\s*\n?([\s\S]*)$", text)
    if truncated_match and "```" not in truncated_match.group(1):
        candidates.append(truncated_match.group(1).strip())

    raw_document = _extract_raw_html_document(text)
    if raw_document:
        candidates.append(raw_document)

    raw_fragment = _extract_raw_html_fragment(text)
    if raw_fragment:
        candidates.append(raw_fragment)

    valid_matches = [candidate for candidate in candidates if _looks_like_html_artifact(candidate)]
    if not valid_matches:
        return ""
    return max(valid_matches, key=len)


def _normalize_html_document(html: str, *, title: str) -> str:
    clean_html = str(html or "").strip()
    if not clean_html:
        return ""
    
    # Repair unclosed tags if the model was truncated
    repaired_html = _auto_repair_html(clean_html)
    repaired_html = _remove_markdown_table_separator_rows(repaired_html)
    
    if re.search(r"<!doctype\s+html|<html[\s>]", repaired_html, re.IGNORECASE):
        return repaired_html
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title or "Canvas")}</title>
</head>
<body>
{repaired_html}
</body>
</html>"""


def _auto_repair_html(html: str) -> str:
    """Closes tags that were opened but not closed (handles truncation)."""
    repaired = str(html or "").strip()
    if not repaired:
        return ""

    # 1. Handle mid-attribute or mid-tag truncation
    # If it ends with an unclosed quote after an equals (e.g. class="foo)
    if re.search(r'="[^"]*$', repaired):
        repaired += '"'
    elif re.search(r"='[^']*$", repaired):
        repaired += "'"
    
    # If it ends inside a tag (e.g. <div cl)
    if re.search(r'<[a-z0-9]+[^>]*$', repaired, re.IGNORECASE):
        repaired += ">"

    # 2. Handle unclosed CSS braces if inside a style tag
    # We look for the last <style> block
    style_blocks = list(re.finditer(r"<style[^>]*>([\s\S]*?)(?:</style>|$)", repaired, re.IGNORECASE))
    if style_blocks:
        last_style = style_blocks[-1]
        content = last_style.group(1)
        # If the block is not closed with </style>, check for unclosed braces
        if "</style>" not in repaired[last_style.start():].lower():
            open_braces = content.count("{")
            close_braces = content.count("}")
            if open_braces > close_braces:
                repaired += "}" * (open_braces - close_braces)
            repaired += "</style>"

    # 3. Tag balancing for common block and inline elements
    tags_to_balance = [
        "div", "section", "main", "article", "header", "footer", "nav", "aside", 
        "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", 
        "canvas", "svg", "script", "p", "span", "button", "label", "form",
        "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "a", "i", "b"
    ]
    stack = []
    
    # Extract tags while ignoring self-closing ones and attributes
    for match in re.finditer(r"<(/?)([a-z1-6]+)(?:\s+[^>]*)?>", repaired, re.IGNORECASE):
        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()
        
        # Self-closing tags (void elements)
        if tag_name in ["img", "br", "hr", "input", "meta", "link", "area", "base", "col", "embed", "param", "source", "track", "wbr"]:
            continue

        if tag_name not in tags_to_balance:
            continue
            
        if is_closing:
            if stack and stack[-1] == tag_name:
                stack.pop()
        else:
            stack.append(tag_name)
            
    # Append closing tags in reverse order
    for tag in reversed(stack):
        repaired += f"</{tag}>"
        
    return repaired


def _remove_markdown_table_separator_rows(html: str) -> str:
    def row_is_separator(row_html: str) -> bool:
        cells = re.findall(r"(?is)<t[dh][^>]*>\s*([^<]*)\s*</t[dh]>", row_html)
        normalized = [re.sub(r"\s+", "", cell) for cell in cells if cell is not None]
        return bool(normalized) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in normalized)

    return re.sub(
        r"(?is)<tr\b[^>]*>.*?</tr>",
        lambda match: "" if row_is_separator(match.group(0)) else match.group(0),
        html,
    )


def _inject_canvas_bridge(html: str) -> str:
    """Inject only the canvas messaging bridge — do NOT rewrite the model's color choices."""
    themed = str(html or "")
    bridge = """
  <script id="diu-canvas-bridge">
    window.canvas = {
      __internal_system_request: function(text) {
        if (window.parent) window.parent.postMessage({ type: 'canvas_action', action: 'send_prompt', prompt: text }, '*');
      }
    };
    document.addEventListener('DOMContentLoaded', function() {
      var interactiveSelector = 'a[href^="#"], button[data-target], button[data-scroll-target]';
      document.querySelectorAll(interactiveSelector).forEach(function(control) {
        if (control.dataset.diuCanvasWired === 'true') return;
        control.dataset.diuCanvasWired = 'true';
        control.addEventListener('click', function(event) {
          var targetId = control.getAttribute('href') || control.dataset.target || control.dataset.scrollTarget || '';
          if (!targetId || targetId === '#') return;
          if (targetId.charAt(0) !== '#') targetId = '#' + targetId;
          var target = document.querySelector(targetId);
          if (!target) return;
          event.preventDefault();
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          document.querySelectorAll('.active[data-diu-canvas-wired="true"], [aria-current="true"]').forEach(function(activeControl) {
            activeControl.classList.remove('active');
            activeControl.removeAttribute('aria-current');
          });
          control.classList.add('active');
          control.setAttribute('aria-current', 'true');
        });
      });
    });
  </script>"""
    if "</head>" in themed.lower():
        return re.sub(r"</head>", f"{bridge}\n</head>", themed, count=1, flags=re.IGNORECASE)
    return f"{bridge}\n{themed}"


def _derive_title(question: str, answer: str, *, model_html: str = "") -> str:
    html_title = _extract_title_from_html(model_html)
    if html_title:
        return html_title

    question_title = _clean_canvas_title(question)
    if question_title:
        return question_title

    heading_match = re.search(r"^#{1,6}\s+(.+)$", str(answer or ""), re.MULTILINE)
    if heading_match:
        return _clean_canvas_title(heading_match.group(1))

    return "DIU Workspace"


def _extract_visible_question(question: str) -> str:
    # Remove system signals from the question
    return re.sub(r"\[canvas force unlock\]", "", str(question or "")).strip()


def _slugify(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower()).strip()
    return re.sub(r'[-\s]+', '-', value)


def _build_static_document_canvas(*, title: str, content: str) -> str:
    # Simple line-based HTML conversion (avoiding markdown dependency)
    lines = str(content or "").splitlines()
    body_html = ""
    for line in lines:
        line = line.strip()
        if not line:
            body_html += "<br/>"
        elif line.startswith("## "):
            body_html += f"<h2>{escape(line[3:])}</h2>"
        elif line.startswith("# "):
            body_html += f"<h1>{escape(line[2:])}</h1>"
        elif line.startswith("- "):
            body_html += f"<li>{escape(line[2:])}</li>"
        else:
            body_html += f"<p>{escape(line)}</p>"
    
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title or "Canvas")}</title>
</head>
<body data-canvas-format="document">
  <article class="paper" data-document-style="editable-document" contenteditable="true">
    <header class="document-header">
      <p class="eyebrow">Editable Canvas document</p>
      <h1>{escape(title)}</h1>
      <p class="document-meta">Prepared for: {escape(title)}</p>
    </header>
    {body_html}
  </article>
</body>
</html>"""


def _is_specialist_mode(question: str) -> bool:
    return "Answer in DIU" in str(question or "") and "Mode" in str(question or "")


def _build_interactive_canvas(*, title: str, content: str, sources: list[dict[str, Any]]) -> str:
    sections = _extract_content_sections(content)
    section_links = "".join(
        f'<a href="#section-{index}" class="toc-link">{escape(section["title"])}</a>'
        for index, section in enumerate(sections, start=1)
    )
    section_cards = "".join(
        _render_canvas_section(section, index)
        for index, section in enumerate(sections, start=1)
    )
    source_links = "".join(
        _render_source_link(source)
        for source in sources[:6]
    ) or '<p class="empty-note">This workspace is based on the current DIU answer.</p>'
    intro = escape(_extract_canvas_intro(content))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title or "Interactive Canvas")}</title>
  <style>
    :root {{
      color-scheme: light;
      --canvas-bg: #f5f8f2;
      --canvas-surface: rgba(255, 255, 255, 0.96);
      --canvas-border: rgba(36, 95, 53, 0.12);
      --canvas-shadow: 0 16px 36px rgba(18, 32, 23, 0.08);
      --canvas-text: #173124;
      --canvas-muted: #5e6f63;
      --canvas-accent: #245f35;
      --canvas-accent-soft: rgba(36, 95, 53, 0.08);
    }}

    * {{ box-sizing: border-box; }}

    html, body {{
      margin: 0;
      min-height: 100%;
      background:
        radial-gradient(circle at top left, rgba(95, 177, 113, 0.14), transparent 28%),
        linear-gradient(180deg, rgba(255,255,255,0.82), rgba(245,248,242,0.96)),
        var(--canvas-bg);
      color: var(--canvas-text);
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    body {{ padding: 24px; }}

    .workspace-shell {{
      display: grid;
      gap: 20px;
      max-width: 1400px;
      margin: 0 auto;
    }}

    .workspace-header {{
      display: grid;
      gap: 16px;
      padding: 28px;
      border: 1px solid var(--canvas-border);
      border-radius: 28px;
      background: var(--canvas-surface);
      box-shadow: var(--canvas-shadow);
    }}

    .workspace-eyebrow {{
      margin: 0;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--canvas-accent);
    }}

    .workspace-header h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.6rem);
      line-height: 0.95;
    }}

    .workspace-header p {{
      margin: 0;
      max-width: 70ch;
      color: var(--canvas-muted);
      font-size: 1rem;
      line-height: 1.65;
    }}

    .workspace-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }}

    .stat-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border: 1px solid var(--canvas-border);
      border-radius: 999px;
      background: var(--canvas-accent-soft);
      color: var(--canvas-accent);
      font-size: 13px;
      font-weight: 700;
    }}

    .workspace-grid {{
      display: grid;
      grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }}

    .sidebar,
    .content-card {{
      border: 1px solid var(--canvas-border);
      border-radius: 28px;
      background: var(--canvas-surface);
      box-shadow: var(--canvas-shadow);
    }}

    .sidebar {{
      position: sticky;
      top: 24px;
      display: grid;
      gap: 18px;
      padding: 22px;
    }}

    .sidebar-block {{
      display: grid;
      gap: 12px;
    }}

    .sidebar h2,
    .content-card h2 {{
      margin: 0;
      font-size: 0.92rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--canvas-muted);
    }}

    .toc-list {{
      display: grid;
      gap: 8px;
    }}

    .toc-link {{
      display: block;
      padding: 10px 12px;
      border-radius: 14px;
      background: transparent;
      color: var(--canvas-text);
      text-decoration: none;
      transition: background 0.18s ease, color 0.18s ease;
    }}

    .toc-link:hover,
    .toc-link:focus-visible {{
      background: var(--canvas-accent-soft);
      color: var(--canvas-accent);
      outline: none;
    }}

    .source-list {{
      display: grid;
      gap: 10px;
    }}

    .source-link {{
      display: grid;
      gap: 4px;
      padding: 12px 14px;
      border: 1px solid var(--canvas-border);
      border-radius: 16px;
      text-decoration: none;
      color: var(--canvas-text);
      background: rgba(255, 255, 255, 0.65);
    }}

    .source-link span {{
      color: var(--canvas-muted);
      font-size: 13px;
      word-break: break-word;
    }}

    .content-card {{ padding: 22px; }}

    .content-toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 18px;
    }}

    .search-input {{
      width: min(100%, 380px);
      min-height: 48px;
      padding: 0 16px;
      border: 1px solid var(--canvas-border);
      border-radius: 16px;
      background: rgba(255,255,255,0.86);
      color: var(--canvas-text);
      font-size: 15px;
      outline: none;
    }}

    .search-input:focus {{
      border-color: rgba(36, 95, 53, 0.36);
      box-shadow: 0 0 0 4px rgba(36, 95, 53, 0.08);
    }}

    .content-columns {{
      display: grid;
      gap: 16px;
    }}

    .section-card {{
      display: grid;
      gap: 14px;
      padding: 22px;
      border: 1px solid var(--canvas-border);
      border-radius: 22px;
      background: rgba(255,255,255,0.7);
    }}

    .section-card h3 {{
      margin: 0;
      font-size: 1.2rem;
      line-height: 1.25;
    }}

    .section-card p,
    .section-card li {{
      margin: 0;
      color: var(--canvas-muted);
      font-size: 0.98rem;
      line-height: 1.7;
    }}

    .section-card ul {{
      margin: 0;
      padding-left: 20px;
      display: grid;
      gap: 10px;
    }}

    .empty-state,
    .empty-note {{
      margin: 0;
      color: var(--canvas-muted);
      font-size: 14px;
      line-height: 1.6;
    }}

    .empty-state {{
      display: none;
      padding: 18px;
      border: 1px dashed var(--canvas-border);
      border-radius: 18px;
      background: rgba(255,255,255,0.65);
    }}

    @media (max-width: 980px) {{
      body {{ padding: 14px; }}
      .workspace-grid {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; }}
    }}

    @media (max-width: 640px) {{
      .workspace-header,
      .sidebar,
      .content-card,
      .section-card {{ border-radius: 22px; }}
      .workspace-header {{ padding: 22px 18px; }}
      .workspace-header h1 {{ font-size: clamp(1.8rem, 11vw, 2.6rem); }}
      .content-card,
      .sidebar {{ padding: 18px; }}
      .section-card {{ padding: 18px; }}
      .content-toolbar {{ align-items: stretch; }}
      .search-input {{ width: 100%; }}
    }}
  </style>
</head>
<body data-canvas-format="interactive">
  <main class="workspace-shell">
    <header class="workspace-header">
      <p class="workspace-eyebrow">DIU Workspace</p>
      <h1>{escape(title)}</h1>
      <p>{intro}</p>
      <div class="workspace-stats">
        <div class="stat-pill">Sections {len(sections)}</div>
        <div class="stat-pill">Sources {len(sources[:6])}</div>
        <div class="stat-pill">Responsive canvas</div>
      </div>
    </header>

    <div class="workspace-grid">
      <aside class="sidebar">
        <section class="sidebar-block">
          <h2>On this page</h2>
          <nav class="toc-list">{section_links}</nav>
        </section>

        <section class="sidebar-block">
          <h2>Sources</h2>
          <div class="source-list">{source_links}</div>
        </section>
      </aside>

      <section class="content-card">
        <div class="content-toolbar">
          <h2>Workspace content</h2>
          <input
            class="search-input"
            type="search"
            placeholder="Search this workspace"
            aria-label="Search this workspace"
            data-search
          />
        </div>
        <div class="content-columns" data-sections>{section_cards}</div>
        <p class="empty-state" data-empty-state>No matching section. Try another term.</p>
      </section>
    </div>
  </main>

  <script>
    const searchInput = document.querySelector('[data-search]');
    const sectionCards = Array.from(document.querySelectorAll('[data-section-card]'));
    const emptyState = document.querySelector('[data-empty-state]');

    function updateSearch() {{
      const query = (searchInput?.value || '').trim().toLowerCase();
      let visibleCount = 0;

      sectionCards.forEach((card) => {{
        const haystack = (card.dataset.search || '').toLowerCase();
        const isVisible = !query || haystack.includes(query);
        card.hidden = !isVisible;
        if (isVisible) visibleCount += 1;
      }});

      if (emptyState) {{
        emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
      }}
    }}

    searchInput?.addEventListener('input', updateSearch);
  </script>
</body>
</html>"""


def _extract_content_sections(content: str) -> list[dict[str, Any]]:
    lines = [line.rstrip() for line in str(content or "").splitlines()]
    sections: list[dict[str, Any]] = []
    current = {"title": "Overview", "paragraphs": [], "bullets": []}

    def flush_current() -> None:
        paragraphs = [paragraph for paragraph in current["paragraphs"] if paragraph]
        bullets = [bullet for bullet in current["bullets"] if bullet]
        if not paragraphs and not bullets:
            return
        sections.append(
            {
                "title": current["title"],
                "paragraphs": paragraphs,
                "bullets": bullets,
            }
        )

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        heading_match = re.match(r"^(?:#{1,6}\s+|\d+[.)]\s+)(.+)$", line)
        bullet_match = re.match(r"^[-*]\s+(.+)$", line)

        if heading_match:
            flush_current()
            current = {
                "title": _clean_canvas_title(heading_match.group(1)) or "Section",
                "paragraphs": [],
                "bullets": [],
            }
            continue

        if bullet_match:
            current["bullets"].append(bullet_match.group(1).strip())
            continue

        current["paragraphs"].append(line)

    flush_current()

    if sections:
        return sections

    clean_text = re.sub(r"\s+", " ", str(content or "")).strip()
    if not clean_text:
        return [{"title": "Overview", "paragraphs": ["No content available."], "bullets": []}]

    return [{"title": "Overview", "paragraphs": [clean_text], "bullets": []}]


def _render_canvas_section(section: dict[str, Any], index: int) -> str:
    paragraphs = "".join(
        f"<p>{escape(paragraph)}</p>"
        for paragraph in section.get("paragraphs", [])
    )
    bullets = "".join(
        f"<li>{escape(bullet)}</li>"
        for bullet in section.get("bullets", [])
    )
    bullet_list = f"<ul>{bullets}</ul>" if bullets else ""
    search_text = " ".join(
        [
            str(section.get("title") or ""),
            *section.get("paragraphs", []),
            *section.get("bullets", []),
        ]
    )

    return (
        f'<article class="section-card" id="section-{index}" '
        f'data-section-card data-search="{escape(search_text)}">'
        f"<h3>{escape(section.get('title') or f'Section {index}')}</h3>"
        f"{paragraphs}"
        f"{bullet_list}"
        "</article>"
    )


def _render_source_link(source: dict[str, Any]) -> str:
    title = str(source.get("title") or source.get("source") or "Source").strip()
    url = str(source.get("url") or "").strip()
    location = url or str(source.get("source") or "").strip()
    if url:
        return (
            f'<a class="source-link" href="{escape(url)}" target="_blank" rel="noreferrer">'
            f"<strong>{escape(title)}</strong>"
            f"<span>{escape(location)}</span>"
            "</a>"
        )
    if location:
        return (
            '<div class="source-link">'
            f"<strong>{escape(title)}</strong>"
            f"<span>{escape(location)}</span>"
            "</div>"
        )
    return ""


def _extract_canvas_intro(content: str) -> str:
    stripped = strip_canvas_code_blocks(content)
    # Remove markdown headings from the intro text
    stripped = re.sub(r"^#{1,6}\s+", "", stripped, flags=re.MULTILINE)

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", stripped)
        if sentence.strip()
    ]
    for sentence in sentences:
        if len(sentence) >= 24:
            return sentence[:220]
    return "Browse, search, and review the generated workspace content in one place."


def _extract_raw_html_document(text: str) -> str:
    doc_match = re.search(r"(?is)(<!doctype\s+html[\s\S]*?(?:</html>|$))", text)
    if doc_match:
        return doc_match.group(1).strip()

    html_match = re.search(r"(?is)(<html[\s\S]*?(?:</html>|$))", text)
    if html_match:
        return html_match.group(1).strip()

    return ""


def _extract_raw_html_fragment(text: str) -> str:
    lines = str(text or "").splitlines()
    start_index = next(
        (
            index
            for index, raw_line in enumerate(lines)
            if re.match(
                r"^\s*<(?:main|div|section|article|header|nav|aside|form|label|input|select|option|button|canvas|svg|style|script|p)\b",
                raw_line,
                re.IGNORECASE,
            )
        ),
        -1,
    )
    if start_index == -1:
        return ""

    fragment = "\n".join(lines[start_index:]).strip()
    return fragment if _looks_like_html_artifact(fragment) else ""


def _looks_like_html_artifact(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False

    lowered = value.lower()
    if "<!doctype" in lowered or "<html" in lowered or "<body" in lowered:
        return True

    tags = re.findall(r"</?([a-z][a-z0-9:-]*)\b[^>]*>", value, re.IGNORECASE)
    distinct_tags = {tag.lower() for tag in tags}
    container_tags = {
        "main",
        "div",
        "section",
        "article",
        "header",
        "nav",
        "aside",
        "form",
        "label",
        "input",
        "select",
        "option",
        "button",
        "canvas",
        "svg",
        "style",
        "script",
        "p",
        "h1",
        "h2",
        "h3",
    }
    meaningful_tag_count = sum(1 for tag in tags if tag.lower() in container_tags)
    return meaningful_tag_count >= 6 and len(distinct_tags.intersection(container_tags)) >= 3


def _extract_title_from_html(html: str) -> str:
    if not html:
        return ""

    for pattern in (
        r"(?is)<title[^>]*>(.*?)</title>",
        r"(?is)<h1[^>]*>(.*?)</h1>",
        r"(?is)<h2[^>]*>(.*?)</h2>",
    ):
        match = re.search(pattern, html)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", " ", match.group(1))
        title = re.sub(r"\s+", " ", title).strip()
        if title:
            return title[:88]
    return ""


def _clean_canvas_title(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    user_question_match = re.search(r"(?:^|\n)\s*User question:\s*([\s\S]+)$", text, re.IGNORECASE)
    if user_question_match:
        text = user_question_match.group(1).strip()

    text = re.sub(r"\[canvas force unlock\]", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(update canvas:\s*)+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"Use this selected text from the current conversation as the primary context for the user's question:", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(
        r"^generate an interactive visual version of our last discussion now\.?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(
        r"^based on the following content,\s*generate a visual html version now\.?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(
        r"^create a complete standalone website from the following content\.?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(r"^generating visual companion\.?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^here is your workspace\.?", "", text, flags=re.IGNORECASE).strip()
    text = text.rstrip("?.!").strip()

    generic_titles = {"", "visual version", "interactive version", "workspace", "canvas", "artifact"}
    if text.lower() in generic_titles:
        return ""

    return text[:88]


def _is_canvas_update_request(question: str) -> bool:
    normalized = str(question or "").lower()
    return "update canvas" in normalized or "update the current canvas artifact in place" in normalized
