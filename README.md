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
python -m xfile_context
```

The server runs in stdio mode by default, which is compatible with Claude Code.

#### MCP Inspector (Development)

For development and debugging, you can use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to interactively test the server's tools. This requires:

1. The `mcp[cli]` package:
```bash
pip install "mcp[cli]"
```

2. The `uv` package manager (used internally by `mcp dev`):
```bash
pip install uv
```

Start the MCP Inspector from the repository root. If you're using `virtualenvwrapper` or another tool that manages virtual environments outside of `.venv/`, set `UV_PROJECT_ENVIRONMENT` to point to your active virtual environment:

```bash
# If using virtualenvwrapper or similar (VIRTUAL_ENV is set)
UV_PROJECT_ENVIRONMENT=${VIRTUAL_ENV} mcp dev src/xfile_context/dev_server.py:mcp

# If using the default .venv/ directory
mcp dev src/xfile_context/dev_server.py:mcp
```

Once started, open http://localhost:6274 in your browser to access the inspector interface. From there you can:
- View available tools and their schemas
- Invoke tools interactively with custom arguments
- Inspect tool responses

**Note**: The `mcp dev` command may create a `uv.lock` file. This file is ignored by version control and can be safely deleted.

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
- `content`: File content with injected context (prefixed with `[Cross-File Context]` section)
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

All configuration options are shown above with their default values. Set `enable_context_injection: false` to disable context injection entirely.

## Quick Start Guide

Get cross-file context injection working in 5 minutes.

### 1. Install the MCP Server

```bash
# Clone and install
git clone <repository-url>
cd xfile_context
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Configure Claude Code

