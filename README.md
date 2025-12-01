# xfile_context

Cross-File Context Links MCP Server

## Development Setup

### Prerequisites

- Python 3.8 or higher

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd xfile_context
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package with development dependencies:
```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks:
```bash
pre-commit install
```

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality. The hooks will automatically run before each commit and include:

- **black**: Code formatter (line length 100)
- **isort**: Import statement organizer
- **ruff**: Fast Python linter
- **mypy**: Static type checker (strict mode for src/, lenient for tests/)
- **pytest**: Fast unit tests only (excludes tests marked with `@pytest.mark.slow`)

To manually run all hooks on all files:
```bash
pre-commit run --all-files
```

To bypass hooks for a specific commit (not recommended):
```bash
git commit --no-verify
```

### GitHub Actions

This project uses GitHub Actions for continuous integration. The following workflow runs automatically on pull requests and feature branches:

**Lightweight Checks** (`.github/workflows/lightweight-checks.yml`):
- **Triggers**: Runs on pull request creation/updates and pushes to feature branches
- **Jobs**:
  - Code formatting check (black, isort)
  - Linting (ruff)
  - Type checking (mypy)
  - Fast unit tests (pytest with `-m "not slow"`)
- **Purpose**: Provides fast feedback (<2 minutes) in the GitHub PR UI
- **Status**: Required check for PR merge

The workflow mirrors the local pre-commit hooks to ensure consistency between local development and CI/CD.

## License

Copyright (c) 2025 Henru Wang. All rights reserved.

This is proprietary software. See [LICENSE](./LICENSE) for details.
