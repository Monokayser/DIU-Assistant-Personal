from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.apps.canvas.services.artifacts import (
    build_canvas_reply_text,
    create_canvas_artifacts,
    resolve_artifact_path,
    should_create_canvas_artifacts,
    strip_canvas_code_blocks,
)


class CanvasArtifactTests(unittest.TestCase):
    def test_canvas_artifacts_require_explicit_canvas_request_for_agent_chat(self) -> None:
        self.assertFalse(
            should_create_canvas_artifacts(
                "Answer in DIU Admission Mode.\n\nUser question: What is the admission deadline?",
                "The admission deadline depends on the intake.",
            )
        )
        self.assertTrue(
            should_create_canvas_artifacts(
                "Answer in DIU Admission Mode.\n\nUser question: Generate an interactive visual version of our last discussion now. [canvas force unlock]",
                "Here is the canvas plan.",
            )
        )

    def test_explicit_canvas_request_builds_interactive_canvas_without_specialist_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = create_canvas_artifacts(
                Path(temp_dir),
                session_id="explicit-canvas-session",
                question="AGENT ROLE: ADMISSION SPECIALIST.\n\nUser question: Generate an interactive visual version of our last discussion now. [canvas force unlock]",
                answer="Admission guidance summary",
                sources=[],
            )

            html_path = resolve_artifact_path(Path(temp_dir), "explicit-canvas-session", artifacts[0]["id"])
            self.assertIsNotNone(html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("Workspace content", html)
            self.assertIn("Search this workspace", html)
            self.assertIn('data-canvas-format="interactive"', html)

    def test_create_canvas_artifacts_writes_editable_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = create_canvas_artifacts(
                Path(temp_dir),
                session_id="demo-session",
                question="Write a DIU admission document pack",
                answer="## Checklist\n\n- Academic transcripts\n- Passport copy",
                sources=[
                    {
                        "title": "Admission",
                        "url": "https://daffodilvarsity.edu.bd/admission",
                        "source": None,
                    }
                ],
            )

            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0]["mime_type"], "text/html")

            html_path = resolve_artifact_path(Path(temp_dir), "demo-session", artifacts[0]["id"])
            self.assertIsNotNone(html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("Editable Canvas document", html)
            self.assertIn('contenteditable="true"', html)
            self.assertNotIn("<strong>Prompt:</strong>", html)
            self.assertIn("Prepared for: Write a DIU admission document pack", html)

    def test_specialist_mode_defaults_to_interactive_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = create_canvas_artifacts(
                Path(temp_dir),
                session_id="interactive-session",
                question=(
                    "Answer in DIU Admission Mode. Focus on DIU admission eligibility.\n\n"
                    "User question: How can I apply for admission?"
                ),
                answer=(
                    "## Eligibility\n\n"
                    "You need to meet the basic GPA requirement before applying.\n\n"
                    "## Core steps\n\n"
                    "- Collect SSC and HSC transcripts\n"
                    "- Fill in the online application form\n"
                    "- Prepare recent passport-sized photos"
                ),
                sources=[],
            )

            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0]["mime_type"], "text/html")

            html_path = resolve_artifact_path(Path(temp_dir), "interactive-session", artifacts[0]["id"])
            self.assertIsNotNone(html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("Workspace content", html)
            self.assertIn("Search this workspace", html)
            self.assertIn("On this page", html)
            self.assertNotIn("Editable Canvas document", html)
            self.assertNotIn('contenteditable="true"', html)

    def test_resolve_artifact_path_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertIsNone(resolve_artifact_path(Path(temp_dir), "demo-session", "../report.pdf"))

    def test_create_canvas_artifacts_uses_model_html_when_present(self) -> None:
        answer = """I built the calculator.

```html
<main><h1>DIU Waiver Calculator</h1><script>window.ready = true;</script></main>
```
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = create_canvas_artifacts(
                Path(temp_dir),
                session_id="canvas-session",
                question="Build a DIU waiver calculator",
                answer=answer,
                sources=[],
            )

            html_path = resolve_artifact_path(Path(temp_dir), "canvas-session", artifacts[0]["id"])
            self.assertIsNotNone(html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("DIU Waiver Calculator", html)
            self.assertIn("<!doctype html>", html)
            self.assertEqual(strip_canvas_code_blocks(answer), "I built the calculator.")

    def test_create_canvas_artifacts_can_require_model_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = create_canvas_artifacts(
                Path(temp_dir),
                session_id="html-required-session",
                question="Create a complete standalone website. [canvas force unlock]",
                answer="This is only a prose answer, not HTML.",
                sources=[],
                require_model_html=True,
            )

            self.assertEqual(artifacts, [])

    def test_create_canvas_artifacts_uses_raw_html_fragments_without_placeholder_fallback(self) -> None:
        answer = """Here is the requested workspace.

<div class="planner">
  <section><h1>DIU Academic Planner</h1><p>Plan credits by semester.</p></section>
  <section><button>Generate</button><label>Stream</label><select><option>CSE</option></select></section>
</div>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = create_canvas_artifacts(
                Path(temp_dir),
                session_id="raw-fragment-session",
                question="Generate an interactive visual version of our last discussion now. [canvas force unlock]",
                answer=answer,
                sources=[],
            )

            html_path = resolve_artifact_path(Path(temp_dir), "raw-fragment-session", artifacts[0]["id"])
            self.assertIsNotNone(html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("DIU Academic Planner", html)
            self.assertNotIn("Workspace content", html)
            self.assertEqual(build_canvas_reply_text("Generate canvas", answer), "Here is the requested workspace.")



    def test_canvas_artifacts_strip_mode_wrapper_from_document_titles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = create_canvas_artifacts(
                Path(temp_dir),
                session_id="mode-wrap-session",
                question=(
                    "Answer in DIU Admission Mode. Focus on DIU admission eligibility.\n\n"
                    "User question: Update canvas: How can I apply for admission?"
                ),
                answer="## Steps\n\n- Fill out the application form",
                sources=[],
            )

            html_path = resolve_artifact_path(Path(temp_dir), "mode-wrap-session", artifacts[0]["id"])
            self.assertIsNotNone(html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("How can I apply for admission", html)
            self.assertNotIn("Answer in DIU Admission Mode", html)
            self.assertNotIn("Update canvas: Update canvas", html)

    def test_build_canvas_reply_text_falls_back_to_short_workspace_acknowledgement(self) -> None:
        answer = """```html
<!doctype html>
<html><body><main><h1>Planner</h1></main></body></html>
```"""
        message = build_canvas_reply_text(
            "Generate an interactive visual version of our last discussion now. [canvas force unlock]",
            answer,
        )
        self.assertEqual(message, "Here is your workspace. Open the canvas to explore it.")


if __name__ == "__main__":
    unittest.main()
