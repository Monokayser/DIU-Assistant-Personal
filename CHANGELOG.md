# Changelog: DIU Assistant

All notable changes to the DIU Assistant project will be documented in this file.

## [1.2.1] - 2026-04-28
### Changed
- **Repository Hygiene**: Removed stale bridge experiments and an unused backend placeholder module.
- **Project Docs**: Updated the repository map and deployment notes so the documented structure matches the actual Group 1 codebase.
- **Workspace Cleanup**: Standardized generated-directory guidance for `frontend/dist/`, `output/`, and `tmp/`.

## [1.2.0] - 2026-04-27
### Added
- **Visual RAG Integration**: Added a side-by-side document viewer in the Canvas for PDF sources.
- **Premium Animations**: Integrated `framer-motion` for spring-based transitions and staggered message entry.
- **TopBar Component**: Extracted a modular header with theme and mode toggles.
- **Composer Component**: Refactored the input area into a dedicated component with file and voice support.
- **AppShell**: Created a layout wrapper for global overlays and workspace management.

### Changed
- **Gemini Unification**: Standardized all AI calls (Chat, RAG, Transcribe) to use `gemini-3-flash-preview`.
- **Architectural Refactor**: Broke down the 1300-line `App.jsx` into modular components and the `useAssistant` hook.
- **Model Parameters**: Updated `temperature` and `maxOutputTokens` for better stability in Canvas mode.
- **Thinking Budget**: Enabled `thinkingConfig` for reasoning models in artifact generation.

### Fixed
- **Typography Fix**: Resolved "symbol text" issues by integrating Google Variable Fonts (Inter & Outfit) for 1:1 design fidelity.
- **Mobile Canvas Overhaul**: Migrated from "new tab" artifacts to a native full-screen overlay with spring-motion transitions and a dedicated close button.
- **Crash Fix**: Resolved scope issues in the `App` component that prevented startup in certain conditions.
- **Responsive Alignment**: Fine-tuned header and controls for high-precision rendering on small screens.

## [1.1.0] - 2026-04-26
### Added
- Multi-Agent Orchestration via CrewAI.
- Specialized Admission, Scholarship, and Course Advisor agents.
- Interactive Canvas for real-time HTML artifact rendering.

### Changed
- Migrated vector storage to Supabase/ChromaDB.
- Enhanced RAG pipeline with recursive chunking.

---
*© 2026 Daffodil International University | Group-Gamma*