Add to your Claude Code MCP configuration (`~/.config/claude-code/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "xfile_context": {
      "command": "/path/to/xfile_context/venv/bin/python",
      "args": ["-m", "xfile_context"]
    }
  }
}
```

### 3. Start Using Context-Aware Reads

In Claude Code, instead of using the standard `Read` tool, you can now use `read_with_context` to get automatic cross-file context:

```
Tool: read_with_context
Args: {"file_path": "src/services/user_service.py"}
```

The response will include:
- Injected context from related files (imports, callers)
- The file content itself
- Any relevant warnings

### 4. (Optional) Customize Configuration

Create `.cross_file_context_links.yml` in your project root:

```yaml
# Suppress warnings for test files
suppress_warnings:
  - "tests/**/*"

# Enable wildcard import warnings
warn_on_wildcards: true
```

## Known Issues and Limitations

### Language Support

- **Python only**: Only `.py` files are analyzed. Other languages are skipped silently.
- **Future versions**: Multi-language support planned.

### Static Analysis Limitations

The analyzer uses AST (Abstract Syntax Tree) parsing and cannot track runtime-determined relationships:

| Pattern | Status | Description |
|---------|--------|-------------|
| Regular imports | Supported | `import foo`, `from foo import bar` |
| Aliased imports | Supported | `import foo as f`, `from foo import bar as b` |
| Conditional imports | Supported | `if TYPE_CHECKING: import typing` |
| Wildcard imports | Partial | Module-level only; function-level tracking unavailable |
| Circular dependencies | Supported | Detected without crash |
| Dynamic imports | **Untracked** | `importlib.import_module(name)` - warning emitted |
| Dynamic dispatch | **Untracked** | `getattr(obj, name)()` - warning emitted |
| Monkey patching | **Untracked** | `module.attr = replacement` - warning emitted (source modules only) |
| exec/eval | **Untracked** | `exec()`, `eval()` - warning emitted |
| Metaclasses | Partial | Class definition tracked; metaclass logic not analyzed |
| Complex decorators | Partial | Decorated functions tracked; decorator behavior not analyzed |

### Memory and Performance

- **In-memory only**: Relationship graph is not persisted across sessions. Each session starts fresh.
- **Large files**: Files >10,000 lines are skipped and logged as warnings.
- **Cache size**: Default 50KB limit with LRU eviction. Configurable via `cache_size_limit_kb`.

### Features Not Yet Implemented

- Cross-session state sharing
- Relationship graph persistence
- Multi-language support
- Semantic code search
- IDE integrations beyond Claude Code

## Troubleshooting

### Common Issues

#### MCP Server Won't Start

**Symptom**: Error when launching the MCP server.

**Solutions**:
1. Verify Python version: `python3 --version` (requires 3.10+)
2. Check installation: `pip show xfile_context`
3. Verify virtual environment is activated: `which python` should point to venv

```bash
# Reinstall if needed
pip install -e ".[dev]"
```

#### No Context Being Injected

**Symptom**: `read_with_context` returns file content without `[Cross-File Context]` section.

**Possible causes**:
1. **No relationships detected**: The file has no imports or isn't imported by other files
2. **File not indexed yet**: Use `get_relationship_graph` to trigger indexing
3. **Non-Python file**: Only `.py` files receive context injection

**Debug steps**:
1. Use the `get_relationship_graph` MCP tool to see all detected relationships
2. Verify the file has imports or is imported by other files
3. Check if the file is a `.py` file (other extensions are not analyzed)

#### Warnings Not Appearing

**Symptom**: Expected dynamic pattern warnings are not shown.

**Possible causes**:
1. **Test module suppression**: Warnings for dynamic patterns are automatically suppressed in test files (matching `test_*.py`, `*_test.py`, `tests/**/*.py`, or `conftest.py`)
2. **Warning suppression config**: Check `.cross_file_context_links.yml` for `suppress_warnings` entries
3. **Pattern type suppression**: Check for `suppress_dynamic_dispatch_warnings: true` or similar

#### Performance Issues

**Symptom**: Slow response times or high memory usage.

**Solutions**:
1. **Reduce cache size**: Lower `cache_size_limit_kb` in config
2. **Check file count**: Very large codebases (>1000 files) may be slow on initial indexing
3. **Large files**: Files >10,000 lines are skipped automatically

### Debug Tips

#### Enable Verbose Logging

Check the MCP server logs for detailed diagnostics. Logs are written to:
- **Injection logs**: `.xfile_context/injection_log.jsonl` in your project directory
- **Warning logs**: `.xfile_context/warning_log.jsonl` in your project directory
- **Session metrics**: `.xfile_context/session_metrics.jsonl` (written at session end)

#### Check Session Metrics

After a session, review the metrics file for insights:
- Cache hit/miss rates
- Parsing times
- Warning counts by type
- Files with most dependencies

#### Validate Configuration

Ensure `.cross_file_context_links.yml` is valid YAML:

```bash
python -c "import yaml; yaml.safe_load(open('.cross_file_context_links.yml'))"
```

### How to Report Bugs

1. **Check existing issues**: [GitHub Issues](https://github.com/jiggloo/xfile_context/issues)

2. **Gather information**:
   - Python version: `python3 --version`
   - OS: `uname -a` (Linux/macOS) or `ver` (Windows)
   - Error messages (full stack trace if available)
   - Minimal reproduction steps

3. **Create a new issue**: Include:
   - Clear title describing the problem
   - Steps to reproduce
   - Expected vs. actual behavior
   - Environment details
   - Relevant configuration (`.cross_file_context_links.yml`)

4. **Sensitive information**: Do not include:
   - API keys or credentials
   - Proprietary code snippets
   - Personal information

### Error Message Reference

| Error | Cause | Solution |
|-------|-------|----------|
| `FileNotFoundError` | File path doesn't exist | Verify path is correct and file exists |
| `UnicodeDecodeError` | Non-UTF-8 file encoding | Ensure files are UTF-8 encoded |
| `SyntaxError in AST parse` | Invalid Python syntax in file | Fix syntax errors in the source file |
| `MemoryError` | Cache or graph too large | Reduce `cache_size_limit_kb` |
| `TimeoutError` | Parsing took too long | Check for very large files; consider exclusions |

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
