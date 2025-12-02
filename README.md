# xfile_context

Cross-File Context Links MCP Server

## Development Setup

### Prerequisites

- Python 3.10 or higher (required for MCP SDK compatibility)

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

This project uses GitHub Actions for continuous integration. The following workflows run automatically on pull requests:

**Lightweight Checks** (`.github/workflows/lightweight-checks.yml`):
- **Triggers**: Runs on pull request creation/updates and pushes to feature branches
- **Jobs**:
  - Code formatting check (black, isort)
  - Linting (ruff)
  - Type checking (mypy)
  - Fast unit tests (pytest with `-m "not slow"`)
- **Purpose**: Provides fast feedback (<2 minutes) in the GitHub PR UI
- **Status**: Required check for PR merge

**Comprehensive Tests** (`.github/workflows/comprehensive-tests.yml`):
- **Triggers**: Runs on pull request creation/updates only
- **Matrix Strategy**: Tests across Python 3.10, 3.11, 3.12, and 3.13 on Ubuntu
- **Test Scope**: Full unit test suite + integration tests
- **Timeout**: <5 minutes per environment
- **Purpose**: Validates compatibility across all supported Python versions
- **Status**: Required check for PR merge

These workflows ensure code quality and compatibility before merging changes to the main branch.

## Usage

### Running the MCP Server

The Cross-File Context Links MCP Server provides automatic cross-file context injection for Python codebases. It integrates with Claude Code via the Model Context Protocol (MCP).

#### Standalone Mode

Run the MCP server directly:

```bash
python -m xfile_context.mcp_server
```

The server runs in stdio mode by default, which is compatible with Claude Code.

#### Programmatic Usage

Use the server in Python code:

```python
from xfile_context import CrossFileContextMCPServer

# Initialize with default configuration
server = CrossFileContextMCPServer()

# Run the server (stdio transport for Claude Code)
server.run(transport="stdio")
```

### MCP Tools

The server exposes two MCP tools:

#### 1. `read_with_context`

Reads a Python file with automatic cross-file context injection.

**Parameters:**
- `file_path` (str): Absolute or relative path to the Python file

**Returns:**
- `file_path`: The path that was read
- `content`: File content with injected context (formatted per TDD Section 3.8.3)
- `warnings`: List of any warnings (empty if none)

**Example:**
```python
# When called via MCP:
# Tool: read_with_context
# Args: {"file_path": "src/module.py"}
#
# Response includes:
# {
#   "file_path": "src/module.py",
#   "content": "[Cross-File Context]\n...\n---\n<file content>",
#   "warnings": []
# }
```

#### 2. `get_relationship_graph`

Exports the complete relationship graph for the codebase.

**Returns:**
- `nodes`: List of file nodes
- `relationships`: List of relationships between files
- `metadata`: Graph metadata (timestamp, counts)

**Example:**
```python
# When called via MCP:
# Tool: get_relationship_graph
# Args: {}
#
# Response includes:
# {
#   "nodes": [...],
#   "relationships": [...],
#   "metadata": {...}
# }
```

### Configuration

Create a `.cross_file_context_links.yml` file in your project root to customize behavior:

```yaml
# Cache configuration
cache_expiry_minutes: 10
cache_size_limit_kb: 50

# Context injection
context_token_limit: 500
enable_context_injection: true

# Warnings
warn_on_wildcards: false
suppress_warnings: []
function_usage_warning_threshold: 3

# Metrics and logging
enable_injection_logging: true
enable_warning_logging: true
metrics_anonymize_paths: false
```

See TDD Section 3.10.4 for full configuration reference.

### Branch Protection

The main branch is protected with rules enforced via GitHub API. To configure or update branch protection rules:

```bash
./scripts/setup_branch_protection.sh
```

**Prerequisites**: Requires `gh` CLI installed and authenticated with repository admin permissions.

**Protection Rules**:
- Pull requests required (no direct commits)
- Approvals: 0 required (suitable for solo development)
- All 9 CI checks must pass (lightweight + comprehensive)
- Branches must be up-to-date before merging
- Rules enforced for administrators

## License

Copyright (c) 2025 Henru Wang. All rights reserved.

This is proprietary software. See [LICENSE](./LICENSE) for details.
