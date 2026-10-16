# Agent Guidelines

- **Context & Architecture:** Always reference [DESIGN.md](DESIGN.md) for architectural patterns, tech stack choices, and project conventions.
- **Strict Scope:** Touch only files directly relevant to the current task. Do not refactor unrelated code, add unsolicited features, or reformat untouched files.
- **YAGNI & Simplicity:** Write minimal, maintainable code that solves the immediate problem. Avoid speculative abstractions, premature generic patterns, or over-engineering for hypothetical future needs.
- **Execution Workflow:**
  - **Multi-file changes / New architectural components:** Outline a concise plan and wait for confirmation before generating implementation code.
  - **Local fixes / Isolated UI tweaks:** Diagnose the root cause and execute changes directly.
- **Dependencies:** Inspect dependency manifests (e.g., `pyproject.toml`, `package.json`) to verify existing packages.
