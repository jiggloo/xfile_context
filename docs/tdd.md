# Technical Design Document: Cross-File Context Links

**Project**: Cross-File Context Links MCP Server
**Version**: 0.1.0 (Python support only)
**Status**: Draft
**Last Updated**: 2025-11-24
**Related Documents**:
- PRD: [prd.md](./prd.md)
- Edge Cases: [prd_edge_cases.md](./prd_edge_cases.md)
- Testing Plan: [prd_testing.md](./prd_testing.md)
- Open Questions: [prd_open_questions.md](./prd_open_questions.md)
- Design Decisions: [design_decisions.md](./design_decisions.md)

---

## Quick Reference: Document Identifiers

**Document Identifiers:**
- **FR-#**: Functional Requirement (defined in prd.md Section 4.1)
- **NFR-#**: Non-Functional Requirement (defined in prd.md Section 4.2)
- **EC-#**: Edge Case (defined in prd_edge_cases.md Section 6)
- **DD-#**: Design Decision (defined in design_decisions.md)
- **T-#.#**: Test Case (defined in prd_testing.md Section 8)
- **Q-#**: Open Question (defined in this TDD Section 5)
- **TODO-#**: Action Item (defined in this TDD Section 5)
- **G-#**: Implementation Gap (defined in this TDD Section 6)
- **LIMITATION-#**: Known System Limitation (defined in this TDD Section 5.7)
- **RISK-#**: Project Risk (defined in this TDD Section 5.8)
- **Task #.#**: Development Phase Task (defined in this TDD Section 3.14)

**System Components:**
- **Relationship Graph**: In-memory data structure tracking cross-file dependencies (Section 3.3.2, Section 3.5)
- **Working Memory Cache**: LRU cache storing recently-read file snippets (Section 3.3.3, Section 3.4.6)
- **Detector**: Language-specific plugin for AST parsing and relationship extraction (Section 3.4.1)
- **Context Injection**: Process of augmenting Read tool with cross-file context (Section 3.4.7)

**Domain Terms:**
- **Cross-File Context**: Information about how a file relates to other files in the codebase
- **Context Links**: Relationships between files (imports, function calls, etc.)
- **Incremental Update**: Re-analyzing only changed files, not entire codebase
- **Fail-Safe Principle**: "No incorrect context is better than wrong context" (FR-42)

---

## Table of Contents

1. [Constraints](#1-constraints)
2. [Requirements](#2-requirements)
3. [Proposed Solution](#3-proposed-solution)
   - 3.1 [High-Level Architecture](#31-high-level-architecture)
   - 3.2 [Key Design Decisions](#32-key-design-decisions)
   - 3.3 [Data Models](#33-data-models)
   - 3.4 [Component Design](#34-component-design)
   - 3.5 [Relationship Detection](#35-relationship-detection)
   - 3.6 [File Watcher and Change Detection](#36-file-watcher-and-change-detection)
   - 3.7 [Working Memory Cache](#37-working-memory-cache)
   - 3.8 [Context Injection](#38-context-injection)
   - 3.9 [Warning System](#39-warning-system)
   - 3.10 [Metrics and Logging](#310-metrics-and-logging)
   - 3.11 [Error Handling](#311-error-handling)
   - 3.12 [Security & Compliance](#312-security--compliance)
   - 3.13 [Testing Strategy](#313-testing-strategy)
   - 3.14 [Development Plan](#314-development-plan)
4. [Alternatives Considered](#4-alternatives-considered)
5. [Open Questions & TODOs](#5-open-questions--todos)
6. [Gaps Discovered During Implementation](#6-gaps-discovered-during-implementation)

---

## 1. Constraints

### 1.1 Technical Constraints

**Python Version:**
- Target runtime: Python 3.8+ (standard for modern development environments)
- Rationale: Balance between modern features and broad compatibility

**MCP Protocol Integration:**
- MUST integrate with Model Context Protocol (MCP) architecture used by Claude Code
- MUST implement as MCP server exposing tools/resources
- MUST respect Claude Code's tool architecture and conventions
- MUST NOT conflict with other MCP servers (see NFR-14)

**Language Support Scope:**
- Version 0.1.0: **Python only** (`.py` files)
- Rationale: Validate core mechanism before multi-language expansion
- See PRD Section 2.3 (Language Support Roadmap) for future language priorities:
  - v0.2.0: Terraform
  - v0.3.0: TypeScript/JavaScript
  - v0.4.0: Go

**Static Analysis Limitations:**
- Can only analyze code patterns detectable through AST (Abstract Syntax Tree) parsing
- Cannot track runtime-determined relationships (dynamic imports, getattr, exec/eval)
- See prd_edge_cases.md EC-6 through EC-10 for unhandled dynamic patterns
- Fail-safe principle (FR-42): When pattern is undetectable, emit warning but do NOT track incorrectly

**Privacy Requirements:**
- MUST operate entirely locally - no cloud dependencies for core functionality (NFR-5)
- MUST NOT transmit file contents to external servers (NFR-6)
- All processing happens on user's machine

**Project Structure Assumptions:**
- Standard Python project layouts (src/, tests/, etc.)
- Git repositories with .gitignore
- Dependency directories exist (node_modules, .venv, __pycache__)
- MUST respect .gitignore patterns for indexing (NFR-7)
- MUST NOT index dependency directories (NFR-8)

**Code Quality Assumptions:**
- The system assumes **well-linted Python code** for correct function resolution
- Specifically, code should not have linting errors that affect name resolution:
  - **No name shadowing**: Multiple imports with same name (flake8 F811)
  - **No import shadowing**: Local definitions shadowing imports (flake8 F811)
  - **No duplicate definitions**: Same function/class defined multiple times
- **Rationale**: It is not reasonable for an MVP to handle all edge cases of poorly-maintained code
- **Recommendation**: Users should use flake8, ruff, or equivalent linters
- **Behavior with unlinted code**: System uses Python semantics (last definition wins), which may produce incorrect relationship tracking if shadowing exists

### 1.2 Performance Constraints

**Indexing Performance:**
- Initial indexing of 100 files (<5,000 lines each): <10 seconds (see prd_testing.md T-7.1)
- Initial indexing of 1,000 files: <2 minutes (T-7.2)
- Incremental update per file edit: <200ms (T-7.3, NFR-1)
- MUST NOT significantly slow down file access operations

**Runtime Performance:**
- Context injection latency: <50ms per Read operation (T-8.1, NFR-2)
- Cache lookup: <10ms (T-8.2)
- Relationship detection: <200ms for files <5,000 lines (NFR-1)

**Memory Constraints:**
- Relationship graph: <500MB for 10,000 files (NFR-4, T-7.4)
- Working memory cache: configurable size limit, default 50KB per session (FR-16)
- Total system memory footprint: <500MB sustained

**Scalability Targets:**
- SHOULD handle codebases up to 10,000 files (NFR-3)
- Files >10,000 lines: skipped with warning (EC-17)
- Long-running sessions (8+ hours): implement rolling window (EC-16)

### 1.3 User Experience Constraints

**Zero-Configuration Design:**
- MUST work without manual setup for standard project layouts (NFR-9)
- Auto-detect project structure (Python packages, test directories)
- Use sane defaults for all configuration parameters

**Non-Intrusive Behavior:**
- Context injection: No limit in v0.1.0 (FR-10), metrics-driven approach
- MUST NOT clutter agent responses with excessive context
- MUST allow users to disable context injection (FR-12)
- Track token counts to determine if limits needed (data-driven)

**Graceful Degradation:**
- MUST continue operating when:
  - Some files cannot be parsed (EC-18)
  - Cache is full (EC-15)
  - File watcher fails
- Prioritize: No incorrect context > No context at all (FR-42)

**User Control:**
- Configuration file support: `.cross_file_context_links.yml` (FR-39)
- Adjustable parameters (FR-49):
  - Cache size limit (default: 50KB)
  - Token injection limit (default: 500 tokens)
  - AST parsing timeout (default: 5 seconds)
  - AST recursion depth limit (default: 100 levels)
  - Warning suppression

### 1.4 Compatibility Constraints

**Claude Code Integration:**
- MUST integrate with existing Read/Edit/Write tools (NFR-14)
- MUST NOT interrupt existing user workflows
- Context injection MUST be inline during Read tool execution (DD-5)

**File System Compatibility:**
- Support local codebases (no cloud requirement)
- Handle case-sensitive and case-insensitive file systems
- Support symbolic links (with cycle detection and security validation - see Section 3.12.2)
- Support standard ignore patterns (.gitignore, .mcpignore)

**Concurrent Modification:**
- File watcher MUST detect external edits (EC-11, EC-20)
- Cache invalidation MUST happen on file modification (FR-15)
- Handle concurrent file modifications gracefully

**Incremental Indexing:**
- MUST NOT require full codebase re-scan on every change (NFR-15)
- Incremental updates when files are edited (FR-5)
- Support partial graph (incomplete by design per PRD Section 3.4.2)

### 1.5 Development and Testing Constraints

**Test Environment:**
- Representative test codebase: 50-100 Python files (see prd_testing.md Section 8.1)
- Known cross-file dependencies documented in test fixtures
- Edge case coverage (circular dependencies, dynamic imports, etc.)

**Development Timeline:**
- 6-week development cycle (see Section 3.14 Development Plan, to be filled)
- UAT phases: Alpha (Week 1), Beta (Weeks 2-3), Pilot (Week 4)

**Success Criteria:**
- Primary metric: Reduce file re-read rate from 87.5% to <30% (see PRD Section 5.1)
- No critical bugs during UAT
- <5% user opt-out rate

**Third-Party Dependency Licensing:**

This project uses a **proprietary license**, which imposes constraints on third-party dependencies:

- **Permissible licenses** (compatible with proprietary code):
  - MIT License (e.g., tiktoken) ✅
  - BSD License (2-Clause, 3-Clause)
  - Apache License 2.0
  - ISC License
  - Python Software Foundation License

- **Prohibited licenses** (incompatible with proprietary code):
  - GPL (v2, v3) - Copyleft requires source distribution ❌
  - AGPL (v3) - Copyleft with network provision requirement ❌
  - LGPL - Requires dynamic linking or providing object files ❌

- **License verification requirement**:
  - All third-party dependencies MUST be verified for license compatibility before inclusion
  - Use automated license checking tools (e.g., `pip-licenses`, `licensecheck`)
  - Document dependency licenses in development workflow (see Section 3.14)
  - Fail CI/CD builds if prohibited licenses detected

- **Rationale**: Proprietary license allows commercial use without requiring source distribution, but copyleft licenses would force open-sourcing the entire codebase

### 1.6 Architectural Constraints (from Design Decisions)

**Modular Design (DD-1):**
- Detector plugin pattern for relationship detection
- Allow incremental complexity: v0.1.0 (simple calls), v0.1.1 (method chains), v0.1.2 (nested attributes)

**Language-Agnostic Foundation (DD-2):**
- Three-layer architecture: File Watcher → Language Analyzers → Detectors
- v0.1.0 has only Python analyzer, but architecture supports multi-language expansion

**Serializable Structures (DD-4):**
- All data models MUST be serializable (JSON-compatible primitives)
- No complex objects (ast.AST nodes) in stored structures
- Enables future v0.2.0 persistence and state sharing

**Layer Separation (DD-6):**
- MCP Protocol Layer → Business Logic Layer → Storage Layer
- Business logic has no MCP dependencies
- Enables v0.2.0 evolution to thin MCP + backend service architecture

### 1.7 Out of Scope for V0.1.0

**Not Implemented:**
- Multi-language support (deferred to v0.2.0+)
- Relationship graph persistence across restarts (FR-22: in-memory only)
- State sharing between parent/subagent sessions (deferred to v0.2.0 per PRD Section 3.4)
- Semantic similarity / embeddings (structural analysis only)
- IDE-like refactoring tools
- Cross-repository dependency tracking

**Explicitly Deferred:**
- Custom ignore patterns (DD-2: low priority, add later)
- Edit-time context injection warnings (DD-5: completeness subagent handles breaking changes)
- Advanced metrics visualization UI (logs are machine-readable, tools can be built later)

---

## 2. Requirements

**Note on RFC 2119 Keywords:** The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", and "MAY" in this section are to be interpreted as described in RFC 2119.

**Note on PRD-TDD Requirement Relationship:**

This TDD's requirements are derived from the PRD (`docs/prd.md`) but reflect **v0.1.0 implementation decisions** made during technical design:

- **PRD**: Documents product vision and ideal requirements
- **TDD**: Documents what will actually be implemented in v0.1.0, including:
  - **Deferred requirements**: Some PRD requirements postponed to v0.1.1+ (e.g., FR-6, FR-7 circular dependency detection)
  - **Removed requirements**: Some PRD requirements eliminated based on technical analysis (e.g., FR-14 time-based cache expiry)
  - **Modified requirements**: Some PRD requirements adapted based on design insights (e.g., FR-10 changed to metrics-driven approach)

**Requirement numbering** (FR-1, FR-2, etc.) is preserved from the PRD for traceability, even when requirements are deferred or modified.

**Gaps discovered during TDD development** are documented in:
- **PRD Section 10**: "Gaps Discovered During Implementation" - lists all deviations with rationale and TDD cross-references
- **This TDD**: Individual requirement entries show deferral/removal status with inline notes

**Why requirements diverge:**
- Technical design revealed simpler/better approaches (e.g., staleness detection vs time-based expiry)
- Analysis showed some requirements unnecessary for v0.1.0 (e.g., cycle detection when no deep traversals exist)
- Data-driven approach preferred over fixed limits (e.g., no initial token limit, gather metrics first)

**For traceability**: Each modified requirement includes:
- Strikethrough of original text (e.g., ~~MUST handle circular dependencies~~)
- **Status marker** (e.g., **DEFERRED to v0.1.1+** or **REMOVED**)
- Rationale and TDD section references

### 2.1 Functional Requirements

#### 2.1.1 Relationship Detection (FR-1 through FR-7)

**Python Import Detection:**
- **FR-1**: The system MUST detect `import` and `from...import` statements in Python files (.py)
  - Example: `import os`, `from typing import List`
  - Include handling for aliased imports (see FR-3)

- **FR-2**: The system MUST detect function call relationships within the same Python codebase
  - Example: `file_a.py` calls `retry_with_backoff()` defined in `retry.py`
  - v0.1.0: Simple function calls only (per DD-1)
  - v0.1.1+: Method chains, nested attributes

- **FR-3**: The system SHOULD detect class inheritance relationships in Python
  - Example: `class Foo(Bar):` creates relationship from Foo to Bar
  - Track base class references

- **FR-4**: The system SHOULD detect module-level dependencies in Python
  - Example: Wildcard imports `from utils import *` (see EC-4)
  - Track at module level when function-level tracking unavailable

**Graph Maintenance:**
- **FR-5**: The system MUST update relationship graph when Python files are edited
  - Incremental update, not full re-scan
  - Invalidate stale relationships for modified file
  - Re-analyze modified file and update graph

- **FR-6**: ~~The system MUST handle circular dependencies without infinite loops~~ **DEFERRED to v0.1.1+**
  - **Rationale for deferral**: All graph operations (get_dependencies, get_dependents) use O(1) bidirectional index lookups - no deep traversals that could cause infinite loops
  - Cycle detection would be the ONLY deep traversal operation in the system
  - The cost (DFS after every import during indexing) outweighs benefit (code quality warning)
  - See Section 3.5.5 for detailed analysis

- **FR-7**: ~~The system MUST warn users when circular import dependencies are detected in Python code~~ **DEFERRED to v0.1.1+**
  - Deferred with FR-6 as they are coupled requirements
  - Nice-to-have feature for code quality but not essential for core functionality
  - Python handles circular imports at runtime; this is a linting concern not a correctness issue

#### 2.1.2 Context Injection (FR-8 through FR-12)

- **FR-8**: The system MUST provide cached context when agent accesses related files
  - Trigger: Agent performs Read operation on file with known dependencies
  - Inject relevant context from relationship graph

- **FR-9**: The system SHOULD inject function signatures when agent edits call sites
  - Include function name, parameters, return type (if available)
  - Inline during Read tool execution (DD-5)

- **FR-10**: The system MUST track token counts per injection for metrics-driven limit determination
  - **v0.1.0**: No token limit - inject all relevant context
  - **Rationale**: Gather real-world data before imposing arbitrary limits
  - Metrics track: min, max, median, p95, p99 token counts (see Section 3.10.1)
  - **Future (v0.1.1+)**: Add configurable limit based on metrics if needed
  - See Section 3.8.4 for detailed approach

- **FR-11**: The system SHOULD prioritize recently-accessed relationships over older ones
  - Use cache age metadata
  - Prioritize files modified/read in current session

- **FR-12**: The system MUST allow users to disable context injection via configuration
  - Configuration file: `.cross_file_context_links.yml`
  - Setting: `enable_context_injection: false`

#### 2.1.3 Working Memory Cache (FR-13 through FR-17)

- **FR-13**: The system MUST cache file snippets (not full files) for recently-accessed code
  - Cache granularity: Function definitions, line ranges
  - NOT: Full file contents

- **FR-14**: REMOVED - Time-based expiry removed for simplicity in v0.1.0
  - Rationale: Size-based LRU eviction (FR-16) is sufficient
  - Cache entries removed only when: (a) file modified (FR-15), or (b) LRU eviction when cache full
  - May be reconsidered in future versions if memory usage becomes a concern

- **FR-15**: The system MUST invalidate cache when underlying file is modified
  - File watcher tracks modification timestamps (see Section 3.6)
  - Cache checks staleness on each read operation (demand-driven)
  - Stale entries refreshed automatically on next access
  - See Section 3.7 for staleness detection algorithm

- **FR-16**: The system MUST have a configurable cache size limit
  - Initial default: 50KB per session
  - Adjustable via configuration (FR-49)
  - LRU eviction when limit exceeded (EC-15)

- **FR-17**: The system MUST provide cache hit/miss statistics for debugging
  - Track: hit rate, miss rate, eviction count, staleness refresh count
  - Emit in session metrics (FR-46)

#### 2.1.4 Cross-File Awareness (FR-18 through FR-21)

- **FR-18**: The system MUST identify all files that import/call a function being edited
  - Query relationship graph for reverse dependencies
  - Return list of dependent files with line numbers

- **FR-19**: The system MUST track and report the number of files that depend on each function being edited
  - Metric emission only (no fixed threshold in v0.1.0)
  - Data-driven threshold decisions post-launch (FR-46, FR-49)

- **FR-20**: The system SHOULD provide a list of dependent files when requested
  - API/query interface for relationship graph (FR-24)
  - Include file paths and line numbers

- **FR-21**: The system MUST track bidirectional relationships
  - Forward: A imports B
  - Reverse: B imported by A
  - Efficient bi-directional index in graph structure

#### 2.1.5 Relationship Graph Management (FR-22 through FR-25)

- **FR-22**: The system MUST maintain relationship graph in-memory during session
  - v0.1.0: No persistence across restarts
  - Graph rebuilt on each session start
  - v0.2.0+: Add persistence (see PRD Section 3.4)

- **FR-23**: The system MUST provide serialization/export of relationship graph to structured format
  - Format: JSON (human-readable)
  - Enable external tool integration and validation

- **FR-24**: The system SHOULD provide API to query relationship graph structure programmatically
  - Query patterns:
    - Get dependents of file X
    - Get dependencies of file X
    - Check if relationship exists between X and Y
    - Export full graph

- **FR-25**: Exported graph MUST include:
  - All detected relationships (source, target, type, line number)
  - File paths (absolute or relative to project root)
  - Relationship types (import, function_call, inheritance)
  - Timestamps (last modified, last analyzed)
  - Metadata (warnings, limitations, dynamic patterns detected)

#### 2.1.6 Context Injection Logging (FR-26 through FR-29)

- **FR-26**: The system MUST log all context injection events to a structured format
  - Real-time logging during session
  - Enable post-session analysis

- **FR-27**: Context injection logs MUST include:
  - `timestamp`: ISO 8601 format
  - `source_file`: File providing the context
  - `target_file`: File being edited/read (injection trigger)
  - `relationship_type`: import, function_call, etc.
  - `snippet`: The injected code snippet (function signature or full definition)
  - `cache_age`: Seconds since snippet last read
  - `token_count`: Number of tokens in injection

- **FR-28**: Context injection logs SHOULD use the same format as Claude Code session logs
  - Format: JSONL (newline-delimited JSON)
  - Consistent with existing Claude Code logging infrastructure

- **FR-29**: The system MUST provide an API or query mechanism to access recent context injection events
  - Query recent N injections
  - Filter by file, relationship type, time range

#### 2.1.7 Dynamic Python Handling and Warnings (FR-30 through FR-42)

**Warning System Overview:**
- **FR-30**: The system MUST emit warnings when encountering Python patterns that cannot be statically analyzed
  - Dynamic imports, dynamic dispatch, monkey patching, exec/eval, decorators, metaclasses
  - See prd_edge_cases.md EC-6 through EC-10

**Test vs Source Module Distinction:**
- **FR-31**: The system MUST distinguish between test modules and source modules when emitting warnings
  - Test modules: Suppress warnings (expected behavior for mocking, fixtures)
  - Source modules: Emit warnings (help developers understand limitations)

- **FR-32**: Test module identification MUST support common patterns:
  - File patterns: `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`, `**/conftest.py`
  - Pytest configuration parsing (DD-3): Read `pytest.ini`, `pyproject.toml`, `setup.cfg`
  - Extract `testpaths`, `python_files` settings

**Specific Pattern Warnings:**
- **FR-33**: The system MUST emit warnings for dynamic dispatch in source modules only
  - Pattern: `getattr(obj, dynamic_name)()`
  - Warning: "⚠️ Dynamic dispatch detected in {file}:{line} - relationship tracking unavailable for `getattr(obj, '{name}')`"
  - See EC-6

- **FR-34**: The system MUST emit warnings for monkey patching in source modules only
  - Pattern: `module.attribute = replacement`
  - Warning: "⚠️ Monkey patching detected in {file}:{line} - `{module}.{attr}` reassigned, relationship tracking may be inaccurate"
  - See EC-7

- **FR-35**: The system MUST emit warnings for `exec()` and `eval()` usage in source modules only
  - Pattern: `exec(code_string)` or `eval(expression_string)`
  - Warning: "⚠️ Dynamic code execution detected in {file}:{line} - `exec()`/`eval()` prevents static analysis, relationships may be incomplete"
  - See EC-9

- **FR-36**: The system SHOULD emit informational warnings for decorators in source modules
  - Pattern: `@decorator` that modifies function behavior
  - Warning: "⚠️ Decorator `{decorator_name}` in {file}:{line} may modify function behavior - tracking original definition only"
  - Suppress for common test decorators (`@pytest.mark`, `@unittest.skip`)
  - See EC-8

- **FR-37**: The system SHOULD emit informational warnings for metaclass usage
  - Pattern: `class Foo(metaclass=Meta):` or `__metaclass__ = Meta`
  - Warning: "ℹ️ Metaclass detected in {file}:{line} - class `{name}` uses metaclass `{metaclass}`, runtime behavior may differ from static definition"
  - See EC-10

**Warning Format and Suppression:**
- **FR-38**: Warning messages MUST include:
  - File path (absolute or relative to project root)
  - Line number
  - Pattern type (e.g., "dynamic_dispatch", "monkey_patching")
  - Human-readable explanation of limitation
  - Actionable guidance (if applicable)

- **FR-39**: The system MUST allow users to configure warning suppression via configuration file
  - File: `.cross_file_context_links.yml`
  - See FR-40 for suppression granularity

- **FR-40**: The system SHOULD support warning suppression at multiple levels:
  - File-level: `suppress_warnings: ["path/to/file.py"]`
  - Directory-level: `suppress_warnings: ["tests/**/*"]`
  - Pattern-specific: `suppress_dynamic_dispatch_warnings: true`

- **FR-41**: All warnings MUST be logged to structured format
  - Format: JSONL
  - Fields: timestamp, file, line, pattern_type, message

**Fail-Safe Principle:**
- **FR-42**: The system MUST NOT attempt to track relationships for patterns it cannot statically analyze
  - When dynamic pattern detected: Emit warning, mark as untrackable, DO NOT guess
  - Prioritize correctness over completeness

#### 2.1.8 Session Metrics and Data Collection (FR-43 through FR-49)

**Metrics Emission:**
- **FR-43**: The system MUST emit structured metrics at the end of each Claude Code session
  - Trigger: Session end/cleanup
  - Format: Structured file (see FR-45)

- **FR-44**: Session metrics MUST include all measurable values referenced in configurable parameters
  - Cache expiry times actually used
  - Token counts actually injected
  - Dependency counts for edited functions
  - Enable data-driven threshold tuning (FR-49)

- **FR-45**: Session metrics MUST be written to a structured format
  - Recommended: JSONL (newline-delimited JSON)
  - Machine-parseable for automated analysis

**Required Metrics (FR-46):**
The system MUST track and emit the following metrics per session:

**Cache Performance:**
- Actual cache expiry times used (from config)
- Cache hit rate (hits / (hits + misses))
- Cache miss rate
- Total cache size at peak
- Number of evictions (LRU, expiry-based)

**Context Injection:**
- Token counts per injection: min, max, median, p95
- Number of injections exceeding various thresholds (e.g., 300, 500, 700 tokens)
- Total injections performed
- Injections by relationship type (import, function_call, etc.)

**Relationship Graph:**
- Number of files in graph
- Number of relationships detected
- Most-connected files (top 10 with dependency counts)
- Note: Circular dependency detection deferred to v0.1.1+ (see Section 3.5.5)

**Function Usage Distribution:**
- For all functions edited during session: How many files depend on each
- Histogram data: X functions used in 1 file, Y functions used in 2-3 files, Z functions used in 4+ files

**Re-Read Patterns:**
- Files re-read during session with re-read counts
- Enable comparison to baseline (87.5% re-read rate)

**Performance:**
- Parsing times per file: min, max, median, p95
- Injection latency: min, max, median, p95
- Total indexing time

**Warning Statistics:**
- Count of each warning type emitted (dynamic_dispatch, monkey_patching, etc.)
- Files with most warnings (top 10)

**Metrics Privacy and Analysis:**
- **FR-47**: Metrics MUST be anonymized/aggregatable
  - No sensitive code snippets in metrics
  - Optional file path anonymization
  - Enable cross-session analysis without privacy concerns

- **FR-48**: The system SHOULD provide a metrics analysis tool
  - Parse session metrics from multiple sessions
  - Compute aggregate statistics (mean, median, p95)
  - Identify normal vs. outlier patterns
  - Suggest optimal configuration values

**Data-Driven Configuration:**
- **FR-49**: Configuration parameters MUST be adjustable based on observed metrics
  - No hard-coded thresholds that cannot be tuned
  - Examples:
    - Cache size limit (FR-16): Adjustable based on memory pressure observations
    - Token injection behavior (FR-10): No limit in v0.1.0, future limit determined by p95 token count if needed
    - AST parsing timeout: Adjustable based on file complexity and performance needs
    - AST recursion depth: Adjustable based on codebase nesting patterns
  - Configuration file: `.cross_file_context_links.yml`

### 2.2 Non-Functional Requirements

#### 2.2.1 Performance Requirements (NFR-1 through NFR-4)

- **NFR-1**: Relationship detection MUST complete within 200ms for files <5,000 lines
  - Includes AST parsing, detector execution, graph update
  - Tested via T-7.3 (see prd_testing.md)

- **NFR-2**: Context injection MUST NOT add more than 50ms latency to Read operations
  - Total latency budget: Read file + Query graph + Format context = <50ms
  - Tested via T-8.1

- **NFR-3**: The system SHOULD handle codebases up to 10,000 files
  - Graceful degradation beyond this limit (warnings, selective indexing)
  - Memory usage remains within NFR-4 bounds

- **NFR-4**: The system MUST NOT consume more than 500MB of memory for relationship graph
  - Includes graph structure, metadata, indices
  - Does NOT include cache (separate 50KB limit per FR-16)
  - Tested via T-7.4

#### 2.2.2 Privacy & Security Requirements (NFR-5 through NFR-8)

- **NFR-5**: The system MUST operate entirely locally
  - No cloud calls for core functionality
  - All processing on user's machine

- **NFR-6**: The system MUST NOT transmit file contents to external servers
  - Code stays on local filesystem
  - Metrics anonymized (FR-47)

- **NFR-7**: The system SHOULD respect .gitignore patterns for indexing
  - Parse .gitignore files in project
  - Skip ignored files during indexing

- **NFR-8**: The system MUST NOT index files in dependency directories
  - Patterns to skip: `node_modules/`, `.venv/`, `__pycache__/`, `.git/`, `venv/`, `env/`
  - User-configurable ignore patterns (low priority, see DD-2)

#### 2.2.3 Usability Requirements (NFR-9 through NFR-12)

- **NFR-9**: The system MUST work without manual configuration for standard project layouts
  - Auto-detect Python packages, test directories
  - Sane defaults for all configuration parameters
  - Configuration file optional, not required

- **NFR-10**: The system SHOULD provide visual indicators when context is injected
  - See PRD Open Questions Q-1 (UI deferred to post-launch)
  - Minimum: Logs are available for analysis (FR-26)

- **NFR-11**: The system MUST allow users to query the relationship graph
  - API interface (FR-24)
  - Export capability (FR-23)

- **NFR-12**: The system SHOULD log all relationship detections for debugging
  - Include in structured logs
  - Enable troubleshooting parsing/detection issues

#### 2.2.4 Compatibility Requirements (NFR-13 through NFR-16)

- **NFR-13**: The system MUST integrate with Claude Code's existing MCP architecture
  - Implement as MCP server
  - Follow MCP protocol specification
  - See DD-6 for architecture

- **NFR-14**: The system MUST NOT conflict with existing Read/Edit/Write tools
  - Extend tools, don't replace
  - Context injection is additive (inline with Read)

- **NFR-15**: The system SHOULD support incremental indexing
  - Not require full re-scan on every file edit
  - Incremental graph updates (FR-5)

- **NFR-16**: The system MUST gracefully degrade when parsing fails for a file
  - Skip file, log error, continue with others (EC-18)
  - Mark file as "unparseable" in graph metadata

### 2.3 Edge Case Requirements

See [`prd_edge_cases.md`](./prd_edge_cases.md) for full details. Key edge cases that MUST be handled:

**Relationship Detection:**
- **EC-1**: ~~Circular dependencies - Detect, warn, continue processing~~ **DEFERRED to v0.1.1+** (see FR-6, FR-7, Section 3.5.5 for rationale)
- **EC-2**: Dynamic imports - Skip, log as untrackable
- **EC-4**: Wildcard imports - Track at module level with limitations note
- **EC-6**: Dynamic dispatch - Warn in source modules, suppress in tests
- **EC-7**: Monkey patching - Warn in source modules, suppress in tests

**Context Injection:**
- **EC-11**: Stale cache after external edit - File watcher invalidates
- **EC-12**: Large functions - Inject signature only if exceeds token limit
- **EC-13**: Multiple definitions - Disambiguate with file paths

**Memory Management:**
- **EC-15**: Memory pressure - LRU eviction when cache full
- **EC-17**: Massive files - Skip files >10,000 lines with warning

**Failure Modes:**
- **EC-18**: Parsing failure - Skip file, log error, continue
- **EC-19**: Graph corruption - Detect, clear, rebuild

### 2.4 Testing Requirements

See [`prd_testing.md`](./prd_testing.md) for full details. Testing MUST cover:

**Functional Testing (T-1 through T-6):**
- T-1: Relationship detection (imports, calls, wildcards, import ambiguity)
  - Import ambiguity: Test `utils.py` vs `utils/__init__.py` precedence (module file should shadow package)
  - Note: Circular dependency detection deferred to v0.1.1+ (see Section 3.5.5)
- T-2: Context injection (trigger, limits, relevance, configurability)
- T-3: Working memory cache (hit/miss, expiry, invalidation, LRU)
- T-4: Cross-file awareness (dependents, warnings, bidirectional relationships, graph export)
- T-5: Context injection logging (structured format, required fields, parseability)
- T-6: Dynamic Python handling (test vs source distinction, warning suppression, fail-safe)

**Security Testing:**
- DoS Prevention: Test AST parsing with deeply nested expressions (configure `ast_max_recursion_depth` to low value for testing)
- DoS Prevention: Test AST parsing timeout with complex files (configure `ast_parsing_timeout_seconds` for testing)
- Path Traversal: Test symlink handling with targets outside project root

**Performance Testing (T-7 through T-8):**
- T-7: Indexing performance (100 files <10s, 1000 files <2min, incremental <200ms)
- T-8: Runtime performance (injection <50ms, cache lookup <10ms)

**Integration Testing (T-9 through T-10):**
- T-9: Claude Code integration (MCP server, tool integration, error handling)
- T-10: Session metrics (emission, required fields, parseability, analysis tool)

**UAT Testing:**
- Alpha: 3-5 internal developers, Week 1, focus on basic functionality
- Beta: 10-15 external developers, Weeks 2-3, focus on real-world usage
- Pilot: 50+ developers, Week 4, focus on performance at scale

**Success Criteria:**
- Primary: <30% re-read rate (from 87.5% baseline)
- >80% user satisfaction
- <5% opt-out rate

---

## 3. Proposed Solution

### 3.1 High-Level Architecture

#### 3.1.1 Architecture Overview

Cross-File Context Links is implemented as a **standalone MCP server** with a **three-layer architecture** designed to enable smooth evolution from v0.1.0 (single-session, in-memory) to v0.2.0 (multi-session, persisted state).

**Architectural Layers:**

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: MCP Protocol Layer                                 │
│   - Handles MCP tool calls (read_with_context, etc.)       │
│   - Thin adapter, no business logic                         │
│   - Communication: stdio (standard MCP pattern)             │
└─────────────────────────────────────────────────────────────┘
                         ↓ delegates to
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Business Logic Layer                               │
│   - CrossFileContextService (orchestrates all components)   │
│   - RelationshipGraph, WorkingMemoryCache                   │
│   - Language Analyzers (PythonAnalyzer in v0.1.0)          │
│   - Relationship Detectors (plugin pattern)                 │
│   - FileWatcher, WarningSystem, MetricsCollector           │
│   - NO MCP dependencies (enables v0.2.0 extraction)        │
└─────────────────────────────────────────────────────────────┘
                         ↓ uses
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Storage Layer                                      │
│   - RelationshipStore interface (abstract)                  │
│   - InMemoryStore (v0.1.0 implementation)                  │
│   - SQLiteStore (v0.2.0 future implementation)             │
│   - Serializable data structures (JSON-compatible)         │
└─────────────────────────────────────────────────────────────┘
```

**Key Architectural Patterns (from Design Decisions):**

1. **Layer Separation (DD-6)**: MCP protocol handling separated from business logic, enabling v0.2.0 backend service extraction with minimal refactoring
2. **Detector Plugin Pattern (DD-1)**: Relationship detectors are modular, prioritized plugins
3. **Language Analyzer Registry (DD-2)**: Three-layer file monitoring: Watcher → Analyzers → Detectors
4. **Storage Abstraction (DD-4)**: Interface-based storage with serializable structures
5. **Dependency Injection**: Factory pattern for creating services with injected dependencies

#### 3.1.2 System Context

**Integration with Claude Code:**

```
Claude Code Session
    ↓ spawns MCP server (per-session, via stdio)
┌────────────────────────────────────────────────┐
│ xfile-context MCP Server Process               │
│   - Receives MCP tool calls                    │
│   - Returns enhanced Read results with context │
│   - Monitors project files via watcher         │
│   - In-memory graph (session-scoped)          │
└────────────────────────────────────────────────┘
    ↓ watches & indexes
┌────────────────────────────────────────────────┐
│ User's Project Repository                      │
│   - Python files (.py)                         │
│   - Configuration (.cross_file_context_links.yml) │
│   - Test directories (tests/, conftest.py)    │
└────────────────────────────────────────────────┘
```

**MCP Server Lifecycle:**
- **Spawn**: Claude Code spawns MCP server at session start
- **Initialization**: Server indexes project files, builds initial relationship graph
- **Active**: Server watches for file changes, responds to tool calls
- **Termination**: Session ends, server terminates, in-memory graph discarded (per FR-22)

**Configuration:**
```json
// .claude_code/mcp_servers.json
{
  "xfile-context": {
    "command": "python",
    "args": ["-m", "xfile_context.mcp_server"],
    "cwd": "${workspaceFolder}"
  }
}
```

#### 3.1.3 Component Diagram

**Major Components and Interactions:**

```
┌─────────────────────────────────────────────────────────────────┐
│ CrossFileContextMCPServer (MCP Protocol Layer)                   │
│   • list_tools() → Returns available MCP tools                   │
│   • call_tool(name, args) → Delegates to service                │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓ uses
┌─────────────────────────────────────────────────────────────────┐
│ CrossFileContextService (Business Logic Orchestrator)            │
│   • Owns: graph, cache, store, watcher, analyzer                │
│   • read_with_context(filepath) → Enhanced read with injection  │
│   • query_relationships(filepath) → Query graph API             │
│   • export_graph(format) → Export graph to JSON                 │
└─────────────────────────┬───────────────────────────────────────┘
                          ↓ coordinates
                   ┌──────┴──────┬─────────┬──────────┐
                   ↓             ↓         ↓          ↓
         ┌─────────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐
         │Relationship │ │Working   │ │File    │ │Warning   │
         │Graph        │ │Memory    │ │Watcher │ │System    │
         │             │ │Cache     │ │        │ │          │
         └──────┬──────┘ └────┬─────┘ └───┬────┘ └──────────┘
                ↓             ↓            ↓
         ┌──────────────────────────────────────┐
         │ RelationshipStore (abstraction)      │
         │   - InMemoryStore (v0.1.0)          │
         │   - SQLiteStore (v0.2.0 future)     │
         └──────────────────────────────────────┘
```

**Detailed Component Breakdown:**

**1. RelationshipGraph**
- Owns bidirectional index of file relationships
- Query operations: get_dependencies(file), get_dependents(file)
- Update operations: add_relationship(), remove_relationships_for_file()
- Cycle detection for circular imports
- Delegates persistence to RelationshipStore

**2. FileWatcher (DD-2: Language-Agnostic)**
- Monitors project directory for file changes
- Respects .gitignore patterns (NFR-7)
- Skips dependency directories (node_modules, .venv, etc. per NFR-8)
- On file change: Query AnalyzerRegistry for appropriate analyzer
- Dispatch to analyzer if supported language, skip otherwise

**3. AnalyzerRegistry (DD-2)**
- Registers language analyzers by file extension
- v0.1.0: PythonAnalyzer (.py files only)
- v0.2.0+: Add TypeScriptAnalyzer, GoAnalyzer
- Query: get_analyzer(filepath) → Optional[LanguageAnalyzer]

**4. PythonAnalyzer (DD-2)**
- Implements LanguageAnalyzer interface
- Owns DetectorRegistry with Python-specific detectors
- analyze_file(filepath) → Parse AST, run detectors, return relationships
- Supported extensions: [".py"]

**5. DetectorRegistry (DD-1)**
- Registers relationship detectors with priorities
- Priority-based dispatch (highest priority first)
- One detector per AST node (first matching detector wins)
- v0.1.0 detectors:
  - ImportDetector (priority 100): Builds import map
  - SimpleCallDetector (priority 50): Detects function() and module.function()
  - AliasedImportDetector: Handles import foo as bar
  - ConditionalImportDetector: Handles if TYPE_CHECKING
  - WildcardImportDetector: Handles from utils import *
  - ClassInheritanceDetector: Tracks inheritance

**6. WorkingMemoryCache**
- LRU cache for file snippets (not full files)
- Expiry: 10 minutes from last access (configurable per FR-14)
- Size limit: 50KB (configurable per FR-16)
- Operations:
  - get(filepath, line_range) → Optional[CacheEntry]
  - put(filepath, line_range, content, metadata)
  - invalidate(filepath) (on file modification)
  - evict_expired(), evict_lru()
- Statistics: hit rate, miss rate, eviction counts

**7. RelationshipStore (DD-4: Storage Abstraction)**
- Abstract interface for graph persistence
- Operations:
  - add(relationship: Relationship)
  - query(source_file) → List[Relationship]
  - get_all() → List[Relationship]
  - export_to_json(path) (all implementations must support)
- v0.1.0: InMemoryStore (simple list, no persistence)
- v0.2.0+: SQLiteStore (queryable, transactional)

**8. TestFileDetector (DD-3)**
- Reads pytest configuration (pytest.ini, pyproject.toml, setup.cfg)
- Extracts python_files, testpaths patterns
- Fallback to defaults: test_*.py, *_test.py, tests/**/*.py, conftest.py
- Classification: is_test_file(filepath) → bool

**9. WarningSystem**
- Detects dynamic Python patterns (EC-6 through EC-10)
- Test vs source module distinction (uses TestFileDetector)
- Warning types: dynamic_dispatch, monkey_patching, exec_eval, decorators, metaclasses
- Suppression via configuration (.cross_file_context_links.yml)
- Structured logging (JSONL format)

**10. MetricsCollector**
- Tracks session metrics (FR-43 through FR-49)
- Emits at session end: cache performance, injection stats, graph stats, warnings
- Structured format (JSONL) for automated analysis
- Enables data-driven threshold tuning

#### 3.1.4 Data Flow Diagrams

**Flow 1: Initial Project Indexing (Session Start)**

```
Session Start
    ↓
MCP Server Spawned
    ↓
CrossFileContextService.__init__()
    ↓
┌────────────────────────────────────┐
│ 1. Discover Python Files           │
│    - Walk project directory        │
│    - Respect .gitignore (NFR-7)   │
│    - Skip dependencies (NFR-8)     │
│    - Filter: *.py only (v0.1.0)   │
└────────────────┬───────────────────┘
                 ↓
┌────────────────────────────────────┐
│ 2. Parse & Analyze Each File       │
│    - PythonAnalyzer.analyze_file() │
│    - AST parsing (ast.parse)       │
│    - Detector dispatch (priority)  │
│    - Build import map              │
│    - Detect relationships          │
└────────────────┬───────────────────┘
                 ↓
┌────────────────────────────────────┐
│ 3. Build Relationship Graph        │
│    - Add relationships to graph    │
│    - Build bidirectional index     │
│    - Store in RelationshipStore    │
└────────────────┬───────────────────┘
                 ↓
┌────────────────────────────────────┐
│ 4. Start File Watcher              │
│    - Watch project directory       │
│    - Listen for file changes       │
└────────────────────────────────────┘
                 ↓
Ready to serve MCP tool calls
```

**Performance Target**: Index 100 files (<5,000 lines each) in <10 seconds (T-7.1)

---

**Flow 2: Read with Context Injection (Demand-Driven)**

```
Claude Code: Read(bot.py)
    ↓ MCP tool call
CrossFileContextMCPServer.call_tool("read_with_context", {filepath: "bot.py"})
    ↓ delegates to service
CrossFileContextService.read_with_context("bot.py")
    ↓
┌──────────────────────────────────────────┐
│ 1. Cache Get with Staleness Check       │
│    content = cache.get("bot.py")        │
│    ↓ checks: is_stale("bot.py")?        │
│    If stale or miss:                     │
│      - Capture timestamp                 │
│      - Read from disk                    │
│      - Re-analyze relationships (AST)    │
│      - Update cache + graph atomically   │
│    If fresh: Return cached content       │
│    (500 tokens)                          │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 2. Query Relationship Graph              │
│    deps = graph.get_dependencies("bot.py")│
│    → ["retry.py:120", "config.py:45"]   │
│    (Graph is fresh - updated in step 1) │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 3. Get Context from Dependencies        │
│    For each dep:                         │
│      content = cache.get(dep)            │
│      (Each triggers staleness check!)    │
│      snippet = extract_signature(content)│
│      context.append(snippet)             │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 4. Token Budget Check                    │
│    total_tokens = count_tokens(context)  │
│    if total_tokens > 500: truncate       │
│    (FR-10: <500 token limit)            │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 5. Format Context Section                │
│    --- Related Context ---               │
│    def retry_with_backoff(...):          │
│      """..."""                           │
│    ---                                   │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 6. Log Injection Event                   │
│    {timestamp, source, target, tokens,   │
│     relationship_type}                   │
│    (FR-26, FR-27: structured JSONL)     │
└──────────────┬───────────────────────────┘
               ↓
Return to Claude: content + context (550 tokens)
```

**Performance Target**: Injection latency <50ms (T-8.1, NFR-2)

**Token Savings**: 58% reduction (from 1,300 tokens to 550 tokens in example)

**Key Change**: Analysis is demand-driven (happens during cache.get), not triggered by file watcher

---

**Flow 3: File Modification (Simplified Timestamp-Only)**

```
User edits retry.py (external editor or Claude Edit tool)
    ↓ file system event
FileWatcher detects modification
    ↓
┌──────────────────────────────────────────┐
│ 1. Update Timestamp (Only!)             │
│    file_event_timestamps["retry.py"] =   │
│      time.time()                         │
│    # Thread-safe: GIL protects dict write│
│    # NO analysis, NO cache invalidation  │
└──────────────────────────────────────────┘
               ↓
Done! (FileWatcher idle again)

Later, when "retry.py" is read:
    ↓
┌──────────────────────────────────────────┐
│ 2. Demand-Driven Refresh (Cache Read)   │
│    cache.get("retry.py")                 │
│    ↓ detects: is_stale?                  │
│    file_event_timestamps["retry.py"] >   │
│      file_last_read_timestamps["retry.py"]│
│    ↓ TRUE → refresh from disk            │
│    - Read file                           │
│    - Parse AST                           │
│    - Detect relationships                │
│    - Update graph atomically             │
└──────────────────────────────────────────┘
```

**Performance Target**: Timestamp update ~microseconds (instant)
**Analysis deferred to read**: Happens demand-driven, within <200ms (NFR-1)

**Key Change**: FileWatcher does minimal work (timestamp only). All expensive operations deferred to cache reads.

---

**Flow 4: Dynamic Pattern Detection & Warning Emission**

```
PythonAnalyzer.analyze_file("source.py")
    ↓ AST traversal
Detects: getattr(obj, dynamic_name)()
    ↓
┌──────────────────────────────────────────┐
│ 1. Check File Classification             │
│    is_test = TestFileDetector.is_test_file│
│              ("source.py")                │
│    → False (source module)               │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 2. Check Warning Suppression Config      │
│    config = load_config()                │
│    if "source.py" in suppressed: skip    │
│    if suppress_dynamic_dispatch: skip    │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 3. Emit Warning                           │
│    warning = Warning(                    │
│      file="source.py",                   │
│      line=42,                            │
│      type="dynamic_dispatch",            │
│      message="⚠️ Dynamic dispatch..."    │
│    )                                     │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 4. Log to Structured Format              │
│    {timestamp, file, line, type, msg}    │
│    (FR-41: JSONL format)                 │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────────┐
│ 5. Mark as Untrackable (FR-42)          │
│    graph.add_metadata(file, {            │
│      "has_dynamic_patterns": True,       │
│      "patterns": ["dynamic_dispatch"]    │
│    })                                    │
│    DO NOT attempt to track relationship  │
└──────────────────────────────────────────┘
```

**Principle**: Fail-safe - emit warning, mark as untrackable, do NOT guess relationships (FR-42)

#### 3.1.5 Evolution Path: V0.1.0 → V0.2.0

**V0.1.0 Architecture (Current):**

```
┌──────────────────────────────────────────────────┐
│ Single MCP Server Process (Per Session)          │
│                                                   │
│  ┌────────────────────────────────────────────┐ │
│  │ MCP Protocol Layer                         │ │
│  │   CrossFileContextMCPServer                │ │
│  └───────────────┬────────────────────────────┘ │
│                  ↓                               │
│  ┌────────────────────────────────────────────┐ │
│  │ Business Logic Layer                       │ │
│  │   CrossFileContextService                  │ │
│  │     - RelationshipGraph (in-memory)       │ │
│  │     - WorkingMemoryCache                   │ │
│  │     - FileWatcher                          │ │
│  │     - PythonAnalyzer + Detectors          │ │
│  └───────────────┬────────────────────────────┘ │
│                  ↓                               │
│  ┌────────────────────────────────────────────┐ │
│  │ Storage Layer                              │ │
│  │   InMemoryStore (list of Relationship)    │ │
│  └────────────────────────────────────────────┘ │
│                                                   │
│ Session ends → Graph discarded (FR-22)          │
└──────────────────────────────────────────────────┘
```

**Characteristics:**
- Self-contained: All logic in single MCP server process
- In-memory only: No persistence across sessions (FR-22)
- Isolated: Each session rebuilds graph from scratch
- Simple: No IPC, no backend service management

---

**V0.2.0 Architecture (Future):**

```
┌────────────────────────┐  ┌────────────────────────┐
│ Parent Session         │  │ Subagent Session 1     │
│   MCP Server A         │  │   MCP Server B         │
│     ↓                  │  │     ↓                  │
│   Client (IPC adapter) │  │   Client (IPC adapter) │
└───────────┬────────────┘  └──────────┬─────────────┘
            │                          │
            └──────────┬───────────────┘
                       ↓ IPC (Unix socket / HTTP)
          ┌────────────────────────────────────┐
          │ Backend Service Process            │
          │   (Long-running, shared)           │
          │                                    │
          │  CrossFileContextService           │
          │    - RelationshipGraph             │
          │    - WorkingMemoryCache            │
          │    - FileWatcher                   │
          │    - PythonAnalyzer + Detectors    │
          │    - SQLiteStore (persisted)       │
          │                                    │
          │  ↓ persists to                     │
          │  SQLite Database                   │
          │  (.xfile_context/graph.db)         │
          └────────────────────────────────────┘
```

**Characteristics:**
- Multi-session: Parent + subagents share graph state
- Persisted: Graph survives session restarts
- Efficient: Subagents avoid re-parsing (load from shared graph)
- Thin MCP servers: Protocol adapters only, delegate to backend

---

**Refactoring Effort (V0.1.0 → V0.2.0):**

| Component | Lines Changed | Lines Added | Notes |
|-----------|---------------|-------------|-------|
| MCP Server | 1 line | 0 | Change service instantiation |
| Business Logic | 1 line | 0 | Swap InMemoryStore → SQLiteStore |
| Client Adapter | 0 | ~50 | New CrossFileContextClient class |
| IPC Layer | 0 | ~100 | New communication mechanism |
| **Total** | **2 lines** | **~150 lines** | Business logic unchanged |

**Key Enablers:**
- Layer separation (DD-6): MCP layer has no business logic
- Storage abstraction (DD-4): Swap store implementations
- Dependency injection: Factory pattern for instantiation
- Interface-based design: Service interface unchanged
- Modular components (DD-1, DD-2): Move as unit to backend

#### 3.1.6 Key Architectural Decisions Summary

**DD-1 (Modular AST Parsing):**
- Impact: Relationship detectors are independent, prioritized plugins
- Benefit: Incremental complexity (v0.1.0 simple calls, v0.1.1+ method chains)

**DD-2 (Language-Agnostic File Watcher):**
- Impact: Three-layer architecture: Watcher → Analyzers → Detectors
- Benefit: Add TypeScript/Go support without watcher changes

**DD-3 (Test File Detection):**
- Impact: Parse pytest configuration, treat conftest.py as test infrastructure
- Benefit: Accurate test vs source distinction, suppress noisy warnings

**DD-4 (Persistence Architecture):**
- Impact: Serializable structures (primitives only) + storage abstraction
- Benefit: Easy v0.2.0 migration (InMemoryStore → SQLiteStore)

**DD-5 (Context Injection Strategy):**
- Impact: Inline injection during Read tool (location + signature only)
- Benefit: 58% token reduction, natural UX, automatic and proactive

**DD-6 (MCP Server Architecture):**
- Impact: Layered design with no MCP dependencies in business logic
- Benefit: v0.2.0 backend extraction requires only 2 lines changed

**Synergies:**
- DD-1 detectors work within DD-2 language analyzers
- DD-2 analyzers use DD-4 storage abstraction
- DD-4 storage enables DD-6 v0.2.0 evolution
- DD-5 injection leverages DD-1 relationship detection
- All orchestrated by DD-6 service layer

---

### 3.2 Key Design Decisions

The following architectural decisions were made during the design phase to address open questions while supporting future evolution. **For full rationale, analysis, and implementation details, see [`design_decisions.md`](./design_decisions.md).**

| Decision | Problem | Solution | Key Impact |
|----------|---------|----------|------------|
| **DD-1**: Modular AST Parsing | How deep should call detection go in v0.1.0? | Detector plugin pattern with incremental complexity | v0.1.0: simple calls only; v0.1.1+: add method chains, nested attributes as separate plugins |
| **DD-2**: Language-Agnostic Watcher | Design for multi-language future (TypeScript v0.2.0, Go v0.3.0)? | Three-layer architecture: Watcher → Analyzers → Detectors | Add new languages without watcher changes; plugin-based language support |
| **DD-3**: Test File Detection | Distinguish test vs source modules for warning suppression? | Parse pytest configuration files; treat `conftest.py` as test infrastructure | Accurate warning suppression; no pytest runtime dependency; respects user config |
| **DD-4**: Persistence Architecture | Enable v0.2.0 persistence with minimal refactoring? | Serializable structures (primitives only) + storage abstraction | v0.2.0 migration: ~1 line change (InMemoryStore → SQLiteStore) |
| **DD-5**: Context Injection | When and how to inject context to reduce re-reads? | Inline with Read tool (location + signature only) | 58% token reduction; natural UX; no new tools for Claude to learn |
| **DD-6**: MCP Architecture | Minimize v0.2.0 refactoring for backend extraction? | Layered architecture: MCP Protocol → Business Logic → Storage | v0.2.0 backend extraction: 2 lines changed, ~150 lines added; business logic untouched |
| **DD-8**: AST vs Interpreter | Use AST analysis or interpreter inspection for symbol resolution? | AST-first (v0.1.0); optional interpreter fallback (v0.2.0+) | Safe, fast, no code execution; works with incomplete code; metrics track effectiveness (see Section 3.5.6) |

**Key Synergies**: All decisions work together cohesively:
- DD-1 detector plugins work within DD-2 language analyzers
- Both use DD-4 storage abstraction for persistence
- DD-3 test detection enables accurate warning suppression
- DD-8 AST-first approach provides safe, fast symbol resolution
- DD-6 service layer orchestrates all components
- DD-5 context injection is the user-facing feature that leverages the entire system

---

### 3.3 Data Models

This section defines all core data structures. Per DD-4, all models use **JSON-compatible primitives only** (str, int, bool, float, Optional, List, Dict) to enable easy serialization and future persistence.

#### 3.3.1 Relationship Model

**Core Relationship Structure:**

```python
from dataclasses import dataclass
from typing import Optional, Dict

class RelationshipType:
    """Types of relationships between files"""
    IMPORT = "import"                    # from foo import bar
    FUNCTION_CALL = "function_call"      # calling a function from another file
    CLASS_INHERITANCE = "inheritance"    # class Foo(Bar)
    WILDCARD_IMPORT = "wildcard_import"  # from foo import *
    CONDITIONAL_IMPORT = "conditional_import"  # if TYPE_CHECKING: import

@dataclass
class Relationship:
    """
    Represents a dependency relationship between two files.

    Design Constraint (DD-4): Uses primitives only for easy serialization.
    All fields are JSON-compatible.
    """

    # Required fields
    source_file: str          # File that depends on target (absolute or relative path)
    target_file: str          # File being depended upon
    relationship_type: str    # RelationshipType enum value (stored as string)
    line_number: int          # Line in source_file where relationship exists

    # Optional fields
    source_symbol: Optional[str] = None    # Symbol in source (e.g., function name)
    target_symbol: Optional[str] = None    # Symbol in target (e.g., imported name)
    target_line: Optional[int] = None      # Line in target where symbol defined

    # Metadata (JSON-compatible dict)
    metadata: Optional[Dict[str, str]] = None
```

**Example Instances:**

```python
# Example 1: Import relationship
rel1 = Relationship(
    source_file="src/bot.py",
    target_file="src/retry.py",
    relationship_type=RelationshipType.IMPORT,
    line_number=5,
    source_symbol="retry_with_backoff",
    target_symbol="retry_with_backoff",
    target_line=120
)

# Example 2: Function call relationship
rel2 = Relationship(
    source_file="src/bot.py",
    target_file="src/retry.py",
    relationship_type=RelationshipType.FUNCTION_CALL,
    line_number=46,
    source_symbol=None,
    target_symbol="retry_with_backoff",
    target_line=120
)

# Example 3: Wildcard import (module-level)
rel3 = Relationship(
    source_file="src/handlers.py",
    target_file="src/utils.py",
    relationship_type=RelationshipType.WILDCARD_IMPORT,
    line_number=3,
    source_symbol="*",
    target_symbol=None,
    target_line=None,
    metadata={"limitation": "function-level tracking unavailable"}
)
```

**Serialization Format (JSON):**

```json
{
  "source_file": "src/bot.py",
  "target_file": "src/retry.py",
  "relationship_type": "import",
  "line_number": 5,
  "source_symbol": "retry_with_backoff",
  "target_symbol": "retry_with_backoff",
  "target_line": 120,
  "metadata": {}
}
```

---

#### 3.3.2 Relationship Graph Model

**Graph Structure:**

```python
from typing import List, Dict, Set, Optional

@dataclass
class FileMetadata:
    """Metadata about a file in the relationship graph"""
    filepath: str
    last_analyzed: float        # Unix timestamp
    relationship_count: int     # Number of relationships involving this file
    has_dynamic_patterns: bool  # Contains untrackable dynamic patterns (FR-42)
    dynamic_pattern_types: List[str]  # e.g., ["dynamic_dispatch", "monkey_patching"]
    is_unparseable: bool        # Syntax error prevented analysis (EC-18)
    # Note: has_circular_deps removed (cycle detection deferred to v0.1.1+, see Section 3.5.5)

class RelationshipGraph:
    """
    Bidirectional graph of file relationships.

    Maintains two indices for efficient queries:
    - dependencies: file → files it depends on
    - dependents: file → files that depend on it
    """

    # Core data (stored in RelationshipStore per DD-4)
    _relationships: List[Relationship]

    # Bidirectional indices for fast lookups
    _dependencies: Dict[str, Set[str]]  # file → files it depends on
    _dependents: Dict[str, Set[str]]    # file → files that depend on it

    # Metadata
    _file_metadata: Dict[str, FileMetadata]

    # Note: _circular_groups removed (cycle detection deferred to v0.1.1+, see Section 3.5.5)

    # Key operations:
    # - add_relationship(rel) → Add relationship and update indices
    # - get_dependencies(filepath) → Get relationships where filepath depends on others
    # - get_dependents(filepath) → Get relationships where others depend on filepath
    # - remove_relationships_for_file(filepath) → Remove all relationships involving file
    # - export_to_dict() → Export graph to JSON (FR-23, FR-25)
    # Note: detect_circular_dependencies() removed (deferred to v0.1.1+, see Section 3.5.5)
```

**Bidirectional Index Update Error Handling:**

When adding relationships, both indices must be updated:
```python
def add_relationship(self, rel: Relationship) -> None:
    """
    Add relationship and update bidirectional indices.

    Error handling: At target scale (10,000 files, <500MB), dict updates
    are highly unlikely to fail. If they do fail (e.g., out of memory),
    raise error immediately - do NOT attempt rollback/recovery.
    """
    try:
        # Update forward index
        if rel.source_file not in self._dependencies:
            self._dependencies[rel.source_file] = set()
        self._dependencies[rel.source_file].add(rel.target_file)

        # Update reverse index
        if rel.target_file not in self._dependents:
            self._dependents[rel.target_file] = set()
        self._dependents[rel.target_file].add(rel.source_file)

        # Add to relationships list
        self._relationships.append(rel)
    except Exception as e:
        # If dict update fails (extremely unlikely at target scale):
        # Log error with full context and re-raise
        # Do NOT attempt rollback - indices may be inconsistent
        # System will rebuild graph from scratch on next session
        logger.error(f"Graph update failed for {rel.source_file} → {rel.target_file}: {e}")
        raise
```

**Rationale:**
- Target scale: 10,000 files, <500MB memory → dict updates extremely unlikely to fail
- If failure occurs: Indicates serious system issue (out of memory, disk failure)
- Recovery strategy: Graph is in-memory only (v0.1.0), rebuilt on next session
- Complexity tradeoff: Simple error handling vs complex transaction/rollback logic

**Graph Export JSON Format (FR-25):**

```json
{
  "version": "0.1.0",
  "timestamp": 1700000000.0,
  "relationships": [
    {
      "source_file": "src/bot.py",
      "target_file": "src/retry.py",
      "relationship_type": "import",
      "line_number": 5,
      "source_symbol": "retry_with_backoff",
      "target_symbol": "retry_with_backoff",
      "target_line": 120,
      "metadata": {}
    }
  ],
  "file_metadata": {
    "src/bot.py": {
      "filepath": "src/bot.py",
      "last_analyzed": 1700000000.0,
      "relationship_count": 5,
      "has_dynamic_patterns": false,
      "dynamic_pattern_types": [],
      "is_unparseable": false
    }
  },
  "statistics": {
    "total_files": 150,
    "total_relationships": 423,
    "files_with_dynamic_patterns": 12
  }
}
}
```

---

#### 3.3.3 Cache Entry Model

**Cache Entry Structure:**

```python
@dataclass
class CacheEntry:
    """
    Cached file snippet for working memory (FR-13).

    Design: Cache snippets (function signatures), not full files.
    """

    # Core data
    filepath: str
    line_start: int
    line_end: int
    content: str              # The cached snippet (function signature + docstring)

    # Metadata
    last_accessed: float      # Unix timestamp of last access (for LRU eviction)
    access_count: int         # Number of times accessed
    size_bytes: int           # Size in bytes for cache size tracking

    # Context
    symbol_name: Optional[str] = None   # Function/class name if applicable

@dataclass
class CacheStatistics:
    """Statistics for working memory cache (FR-17)"""

    hits: int
    misses: int
    staleness_refreshes: int  # Number of refreshes due to staleness detection
    evictions_lru: int        # Number of LRU evictions
    current_size_bytes: int
    peak_size_bytes: int
    current_entry_count: int
    peak_entry_count: int
```

**Timestamp Tracking Structures:**

The cache maintains two separate timestamp dictionaries for staleness detection (see Section 3.7):

```python
# Owned by FileWatcher (updated by watcher thread)
# GIL ensures thread-safe reads by cache thread
file_event_timestamps: Dict[str, float] = {}  # filepath -> last modification time

# Owned by WorkingMemoryCache (updated by cache thread)
# Protected by cache lock, synchronized with actual_cache
file_last_read_timestamps: Dict[str, float] = {}  # filepath -> time file was read
```

**Staleness Detection:**
- Cache checks `file_event_timestamps[filepath] > file_last_read_timestamps[filepath]`
- If stale: Refresh from disk and update relationship graph (demand-driven)
- See Section 3.7 for detailed staleness checking algorithm

**Example Cache Entry:**

```python
entry = CacheEntry(
    filepath="src/retry.py",
    line_start=120,
    line_end=135,
    content='def retry_with_backoff(func, max_attempts=3, base_delay=1.0):\n    """Retry function with exponential backoff"""\n    ...',
    last_accessed=1700000480.0,
    access_count=3,
    size_bytes=250,
    symbol_name="retry_with_backoff"
)
```

---

#### 3.3.4 Warning Model

**Warning Structure:**

```python
class WarningType:
    """Types of warnings for untrackable dynamic patterns"""
    DYNAMIC_DISPATCH = "dynamic_dispatch"      # getattr(obj, name)()
    MONKEY_PATCHING = "monkey_patching"        # module.attr = replacement
    EXEC_EVAL = "exec_eval"                    # exec()/eval()
    DECORATOR = "decorator"                    # @decorator with dynamic behavior
    METACLASS = "metaclass"                    # Custom metaclass
    CIRCULAR_IMPORT = "circular_import"        # Circular dependency detected

@dataclass
class Warning:
    """
    Warning about untrackable dynamic patterns or code smells.

    Structured format for logging (FR-38, FR-41).
    """

    # Location
    filepath: str
    line_number: int

    # Warning details
    warning_type: str         # WarningType enum value (stored as string)
    message: str              # Human-readable explanation

    # Context
    timestamp: float          # When warning was emitted
    code_snippet: Optional[str] = None  # Snippet of problematic code

    # Metadata
    severity: str = "warning"  # "info", "warning", "error"
    suppressed: bool = False   # Whether warning was suppressed by config

@dataclass
class SuppressionConfig:
    """Configuration for warning suppression (FR-39, FR-40)"""

    # File/directory-level suppression
    suppressed_files: List[str]         # Exact file paths
    suppressed_patterns: List[str]      # Glob patterns (e.g., "tests/**/*")

    # Pattern-specific suppression
    suppress_dynamic_dispatch: bool
    suppress_monkey_patching: bool
    suppress_exec_eval: bool
    suppress_decorators: bool
    suppress_metaclasses: bool
    suppress_circular_imports: bool
```

**Warning JSON Format (FR-41):**

```json
{
  "timestamp": 1700000000.0,
  "filepath": "src/handler.py",
  "line_number": 42,
  "warning_type": "dynamic_dispatch",
  "severity": "warning",
  "message": "⚠️ Dynamic dispatch detected in src/handler.py:42 - relationship tracking unavailable for `getattr(obj, 'handle')`",
  "code_snippet": "handler = getattr(obj, func_name)()",
  "suppressed": false
}
```

**Configuration File Format (.cross_file_context_links.yml):**

```yaml
# Warning suppression
suppress_warnings:
  - "tests/test_helpers.py"
  - "scripts/migration.py"

suppress_warnings_patterns:
  - "tests/**/*"
  - "**/conftest.py"

# Pattern-specific suppression
suppress_dynamic_dispatch_warnings: false
suppress_monkey_patching_warnings: false
suppress_exec_eval_warnings: false
suppress_decorator_warnings: false
suppress_metaclass_warnings: false
suppress_circular_import_warnings: false

# Configuration parameters (FR-49)
cache_expiry_seconds: 600      # 10 minutes (FR-14)
cache_size_limit_kb: 50        # 50KB (FR-16)
token_injection_limit: 500     # tokens (FR-10)
enable_context_injection: true # (FR-12)
```

---

#### 3.3.5 Context Injection Log Model

**Injection Log Entry Structure (FR-26, FR-27):**

```python
@dataclass
class ContextInjectionEvent:
    """
    Log entry for context injection event.

    Structured format matching Claude Code session logs (FR-28).
    """

    # Event metadata
    timestamp: float          # Unix timestamp
    event_type: str           # "context_injection" for consistency with other logs

    # Trigger information
    trigger: str              # "agent_read_file"
    trigger_file: str         # File being read (e.g., "src/bot.py")

    # Injected context
    injected_context: List[Dict[str, any]]  # List of context snippets

    # Metrics
    total_token_count: int    # Total tokens injected
    cache_hit: bool           # Whether context came from cache

@dataclass
class InjectedContextSnippet:
    """Individual context snippet within injection event"""

    source_file: str          # File providing context (e.g., "src/retry.py")
    lines: str                # Line range (e.g., "120-135")
    snippet: str              # Function signature + docstring
    relationship_type: str    # "import", "function_call", etc.
    cache_age_seconds: float  # Age of cached snippet
    relevance_score: float    # 0.0-1.0 (future: prioritization)
    token_count: int          # Tokens in this snippet
```

**Context Injection Log Format (JSONL, FR-28):**

```json
{
  "timestamp": 1700000000.0,
  "event_type": "context_injection",
  "trigger": "agent_read_file",
  "trigger_file": "src/bot.py",
  "injected_context": [
    {
      "source_file": "src/retry.py",
      "lines": "120-135",
      "snippet": "def retry_with_backoff(func, max_attempts=3, base_delay=1.0):\n    \"\"\"Retry function with exponential backoff\"\"\"",
      "relationship_type": "import",
      "cache_age_seconds": 480.0,
      "relevance_score": 0.95,
      "token_count": 45
    }
  ],
  "total_token_count": 45,
  "cache_hit": true
}
```

---

#### 3.3.6 Session Metrics Model

**Session Metrics Structure (FR-43 through FR-49):**

```python
@dataclass
class SessionMetrics:
    """
    Comprehensive metrics emitted at session end.

    Enables data-driven threshold tuning (FR-44, FR-46, FR-49).
    """

    # Session metadata
    session_id: str
    session_start: float      # Unix timestamp
    session_end: float        # Unix timestamp
    session_duration_seconds: float

    # Configuration used
    config: Dict[str, any]    # Cache expiry, size limits, token limits

    # Cache performance (FR-46)
    cache_stats: Dict[str, any]

    # Context injection stats (FR-46)
    injection_stats: Dict[str, any]

    # Relationship graph stats (FR-46)
    graph_stats: Dict[str, any]

    # Re-read patterns (FR-46)
    reread_patterns: Dict[str, int]  # filepath → reread count

    # Performance metrics (FR-46)
    performance: Dict[str, any]

    # Warning statistics (FR-46)
    warning_stats: Dict[str, any]

# Detailed nested structures for session metrics

@dataclass
class CachePerformanceMetrics:
    """Cache performance metrics (FR-46)"""
    expiry_time_seconds: int      # Configured expiry time
    size_limit_kb: int            # Configured size limit
    hits: int
    misses: int
    hit_rate: float               # hits / (hits + misses)
    miss_rate: float              # 1 - hit_rate
    peak_size_bytes: int
    evictions_lru: int
    evictions_expiry: int
    actual_expiry_times: List[float]  # Distribution of actual ages when evicted

@dataclass
class InjectionPerformanceMetrics:
    """Context injection metrics (FR-46)"""
    token_limit: int              # Configured token limit
    total_injections: int
    injections_by_type: Dict[str, int]  # type → count
    token_counts: List[int]       # All token counts for distribution
    tokens_exceeding_300: int
    tokens_exceeding_500: int
    tokens_exceeding_700: int

@dataclass
class GraphStatistics:
    """Relationship graph statistics (FR-46)"""
    total_files: int
    total_relationships: int
    circular_dependency_count: int
    most_connected_files: List[Dict[str, any]]  # Top 10 files with dependency counts

@dataclass
class FunctionUsageDistribution:
    """Function usage distribution (FR-46)"""
    histogram: Dict[str, int]  # "1 file" → count, "2-3 files" → count, "4+ files" → count
    edited_functions: List[Dict[str, any]]  # List of edited functions with dependency counts

@dataclass
class PerformanceMetrics:
    """Performance timings (FR-46)"""
    parsing_times_ms: List[float]
    injection_latencies_ms: List[float]
    total_indexing_time_seconds: float

@dataclass
class WarningStatistics:
    """Warning statistics (FR-46)"""
    warning_counts: Dict[str, int]  # warning_type → count
    files_with_warnings: List[Dict[str, any]]  # Top 10 files with most warnings
```

**Complete Session Metrics JSON Format:**

```json
{
  "session_id": "1ea0f7d8",
  "session_start": 1700000000.0,
  "session_end": 1700014400.0,
  "session_duration_seconds": 14400.0,
  "config": {
    "cache_expiry_seconds": 600,
    "cache_size_limit_kb": 50,
    "token_injection_limit": 500
  },
  "cache_stats": {
    "expiry_time_seconds": 600,
    "size_limit_kb": 50,
    "hits": 143,
    "misses": 67,
    "hit_rate": 0.681,
    "miss_rate": 0.319,
    "peak_size_bytes": 48000,
    "evictions_lru": 3,
    "evictions_expiry": 12,
    "actual_expiry_times": {
      "min": 420.0,
      "max": 680.0,
      "median": 590.0,
      "p95": 640.0
    }
  },
  "injection_stats": {
    "token_limit": 500,
    "total_injections": 87,
    "injections_by_type": {
      "import": 65,
      "function_call": 22
    },
    "token_distribution": {
      "min": 25,
      "max": 480,
      "median": 120,
      "p95": 420,
      "mean": 145.3
    },
    "tokens_exceeding_300": 15,
    "tokens_exceeding_500": 0,
    "tokens_exceeding_700": 0
  },
  "graph_stats": {
    "total_files": 156,
    "total_relationships": 487,
    "circular_dependency_count": 2,
    "most_connected_files": [
      {"file": "src/utils.py", "dependency_count": 23},
      {"file": "src/retry.py", "dependency_count": 18}
    ]
  },
  "reread_patterns": {
    "src/bot.py": 8,
    "src/retry.py": 7,
    "src/config.py": 4
  },
  "performance": {
    "parsing_times_ms": {
      "min": 15.2,
      "max": 185.7,
      "median": 42.3,
      "p95": 120.5
    },
    "injection_latencies_ms": {
      "min": 5.1,
      "max": 38.2,
      "median": 12.5,
      "p95": 28.7
    },
    "total_indexing_time_seconds": 8.5
  },
  "warning_stats": {
    "warning_counts": {
      "dynamic_dispatch": 5,
      "circular_import": 2
    },
    "files_with_warnings": [
      {"file": "src/plugin_loader.py", "warning_count": 3}
    ]
  }
}
```

---

#### 3.3.7 Analysis Context Model

**Analysis Context (Shared State for Detectors):**

```python
@dataclass
class AnalysisContext:
    """
    Shared context passed to all relationship detectors.

    Built once per file analysis, used by all detectors.
    """

    filepath: str             # File being analyzed

    # Import map (built by ImportDetector, used by all call detectors)
    import_map: Dict[str, str]  # symbol → source_file
    # Example: {"retry_with_backoff": "src/retry.py", "os": "os"}

    # Module info
    module_name: Optional[str]

    # Scope tracking (for nested functions, classes)
    current_scope: List[str]

    # AST tree (for reference by detectors)
    ast_tree: any  # ast.Module (not serialized - transient only)
```

---

#### 3.3.8 Data Model Summary

**All Models at a Glance:**

| Model | Purpose | Serializable | Stored In |
|-------|---------|--------------|-----------|
| `Relationship` | File dependency | ✅ Yes (primitives) | RelationshipStore |
| `RelationshipGraph` | Bidirectional dependency index | Partial (indices in-memory, rels in store) | In-memory + Store |
| `FileMetadata` | File analysis metadata | ✅ Yes | RelationshipGraph |
| `CacheEntry` | Cached code snippet | ✅ Yes | WorkingMemoryCache |
| `CacheStatistics` | Cache performance metrics | ✅ Yes | MetricsCollector |
| `Warning` | Dynamic pattern warning | ✅ Yes | Log file (JSONL) |
| `SuppressionConfig` | Warning suppression config | ✅ Yes | Config file (YAML) |
| `ContextInjectionEvent` | Injection log entry | ✅ Yes | Log file (JSONL) |
| `SessionMetrics` | End-of-session metrics | ✅ Yes | Metrics file (JSON) |
| `AnalysisContext` | Detector shared state | ❌ No (contains AST) | Transient (per-analysis) |

**Key Design Principle (DD-4)**: All persistent models use primitives only (str, int, float, bool, List, Dict, Optional). Complex objects (AST nodes, networkx graphs) are NOT stored, ensuring easy serialization and v0.2.0 migration.

---

### 3.4 Component Design

This section describes the responsibilities, interfaces, and interactions of each major component in the system. The architecture follows the layered design from DD-6 (MCP Architecture) and DD-2 (Language-Agnostic Watcher).

#### 3.4.1 CrossFileContextMCPServer

**Responsibility**: Protocol layer that bridges the MCP protocol with the business logic layer.

**Key Operations**:
- Initialize MCP server and register tools (`read_with_context`, `get_relationship_graph`)
- Receive tool invocation requests from Claude Code
- Translate MCP requests to service calls
- Format service responses as MCP tool results
- Handle MCP server lifecycle (startup, shutdown, health checks)

**Dependencies**:
- Depends on: `CrossFileContextService` (business logic)
- Used by: Claude Code (MCP client)

**Configuration**:
- Server name: `"cross-file-context-links"`
- Protocol version: MCP 1.0
- Tool definitions per MCP specification

**Design Constraint (DD-6)**: This layer contains ZERO business logic. All analysis, caching, and context injection logic resides in `CrossFileContextService`. This enables clean separation for future backend extraction in v0.2.0.

---

#### 3.4.2 CrossFileContextService

**Responsibility**: Core business logic coordinator that owns all analytical components and orchestrates context injection workflow.

**Key Operations**:
- Initialize and coordinate all subsystems (analyzer, watcher, cache, store, warning system, metrics)
- Handle file read requests with context injection
- Provide relationship graph queries and export
- Manage component lifecycle and configuration

**Owned Components**:
- `PythonAnalyzer`: Performs Python file analysis
- `FileWatcher`: Monitors file system changes
- `WorkingMemoryCache`: Caches recently-read content
- `RelationshipStore`: Stores relationship graph
- `WarningSystem`: Detects and emits warnings
- `MetricsCollector`: Aggregates session metrics

**Key Interfaces**:
```python
# High-level operations exposed to MCP layer
read_file_with_context(file_path: str) -> ReadResult
get_relationship_graph() -> GraphExport
get_dependents(file_path: str) -> List[Relationship]
```

**Context Injection Workflow** (see DD-5):
1. Receive read request for `target_file`
2. Check cache for recent read of `target_file`
3. If cache miss: Read file from disk
4. Query relationship store for dependencies of `target_file`
5. For each dependency, check if cached (fresh within 10 min)
6. Assemble context snippets (location + signature only)
7. Return file content + injected context
8. Log injection event to metrics collector

**Configuration Parameters** (see FR-49):
- `cache_expiry_minutes`: Cache freshness threshold (default: 10)
- `cache_size_limit_kb`: Max cache size (default: 50)
- `context_token_limit`: Max tokens for injected context (default: 500)

**Design Constraint (DD-6)**: Service layer is storage-agnostic. Uses `RelationshipStore` interface (DD-4), allowing v0.2.0 to swap `InMemoryStore` → `SQLiteStore` with minimal changes.

---

#### 3.4.3 PythonAnalyzer

**Responsibility**: Language analyzer for Python files. Part of the language-agnostic analyzer layer from DD-2.

**Key Operations**:
- Parse Python files into AST (Abstract Syntax Tree)
- Coordinate detector plugins to extract relationships
- Handle parsing errors gracefully (EC-18)
- Track Python-specific metadata (imports, function definitions, class definitions)

**Detector Registry**:
- Maintains list of active `RelationshipDetector` plugins
- v0.1.0 default detectors: Import, FunctionCall, ClassInheritance, AliasedImport, ConditionalImport, WildcardImport
- v0.1.1+: Additional detectors can be registered (method chains, nested attributes)

**Interaction with FileWatcher** (DD-2):
- FileWatcher detects `.py` file change
- FileWatcher dispatches change event to `PythonAnalyzer`
- `PythonAnalyzer` re-parses file and updates relationship store

**Error Handling**:
- Syntax errors in Python file: Skip analysis, log warning, continue with other files (EC-18)
- Missing imports: Track relationship anyway (import may be dynamically added)
- Unresolved references: Track as "unresolved", emit informational warning

---

#### 3.4.4 Relationship Detectors

**Responsibility**: Plugin components that detect specific relationship patterns in AST. Implements the detector plugin pattern from DD-1.

**Base Interface**:
```python
class RelationshipDetector:
    """
    Base interface for relationship detection plugins.
    Each detector focuses on one relationship pattern type.
    """
    def detect(self, ast_node, file_path: str) -> List[Relationship]:
        """
        Analyze AST node and return detected relationships.
        Returns empty list if pattern not found.
        """
```

**v0.1.0 Detectors**:

1. **ImportDetector**:
   - Detects: `import module`, `from module import name`
   - Handles: Standard library imports, relative imports (`.` and `..`)
   - Output: IMPORT relationships

2. **FunctionCallDetector**:
   - Detects: Simple function calls `function_name(args)`
   - Limitation (DD-1): v0.1.0 handles ONLY simple calls, not method chains or nested attributes
   - Output: FUNCTION_CALL relationships

3. **ClassInheritanceDetector**:
   - Detects: `class ChildClass(ParentClass):`
   - Handles: Single and multiple inheritance
   - Output: INHERITANCE relationships

4. **AliasedImportDetector**:
   - Detects: `import foo as bar`, `from foo import baz as qux`
   - Tracks: Original name and alias (EC-3)
   - Output: IMPORT relationships with alias metadata

5. **ConditionalImportDetector**:
   - Detects: `if TYPE_CHECKING:`, `if sys.version_info >= ...:`
   - Tracks: Conditional nature in metadata (EC-5)
   - Output: IMPORT relationships marked as conditional

6. **WildcardImportDetector**:
   - Detects: `from module import *`
   - Limitation (EC-4): Tracks at module level only, cannot track specific function usage
   - Output: IMPORT relationships marked as wildcard
   - Optional warning: Configurable via `warn_on_wildcards` setting (default: false)

**v0.1.1+ Detectors** (incremental additions per DD-1):
- `MethodChainDetector`: `obj.method().another()`
- `NestedAttributeDetector`: `module.submodule.function()`

**Design Principle (DD-1)**: Each detector is independent and stateless. New relationship patterns can be supported by adding new detector plugins without modifying existing detectors.

---

#### 3.4.5 FileWatcher

**Responsibility**: Language-agnostic file system monitoring. Implements the watcher layer from DD-2.

**Key Operations**:
- Monitor project directory for file system events (create, modify, delete)
- Filter events based on file extension and ignore patterns
- Dispatch events to appropriate language analyzer
- Handle rapid successive changes (debouncing/throttling)

**File Extension Routing** (DD-2):
- `.py` files → `PythonAnalyzer`
- Future: `.ts`, `.js` → `TypeScriptAnalyzer` (v0.3.0)
- Future: `.go` → `GoAnalyzer` (v0.4.0)

**Ignore Patterns** (NFR-7, NFR-8):
- Respect `.gitignore` patterns
- Always ignore: `.git/`, `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `node_modules/`
- Configurable additional patterns via `.cross_file_context_links.yml`

**Event Processing**:
- **Create**: Analyze new file, add to relationship graph
- **Modify**: Re-analyze file, update relationships, invalidate cache entries
- **Delete**: Remove from graph, evict from cache, warn on broken references (EC-14)

**Throttling Strategy**:
- Debounce rapid changes (wait 200ms of silence before processing)
- Batch multiple file changes into single analysis pass
- Priority queue: User-edited files processed before bulk changes

**Design Constraint (DD-2)**: FileWatcher has ZERO knowledge of Python, TypeScript, or any specific language. It only knows file extensions and dispatch rules. This enables adding new languages without modifying the watcher.

---

#### 3.4.6 WorkingMemoryCache

**Responsibility**: LRU cache for recently-read file content to reduce redundant re-reads.

**Key Operations**:
- Store file content snippets with timestamps
- Retrieve cached content if fresh (within 10 minutes of last access)
- Evict least-recently-used entries when size limit exceeded
- Invalidate entries when source file modified
- Track cache statistics (hit rate, miss rate, size)

**Cache Key Structure**:
- Primary key: file path
- Secondary key: line range (for function/class snippets)
- Example: `("/path/to/file.py", (10, 25))` caches lines 10-25

**Cache Entry Fields** (see Section 3.3.3):
- `content`: str (file content or snippet)
- `timestamp`: float (Unix epoch, last access time)
- `file_path`: str
- `line_range`: Optional[Tuple[int, int]]
- `metadata`: Dict (file size, hash for staleness detection)

**Expiry Policy** (FR-14):
- Default: 10 minutes from last access
- Configurable via `cache_expiry_minutes` parameter
- Rationale: Balance between freshness and re-read reduction (see PRD Section 7.2 for data-driven threshold tuning)

**Size Limit** (FR-16):
- Default: 50KB per session
- Configurable via `cache_size_limit_kb` parameter
- Eviction: LRU (least-recently-used) when limit exceeded

**Invalidation Triggers**:
- File modified (detected by FileWatcher)
- File deleted (detected by FileWatcher)
- Manual cache clear (via configuration or user command)

**Statistics Tracked**:
- Total reads, cache hits, cache misses
- Hit rate percentage
- Current cache size (bytes)
- Peak cache size during session
- Entries evicted due to size limit vs. expiry

---

#### 3.4.7 RelationshipStore

**Responsibility**: Storage abstraction for the relationship graph. Implements DD-4 (Persistence Architecture).

**Interface**:
```python
class RelationshipStore:
    """
    Abstract storage interface for relationship graph.
    Enables swapping storage backend without changing business logic.
    """
    def add_relationship(self, rel: Relationship) -> None
    def remove_relationship(self, rel: Relationship) -> None
    def get_relationships(self, file_path: str) -> List[Relationship]
    def get_all_relationships(self) -> List[Relationship]
    def export_graph(self) -> GraphExport
```

**v0.1.0 Implementation: InMemoryStore**:
- Stores relationships in-memory using Python dict
- No persistence across sessions (data lost on restart)
- Fast lookups optimized for frequent queries
- Export to JSON format for external analysis (FR-23, FR-25)

**v0.2.0 Implementation: SQLiteStore** (future):
- Persists relationships to SQLite database
- Survives session restarts
- Enables multi-session analysis and history tracking
- **Migration path (DD-4)**: Service layer changes only 1 line:
  ```python
  # v0.1.0
  store = InMemoryStore()

  # v0.2.0
  store = SQLiteStore(db_path=".cross_file_context.db")
  ```

**Graph Export Format** (FR-23, FR-25):
- JSON structure containing:
  - All relationships with metadata
  - File paths (absolute or project-relative)
  - Relationship types
  - Timestamps
  - Graph-level metadata (version, project info)
- Enables external tools to analyze dependencies
- Machine-parseable for automated analysis

---

#### 3.4.8 WarningSystem

**Responsibility**: Detect dynamic Python patterns that cannot be statically analyzed, emit warnings to inform users of limitations.

**Key Operations**:
- Detect unhandled dynamic patterns during AST analysis (EC-6 through EC-10)
- Determine if file is test module or source module (DD-3)
- Check warning suppression configuration
- Emit structured warnings with file path, line number, pattern type, explanation
- Log warnings to structured format for analysis

**Test vs Source Module Detection** (DD-3, FR-32):
- **Test modules**: Files matching patterns:
  - `**/test_*.py`
  - `**/*_test.py`
  - `**/tests/**/*.py`
  - `**/conftest.py`
- **Source modules**: All other `.py` files
- **Behavior**: Many warnings suppressed in test modules (mocking, dynamic dispatch common in tests)

**Detected Patterns and Warning Logic**:

1. **Dynamic Dispatch** (FR-33, EC-6):
   - Pattern: `getattr(obj, dynamic_name)()`
   - Warning in source modules: "⚠️ Dynamic dispatch detected..."
   - Suppressed in test modules

2. **Monkey Patching** (FR-34, EC-7):
   - Pattern: `module.attr = replacement`
   - Warning in source modules: "⚠️ Monkey patching detected..."
   - Suppressed in test modules (expected for mocking)

3. **exec/eval** (FR-35, EC-9):
   - Pattern: `exec(code_string)`, `eval(expression)`
   - Warning in source modules: "⚠️ Dynamic code execution detected..."
   - Suppressed in test modules

4. **Complex Decorators** (FR-36, EC-8):
   - Pattern: Custom decorators with dynamic features
   - Informational warning: "ℹ️ Decorator may modify function behavior..."
   - Common test decorators (`@pytest.mark`, `@unittest.skip`) suppressed

5. **Metaclasses** (FR-37, EC-10):
   - Pattern: `class Foo(metaclass=CustomMeta):`
   - Informational warning: "ℹ️ Metaclass detected, runtime behavior may differ..."

6. **Circular Imports** (FR-30, EC-1):
   - Pattern: File A imports B, B imports A
   - Warning always emitted: "⚠️ Circular import detected: A → B → A..."
   - Note: Python allows these but Google Style Guide discourages

**Warning Message Format** (FR-38):
- All warnings include: file path, line number, pattern type, explanation
- Machine-parseable structure:
  ```json
  {
    "type": "dynamic_dispatch",
    "file": "src/module.py",
    "line": 42,
    "message": "Dynamic dispatch detected: getattr(obj, 'method')()",
    "severity": "warning",
    "timestamp": "2025-11-25T10:30:00Z"
  }
  ```

**Suppression Configuration** (FR-39, FR-40):
- Configuration file: `.cross_file_context_links.yml`
- File-level suppression: `suppress_warnings: ["path/to/file.py"]`
- Directory-level suppression: `suppress_warnings: ["tests/**/*"]`
- Pattern-type suppression: `suppress_dynamic_dispatch_warnings: true`

**Warning Logging** (FR-41):
- All warnings logged to `.jsonl` file (one JSON object per line)
- Log location: `.cross_file_context_logs/warnings.jsonl`
- Enables offline analysis and filtering

**Fail-Safe Principle** (FR-42):
- System does NOT attempt to track relationships for unhandled dynamic patterns
- Unhandled patterns marked as "untrackable" in relationship graph metadata
- Never add incorrect relationships to graph

---

#### 3.4.9 MetricsCollector

**Responsibility**: Aggregate session metrics and log context injection events for analysis and threshold tuning.

**Key Operations**:
- Log all context injection events (FR-26, FR-27)
- Aggregate session-level metrics (FR-43, FR-44)
- Export metrics at end of session (FR-45)
- Provide query API for recent events (FR-29)

**Context Injection Logging** (FR-26, FR-27):
- Log format: JSONL (one JSON object per line)
- Log location: `.cross_file_context_logs/injections.jsonl`
- Fields per injection event:
  - `timestamp`: ISO 8601 timestamp
  - `source_file`: File providing context
  - `target_file`: File being read
  - `relationship_type`: IMPORT, FUNCTION_CALL, etc.
  - `snippet`: Injected content (location + signature)
  - `cache_age_seconds`: Age of cached snippet (null if not cached)
  - `token_count`: Approximate token count of snippet
  - `context_token_total`: Total tokens injected for this read

**Session Metrics** (FR-43, FR-44, FR-46):
- Metrics written to `.cross_file_context_logs/session_metrics.jsonl`
- Metrics structure:
  ```json
  {
    "session_id": "uuid",
    "start_time": "ISO timestamp",
    "end_time": "ISO timestamp",
    "cache_performance": {
      "hit_rate": 0.75,
      "miss_rate": 0.25,
      "total_reads": 1000,
      "cache_hits": 750,
      "cache_misses": 250,
      "peak_size_kb": 48.2,
      "average_expiry_seconds": 420
    },
    "context_injection": {
      "total_injections": 500,
      "token_counts": {
        "min": 10,
        "max": 480,
        "median": 150,
        "p95": 420
      },
      "threshold_exceedances": 3
    },
    "relationship_graph": {
      "total_files": 150,
      "total_relationships": 450,
      "most_connected_files": [
        {"file": "utils.py", "dependency_count": 45},
        {"file": "base.py", "dependency_count": 32}
      ]
    },
    "function_usage_distribution": {
      "1-3_files": 120,
      "4-10_files": 25,
      "11+_files": 5
    },
    "re_read_patterns": [
      {"file": "config.py", "read_count": 15},
      {"file": "utils.py", "read_count": 12}
    ],
    "performance": {
      "parsing_time_ms": {"min": 5, "max": 150, "median": 20, "p95": 80},
      "injection_latency_ms": {"min": 2, "max": 45, "median": 10, "p95": 30}
    },
    "warnings": {
      "total_warnings": 8,
      "by_type": {
        "circular_import": 2,
        "dynamic_dispatch": 3,
        "monkey_patching": 1,
        "exec_eval": 2
      },
      "files_with_most_warnings": [
        {"file": "legacy.py", "warning_count": 4}
      ]
    }
  }
  ```

**Metrics Anonymization** (FR-47):
- No sensitive code snippets in metrics
- File paths optionally anonymized (hash-based)
- Metrics safe for aggregation across sessions

**Configuration Adjustability** (FR-49):
- All thresholds configurable via `.cross_file_context_links.yml`:
  - `cache_expiry_minutes`
  - `cache_size_limit_kb`
  - `context_token_limit`
- Metrics include actual configured values used during session

**Metrics Analysis Tool** (FR-48):
- Separate script: `analyze_metrics.py`
- Reads session metrics JSONL files
- Produces summary statistics
- Identifies normal vs. outlier patterns
- Suggests optimal configuration values based on observed data

---

### 3.5 Relationship Detection

This section describes how the system analyzes Python source code to extract cross-file relationships.

#### 3.5.1 AST Parsing Pipeline

**Overview**: The relationship detection pipeline transforms Python source code into relationship records stored in the relationship graph.

**Pipeline Stages**:

1. **File Reading**:
   - Read `.py` file from disk
   - Decode using UTF-8 (standard Python encoding)
   - Preserve line number information for error reporting

2. **AST Parsing**:
   - Parse file into Abstract Syntax Tree using Python's `ast` module
   - Parsing mode: `ast.parse(source, filename, mode='exec')`
   - Preserve node location info (line number, column offset) for warnings
   - **Timeout limit**: 5 seconds per file (configurable via `ast_parsing_timeout_seconds`)
     - If parsing exceeds timeout: Skip file, log warning, continue with other files
     - Rationale: Prevent DoS from maliciously complex files

3. **Detector Dispatch**:
   - Traverse AST nodes top-to-bottom
   - For each node, invoke all registered detectors in priority order
   - Each detector returns 0 or more `Relationship` objects
   - Aggregate all detected relationships
   - **Recursion depth limit**: 100 levels (configurable via `ast_max_recursion_depth`)
     - If depth exceeded: Skip subtree, log warning, continue with sibling nodes
     - Rationale: Prevent stack overflow and DoS from deeply nested expressions (e.g., `((((...))))`)

4. **Relationship Storage**:
   - Deduplicate relationships (same source, target, type, line)
   - Store in `RelationshipStore`
   - Update bidirectional indexes for efficient queries

**Error Recovery** (EC-18):
- **Syntax Errors**: If `ast.parse()` fails, skip file analysis, log warning, continue with other files
- **Encoding Errors**: Try UTF-8 first, fallback to latin-1, log warning if non-UTF-8
- **Import Errors**: Track relationship even if imported module doesn't exist (may be added later)
- **Partial Analysis**: If some detectors fail, store partial results from successful detectors

**Performance Considerations**:
- Parse each file once, run all detectors on single AST traversal
- Cache AST for 200ms to handle rapid successive edits (debouncing)
- Target: <200ms parsing time for files <5,000 lines (NFR-1)

---

#### 3.5.2 Supported Relationship Types

This subsection details each relationship pattern detected in v0.1.0.

**3.5.2.1 Import Relationships**

**Patterns Detected**:
- `import module`
- `import package.submodule`
- `from module import name`
- `from package import submodule`
- Relative imports: `from . import name`, `from .. import name`

**Relationship Output**:
- Type: `IMPORT`
- Source: File containing import statement
- Target: Imported module (resolved to file path if possible)
- Line number: Location of import statement
- Metadata: Import style (`import` vs `from...import`), imported names

**Module Resolution**:

**Resolution Order** (matches Python's import search order):

For `import module_name` or `from module_name import ...`, resolve in this order:

1. **Same directory**: Check for `module_name.py` in same directory as importing file
2. **Same directory package**: Check for `module_name/__init__.py` in same directory
3. **Parent packages** (up to project root): Walk up directory tree, checking each ancestor
   - For each ancestor directory: Check `module_name.py` and `module_name/__init__.py`
   - Stop at project root boundary (don't search outside project)
4. **Third-party (site-packages)**: Track but don't resolve (outside project scope)
5. **Standard library**: Track but don't resolve (no local file to link)

**Ambiguity Handling**:

When both `utils.py` and `utils/__init__.py` exist in same directory:
- **Resolution**: Prefer `utils.py` (Python's behavior: module file shadows package)
- **Rationale**: Match Python's actual import behavior to minimize surprises
- **Test coverage**: Add test case in Section 2.4 verifying this precedence

**Relative Imports**:

- `from . import name`: Resolve relative to importing file's directory
- `from .. import name`: Resolve relative to parent directory
- `from ..sibling import name`: Resolve relative to parent, then into sibling package
- Relative imports only valid inside packages (directory with `__init__.py`)

**Special Cases**:

- **Standard library imports**: Track relationship but mark target as `<stdlib:module_name>`
  - Examples: `import os`, `from collections import defaultdict`
  - Rationale: No file path to link, but relationship is still meaningful for context
- **Third-party imports**: Track relationship but mark target as `<third-party:package_name>`
  - Examples: `import requests`, `from flask import Flask`
  - Detection: If not found in project and not in stdlib list
- **Unresolved imports**: Track as `<unresolved:module_name>`
  - May be resolved later if file created during editing session
  - May indicate dynamic imports or missing dependencies

**3.5.2.2 Function Call Relationships**

**Patterns Detected (v0.1.0)**:
- Simple function calls: `function_name(args)`
- Module-qualified calls: `module.function(args)` (if module imported)

**Patterns NOT Detected (v0.1.0)**:
- Method chains: `obj.method().another()` (deferred to v0.1.1, see DD-1)
- Nested attributes: `module.submodule.function()` (deferred to v0.1.2)
- Dynamic calls: `getattr(obj, name)()` (cannot be statically analyzed, see EC-6)

**Relationship Output**:
- Type: `FUNCTION_CALL`
- Source: File containing call
- Target: File defining called function (if resolvable)
- Line number: Location of call statement
- Metadata: Function name, call context (in function X, in class Y)

**Function Resolution**:

**Resolution Order** (matches Python scope semantics):

When encountering a function call `foo()`, resolve in this order:

1. **Local scope**: Check if `foo` defined in current file
   - If function `foo` defined locally, link to local definition
   - Takes precedence over imports (Python behavior: local shadows imported)

2. **Imported names**: Check if `foo` imported in current file
   - Look up import statement: `from module import foo` or `import module` + `module.foo`
   - Resolve to defining file based on import target

3. **Built-in functions**: Check if `foo` is Python built-in
   - Examples: `len()`, `print()`, `isinstance()`
   - Track relationship but mark as `<builtin:foo>` (no file to link)

4. **Unresolved**: If not found in above
   - Mark as `<unresolved:foo>`
   - May indicate missing import, dynamic behavior, or error in code

**Name Shadowing Handling**:

The system uses **Python semantics (last definition wins)**:

- **Multiple imports with same name**:
  ```python
  from retry import retry_with_backoff
  from utils import retry_with_backoff  # This wins
  retry_with_backoff()  # → Resolves to utils.retry_with_backoff
  ```
  - **Behavior**: Last import wins (Python overwrites the name)
  - **Assumption**: Code is linted with flake8/ruff (F811 prevents this)

- **Local definition shadows import**:
  ```python
  from retry import retry_with_backoff
  def retry_with_backoff():  # This wins
      pass
  retry_with_backoff()  # → Resolves to local definition
  ```
  - **Behavior**: Local definition wins (Python overwrites imported name)
  - **Assumption**: Code is linted (F811 prevents this)

- **Multiple local definitions**:
  ```python
  def foo():
      pass
  def foo():  # This wins
      pass
  ```
  - **Behavior**: Last definition wins
  - **Assumption**: Code is linted (F811 prevents this)

**Code Quality Requirement**:
- See Section 1.1 "Code Quality Assumptions"
- System assumes well-linted code without shadowing issues
- With unlinted code: Tracking may be incorrect but matches Python runtime behavior

**Alternative Approach**:
- See Section 3.5.6 for interpreter inspection alternative (v0.2.0+ potential enhancement)
- Current approach: AST-based resolution (safe, fast, no code execution)
- Future option: Interpreter inspection fallback for ambiguous cases
- Metrics in Section 3.10.1 track resolution effectiveness to inform future decisions

**3.5.2.3 Class Inheritance Relationships**

**Patterns Detected**:
- Single inheritance: `class Child(Parent):`
- Multiple inheritance: `class Child(Parent1, Parent2):`
- Nested inheritance: `class Child(package.module.Parent):`

**Relationship Output**:
- Type: `INHERITANCE`
- Source: File containing child class
- Target: File defining parent class (if resolvable)
- Line number: Class definition line
- Metadata: Child class name, parent class name(s), inheritance order

**3.5.2.4 Aliased Import Relationships** (EC-3)

**Patterns Detected**:
- Module alias: `import module as alias`
- Name alias: `from module import name as alias`

**Relationship Output**:
- Type: `IMPORT`
- Source: File containing import
- Target: Imported module
- Metadata: **Original name** and **alias** both tracked
  - Example: `from retry import retry_with_backoff as retry` → track both names

**Usage Tracking**:
- When detecting function calls, match against both original name and alias
- Example: If `retry` called, recognize it refers to `retry_with_backoff`

**3.5.2.5 Conditional Import Relationships** (EC-5)

**Patterns Detected**:
- Type checking imports: `if TYPE_CHECKING: from typing import ...`
- Version-conditional imports: `if sys.version_info >= (3, 8): import module`

**Relationship Output**:
- Type: `IMPORT`
- Metadata: `conditional: true`, condition expression
- Interpretation: Import exists only at type-checking time or under certain runtime conditions

**3.5.2.6 Wildcard Import Relationships** (EC-4)

**Patterns Detected**:
- `from module import *`

**Relationship Output**:
- Type: `IMPORT`
- Target: Module (module-level tracking only)
- Metadata: `wildcard: true`
- **Limitation**: Cannot track which specific names are used from the module

**Warning Behavior**:
- Optional warning: Configurable via `warn_on_wildcards` (default: false)
- Rationale: Google Style Guide discourages but Google's pylintrc disables warning (pragmatic)
- Context injection note: "Note: This file uses `from X import *`, specific function tracking unavailable"

---

#### 3.5.3 Incremental Detection Capabilities

**Design Principle (DD-1)**: Implement simple patterns first, add complexity incrementally through detector plugins.

**v0.1.0 Scope**:
- Simple function calls: `function_name(args)`
- Direct imports and aliased imports
- Class inheritance
- Conditional and wildcard imports (with limitations)

**v0.1.1 Planned Additions**:
- **Method chains**: `obj.method().another()`
  - New detector: `MethodChainDetector`
  - Tracks chained method calls as separate relationships
  - Example: `client.connect().send()` → track both `connect()` and `send()`

**v0.1.2 Planned Additions**:
- **Nested attributes**: `module.submodule.function()`
  - New detector: `NestedAttributeDetector`
  - Handles deeply nested module paths
  - Example: `utils.helpers.retry()` → resolve full path

**v0.2.0 Planned Additions**:
- **Decorator analysis**: Analyze decorator logic to understand behavior modifications
- **Context manager usage**: Track `with` statement usage
- **Generator relationships**: Track `yield from` relationships

**Migration Path**: Each version adds new detector plugins without modifying existing detectors. Existing relationship graph remains valid, new relationships are additive.

---

#### 3.5.4 Unhandled Dynamic Patterns

**Design Principle (FR-42, Fail-Safe)**: When pattern cannot be statically analyzed, emit warning but do NOT track incorrectly. Mark as "untrackable" in metadata.

**3.5.4.1 Dynamic Imports** (EC-2)

**Pattern**: `importlib.import_module(variable_name)`

**Detection**:
- AST node: `Call` with `func` = `Attribute(value=Name(id='importlib'), attr='import_module')`
- Check if first argument is `Name` or `Constant` (variable vs literal string)

**Handling**:
- If variable: Cannot resolve at static analysis time
- Warning: "⚠️ Dynamic import detected: `importlib.import_module({var})` - relationship tracking unavailable"
- Mark in metadata: `"untrackable_patterns": ["dynamic_import"]`
- Do NOT add relationship to graph

**3.5.4.2 Dynamic Dispatch** (EC-6, FR-33)

**Pattern**: `getattr(obj, dynamic_name)()`

**Detection**:
- AST node: `Call` where `func` is `Call` to `getattr`
- Check if second argument to `getattr` is variable vs constant

**Handling**:
- If variable: Cannot determine which function will be called
- Warning in **source modules**: "⚠️ Dynamic dispatch detected in {file}:{line} - relationship tracking unavailable for `getattr(obj, '{name}')`"
- **No warning in test modules** (common pattern in test frameworks)
- Mark in metadata: `"untrackable_patterns": ["dynamic_dispatch"]`

**Test vs Source Distinction** (DD-3):
- Test module patterns: `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`, `**/conftest.py`
- Source modules: All other `.py` files

**3.5.4.3 Monkey Patching** (EC-7, FR-34)

**Pattern**: `module.attr = replacement` (runtime reassignment)

**Detection**:
- AST node: `Assign` where target is `Attribute` (e.g., `module.function`)
- Distinguish from initial definition vs reassignment

**Handling**:
- Warning in **source modules**: "⚠️ Monkey patching detected in {file}:{line} - `{module}.{attr}` reassigned, relationship tracking may be inaccurate"
- **No warning in test modules** (expected for mocking)
- Track original definition only, not runtime replacement
- Mark in metadata: `"untrackable_patterns": ["monkey_patching"]`

**3.5.4.4 exec/eval** (EC-9, FR-35)

**Pattern**: `exec(code_string)`, `eval(expression_string)`

**Detection**:
- AST node: `Call` with `func` = `Name(id='exec')` or `Name(id='eval')`

**Handling**:
- Warning in **source modules**: "⚠️ Dynamic code execution detected in {file}:{line} - `exec()`/`eval()` prevents static analysis, relationships may be incomplete"
- **No warning in test modules** (sometimes used in testing edge cases)
- Mark file in metadata: `"contains_dynamic_execution": true`
- Consider increased re-read frequency for files with exec/eval (less trust in cached snippets)

**3.5.4.5 Decorators** (EC-8, FR-36)

**Pattern**: `@decorator_name` before function/class definition

**Detection**:
- AST node: `FunctionDef` or `ClassDef` with non-empty `decorator_list`

**Handling**:
- Track decorated function/class definition
- Track decorator as dependency if imported from another module
- Metadata: List of decorator names
- Warning for complex decorators: "ℹ️ Decorator `{decorator_name}` in {file}:{line} may modify function behavior - tracking original definition only"
- **No warning for common test decorators**: `@pytest.mark.*`, `@unittest.skip`, `@mock.patch`

**3.5.4.6 Metaclasses** (EC-10, FR-37)

**Pattern**: `class Foo(metaclass=CustomMeta):`

**Detection**:
- AST node: `ClassDef` with `keywords` containing `keyword(arg='metaclass')`

**Handling**:
- Track class definition
- Track metaclass as dependency if imported
- Metadata: Metaclass name
- Informational warning: "ℹ️ Metaclass detected in {file}:{line} - class `{name}` uses metaclass `{metaclass}`, runtime behavior may differ from static definition"

---

#### 3.5.5 Circular Dependency Detection - DEFERRED to v0.1.1+

**Original Problem** (EC-1): Python allows circular imports, which can cause subtle runtime errors and are discouraged by Google Python Style Guide (3.19.14).

**Decision: Defer cycle detection to v0.1.1+**

**Rationale for Deferral:**

1. **No infinite loop risk from graph operations**:
   - All graph query operations use O(1) bidirectional index lookups:
     - `get_dependencies(file)` → Dict[str, Set[str]] lookup
     - `get_dependents(file)` → Dict[str, Set[str]] lookup
   - Context injection queries these indices directly - no recursive traversal
   - **Cycle detection would be the ONLY deep traversal algorithm in v0.1.0**
   - The original concern (FR-6: "handle circular dependencies without infinite loops") is moot because there are no deep traversals to loop infinitely

2. **Cost vs benefit analysis**:
   - **Cost**: Running DFS (depth-limited to 50 levels) after EVERY import relationship addition
     - During initial indexing: 1,000 files × ~5 imports/file = 5,000 DFS runs
     - Each DFS: O(n) in graph size in worst case
   - **Benefit**: Code quality warning (linting concern, not correctness issue)
   - Python handles circular imports at runtime; this is not a functional requirement for the MCP server

3. **Alternative approach if needed in future**:
   - Batch cycle detection: Run once after initial indexing completes (not per-import)
   - Or use Tarjan's strongly connected components algorithm (O(V+E) for entire graph)
   - Defer to v0.1.1+ when users request this feature

**What FR-6 originally tried to prevent**:
- The original concern was that graph traversals could loop infinitely if cycles exist
- Analysis shows: We don't do graph traversals in normal operation
- Only queries are shallow index lookups

**Conclusion**: Cycle detection adds complexity without addressing any actual infinite loop risk. Defer as a nice-to-have code quality feature for v0.1.1+.

---

#### 3.5.6 Alternative Approach: Interpreter Inspection (Future Enhancement)

**Current Approach (v0.1.0)**: AST-based static analysis

**Alternative Considered**: Python interpreter inspection for symbol resolution

**How Interpreter Inspection Would Work:**

Instead of parsing AST to infer relationships, dynamically import modules and inspect runtime state:

```python
import importlib
import inspect

# Load module into interpreter
spec = importlib.util.spec_from_file_location("bot", "/path/to/bot.py")
bot_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_module)

# Inspect symbol resolution
func = bot_module.retry_with_backoff
source_file = inspect.getsourcefile(func)  # Returns actual file path
module = inspect.getmodule(func)
```

**Advantages:**
- **Automatic correctness**: Leverages Python's own resolution logic
- **No ambiguity**: Interpreter has already resolved all imports, shadowing, aliases
- **Simpler implementation**: No need to replicate complex Python semantics
- **Future-proof**: Works with new Python features automatically
- **Handles all edge cases**: Relative imports, sys.path manipulation, namespace packages

**Disadvantages:**
- **Side effects**: Importing executes top-level code (file I/O, network, DB connections)
- **Security risk**: Untrusted code could execute arbitrary operations
- **Import failures**: Syntax errors, missing dependencies block analysis
- **Performance**: Module initialization overhead for 1,000+ files
- **Environment dependencies**: Requires correct virtualenv, installed packages
- **Isolation needed**: Subprocess sandboxing, timeouts, resource limits

**Decision for v0.1.0: AST-First Approach**

Use AST-based static analysis as primary method (DD-8):

**Rationale**:
1. **Safety**: No code execution, no side effects
2. **Robustness**: Works on incomplete code, missing dependencies
3. **Performance**: Fast analysis without import overhead
4. **Target use case**: Code generated by Claude Code
   - Can set requirements on generated code (well-linted, no shadowing)
   - Code quality assumptions documented in Section 1.1
5. **Fail-safe principle**: Better to skip edge cases than execute untrusted code

**Potential Future Enhancement (v0.2.0+):**

Add interpreter inspection as **optional fallback** for ambiguous cases:

```python
def resolve_function_call(name, file):
    # 1. Try AST-based resolution (fast, safe)
    result = ast_resolve(name, file)

    if result.is_ambiguous and user_config.enable_interpreter_fallback:
        # 2. Try interpreter inspection (slower, accurate)
        try:
            result = interpreter_resolve(name, file, timeout=5s, sandbox=True)
        except (ImportError, TimeoutError, SecurityError):
            # Fall back to AST result
            pass

    return result
```

**Metrics to Guide Future Decision:**

Track effectiveness of AST-based resolution to determine if interpreter fallback is needed:

- **Identifier resolution rates** (see Section 3.10.3):
  - Percentage traced to immediate imports
  - Percentage unresolved
  - Percentage of unresolved identifiers actually needed for context injection

- **Context injection relevance**:
  - How often do unresolved identifiers block useful context?
  - Cost/benefit of interpreter inspection

If metrics show AST resolution is insufficient (e.g., >10% of context injections blocked by unresolved identifiers), consider adding interpreter fallback in v0.2.0+.

---

### 3.6 File Watcher and Change Detection

This section describes the file system monitoring subsystem that detects changes and triggers incremental analysis.

#### 3.6.1 File System Monitoring

**Library Choice**:
- **Recommended**: `watchdog` Python library
  - Cross-platform (macOS, Linux, Windows)
  - Well-maintained, stable API
  - Handles platform-specific quirks (FSEvents on macOS, inotify on Linux, ReadDirectoryChangesW on Windows)
- **Alternative**: OS-native APIs via Python bindings
  - Lighter weight but platform-specific code required
  - Deferred to v0.2.0+ if performance issues arise

**Monitored Directory**:
- Root: Project directory (where `.git/` exists or user-specified root)
- Recursive: Watch all subdirectories except ignored patterns

**Event Types Handled**:

FileWatcher performs **timestamp updates only** - no immediate analysis or cache invalidation. Analysis and cache refresh are demand-driven (triggered on cache read).

1. **File Create**:
   - New `.py` file added to project
   - Action: Add entry to `file_event_timestamps` with current timestamp
   - Thread-safe: Simple dict write (GIL ensures atomicity)

2. **File Modify**:
   - Existing `.py` file edited
   - Action: Update `file_event_timestamps[filepath]` with current timestamp
   - Thread-safe: Simple dict write (GIL ensures atomicity)

3. **File Delete**:
   - `.py` file removed from project
   - Action: Update `file_event_timestamps[filepath]` with current timestamp
   - Note: Entry persists in timestamp dict (acceptable memory overhead)

4. **File Move/Rename**:
   - Treated as Delete event followed by Create event
   - Old filepath: Update timestamp (marks as deleted)
   - New filepath: Add timestamp (marks as created)

**Ignored Patterns** (NFR-7, NFR-8):

**Always Ignored**:
- `.git/` directory (Git internals)
- `__pycache__/` directories (Python bytecode cache)
- `*.pyc`, `*.pyo` files (compiled Python)
- `.venv/`, `venv/`, `env/` (virtual environments)
- `node_modules/` (JavaScript dependencies)
- `.tox/`, `.pytest_cache/`, `.mypy_cache/` (tool caches)

**Respect `.gitignore`**:
- Parse `.gitignore` file in project root
- Apply ignore patterns to file watcher
- Rationale: Files ignored by Git typically not relevant for analysis (build artifacts, dependencies, etc.)

**User-Configurable Ignore**:
- Configuration file: `.cross_file_context_links.yml`
- Field: `ignore_patterns: ["pattern1", "pattern2"]`
- Example: `ignore_patterns: ["generated/**/*.py", "vendor/*.py"]`

---

#### 3.6.2 Change Event Processing

**Simplified Event Processing** (No Debouncing or Batching):

FileWatcher uses a **timestamp-only** approach with demand-driven analysis:

**Event Processing Flow**:
1. FileWatcher receives file system event (create, modify, delete)
2. FileWatcher updates `file_event_timestamps[filepath] = time.time()`
3. **Done** - No analysis, no cache invalidation, no graph updates

**Why No Debouncing**:
- Timestamp updates are cheap (microseconds)
- Multiple rapid edits → multiple timestamp updates → last write wins
- Analysis happens on-demand when cache reads the file
- Simpler design, no timer management

**Why No Batching**:
- Bulk operations (e.g., `git checkout`) → many timestamp updates
- Each update is fast, no performance concern
- Files only analyzed when actually read by cache

**Thread Safety**:
- FileWatcher thread: Writes to `file_event_timestamps` (dict write is GIL-protected)
- Cache thread: Reads from `file_event_timestamps` (dict read is GIL-protected)
- No explicit locking needed for simple dict operations
- Comment in code: `# Thread-safe: GIL ensures atomicity for dict operations`

**Event Filtering**:
- Only track events for supported file types (`.py` in v0.1.0)
- Ignore patterns applied before timestamp update (see Section 3.6.1)
- If file type not supported: Skip event silently

**Error Handling**:
- If OS file watcher fails: Log error, attempt to restart watcher
- If watcher cannot restart: Fall back to polling (check mtime periodically)
- Graceful degradation: System continues operating with degraded performance

---

#### 3.6.3 Incremental Updates

**Relationship Graph Invalidation**:

**On File Modification**:
1. Query relationship graph for all relationships where `source_file == modified_file`
2. Remove these relationships from graph (old definitions no longer valid)
3. Re-analyze modified file to detect new relationships
4. Add new relationships to graph
5. Update bidirectional indexes

**Dependent File Considerations**:
- If modified file contains function `foo()` used by 10 other files:
  - Relationships FROM modified file → other files are updated
  - Relationships TO modified file (other files calling `foo()`) remain valid UNLESS:
    - Function `foo()` signature changed (requires dependent file context re-injection)
    - Function `foo()` deleted (requires warning about broken references)

**Signature Change Detection** (v0.1.0 limitation):
- v0.1.0: Does NOT detect signature changes
- Assumption: Cached function signatures remain valid within 10-minute expiry window
- Future (v0.2.0): Track function signatures in metadata, invalidate dependent caches if signature changes

**Cache Invalidation Strategy**:

**On File Modification** (EC-11):
1. Invalidate all cache entries where `file_path == modified_file`
2. Invalidate cache entries for snippets from `modified_file` injected into other files
3. Leave cache entries for other files intact (still fresh)

**On File Deletion**:
1. Evict all cache entries for deleted file
2. Leave cache entries for other files (they may still reference deleted file, will re-read and discover it's missing)

**Incremental Re-Analysis**:
- Only modified file is re-analyzed, not entire project
- Target: <200ms for single file re-analysis (NFR-1)
- If modification affects 0 relationships: No graph updates needed (e.g., comment-only change)

---

#### 3.6.4 File Deletion Handling

**Problem** (EC-14): File B deleted, but relationship graph still references it.

**Graph Cleanup**:
1. Query relationships where `source_file == deleted_file` OR `target_file == deleted_file`
2. Remove all matching relationships from graph
3. Update bidirectional indexes
4. Mark deleted file in metadata: `"deleted": true, "deletion_time": timestamp`

**Cache Eviction**:
- Remove all cache entries for deleted file
- Remove cached snippets from deleted file

**Broken Reference Detection**:
- After deletion, check for files that imported from deleted file
- For each importing file, emit warning:
  - "⚠️ Imported file deleted: {importing_file} imports from {deleted_file} which no longer exists"
  - List specific imports that are now broken

**User Notification**:
- If user edits file that depends on deleted file:
  - Context injection note: "⚠️ Note: This file imports from {deleted_file} which was deleted on {timestamp}"
  - Provide last-known location of deleted file (useful for recovery)

**Git Branch Switch Handling**:

**Scenario**: User runs `git checkout other_branch`, causing 50 files to change (some created, some deleted, some modified).

**Handling**:
1. Batch all events (creates, modifies, deletes) from git operation
2. Process deletions first (remove old relationships)
3. Process modifications (update relationships)
4. Process creates (add new relationships)
5. Rebuild relationship graph indexes once after all changes
6. Result: Graph consistent with new branch state

**File Rename Detection**:
- Most file watchers report rename as Delete + Create
- Heuristic to detect rename: Delete and Create within same event batch with similar content
- If detected: Update file paths in relationship graph without re-analysis
- If not detected: Treat as independent delete and create (slight inefficiency but correct)

---

### 3.7 Working Memory Cache

This section describes the caching layer that reduces redundant file re-reads by storing recently-accessed content.

**Key Design Change**: This implementation uses a **demand-driven, timestamp-based staleness detection** approach that eliminates the need for time-based expiry and debouncing. Cache entries are refreshed lazily when detected as stale during read operations.

#### 3.7.1 Cache Structure

**Data Structure**: Combination of LRU (Least Recently Used) ordering and hash map for fast lookups.

**Cache Key**:
- Primary key: File path (absolute path)
- Secondary key: Line range (optional, for function/class snippets)
- Combined key format: `(file_path, line_range)`
- Examples:
  - Full file: `("/path/to/file.py", None)`
  - Function snippet: `("/path/to/file.py", (45, 67))`

**Cache Value**: `CacheEntry` dataclass (see Section 3.3.3)
- `content`: str (file content or snippet)
- `timestamp`: float (Unix epoch, last access time)
- `file_path`: str
- `line_range`: Optional[Tuple[int, int]]
- `metadata`: Dict containing:
  - `size_bytes`: int
  - `file_hash`: str (SHA-256 for staleness detection)
  - `is_snippet`: bool (full file vs function snippet)

**LRU Ordering**:
- Maintain doubly-linked list of cache entries ordered by access time
- Most recently accessed at head, least recently accessed at tail
- On cache hit: Move entry to head of list
- On eviction: Remove from tail of list

**Implementation Options**:
- Python `collections.OrderedDict` (built-in, simple)
- Custom LRU with separate hash map and linked list (faster for large caches)
- Recommended: `collections.OrderedDict` for v0.1.0 (simpler), optimize in v0.2.0 if needed

---

#### 3.7.2 Staleness Detection and Cache Policies

**3.7.2.1 Timestamp-Based Staleness Detection** (FR-15)

The cache uses a **demand-driven staleness detection** approach that compares timestamps to determine if cached content is stale.

**Timestamp Structures** (see Section 3.3.3 for full definition):
```python
# Owned by FileWatcher, updated by watcher thread
file_event_timestamps: Dict[str, float] = {}  # filepath -> last event time

# Owned by WorkingMemoryCache, updated by cache thread
file_last_read_timestamps: Dict[str, float] = {}  # filepath -> when file was read
```

**Staleness Check Algorithm**:
```python
def is_stale(self, filepath: str) -> bool:
    """
    Check if cached file is stale (modified since last read).

    Thread safety: Reads from file_event_timestamps (GIL-protected).
    """
    # File never tracked by watcher - treat as stale
    if filepath not in file_event_timestamps:
        return True

    # File never read before - treat as stale (first access)
    if filepath not in self._file_last_read_timestamps:
        return True

    # Normal case: Compare timestamps
    return file_event_timestamps[filepath] > self._file_last_read_timestamps[filepath]
```

**Fallback for Missed Events** (addresses watcher event loss):
```python
# Optional: Add mtime check as backup
file_mtime = os.path.getmtime(filepath)
return (file_event_timestamps.get(filepath, 0) > self._file_last_read_timestamps.get(filepath, 0)
        or file_mtime > self._file_last_read_timestamps.get(filepath, 0))
```

**Key Properties**:
- **No time-based expiry**: Entries only stale if file actually modified (FR-14 removed)
- **No debouncing needed**: Timestamp updates are instant, analysis deferred to reads
- **Self-healing**: If watcher misses Create event, cache detects and refreshes
- **Conservative**: Unknown files treated as stale (safe default)

---

**3.7.2.2 Size Limit Policy** (FR-16, EC-15)

**Default Size Limit**: 50KB per session

**Rationale**:
- Keep memory footprint minimal (<500MB total system, per NFR-4)
- 50KB ≈ 10-20 typical function snippets or 2-3 full files
- Session metrics will reveal if limit is too restrictive

**Size Tracking**:
- Maintain running total: `current_cache_size_bytes`
- On cache insertion: `current_cache_size_bytes += entry.size_bytes`
- On cache eviction: `current_cache_size_bytes -= entry.size_bytes`

**Eviction Trigger**:
- When inserting new entry would exceed limit:
  1. Evict least-recently-used entries from tail of LRU
  2. Continue evicting until: `current_cache_size_bytes + new_entry_size <= limit`
  3. Insert new entry

**Configuration** (FR-49):
- Parameter: `cache_size_limit_kb` (default: 50)
- Location: `.cross_file_context_links.yml`
- Example: `cache_size_limit_kb: 100` (increase for larger codebases)

**Monitoring**:
- Track peak cache size during session
- Log in session metrics (FR-44)
- If peak consistently reaches limit: Suggest increasing limit in analysis

---

**3.7.2.3 Combined Policy** (Staleness + Size Limit)

**Eviction Priority**:
1. **Stale entries**: Detected on read, refreshed atomically
2. **LRU entries**: When size limit exceeded, evict least-recently-used

**No Background Cleanup Needed**:
- Staleness checked on every read (demand-driven)
- LRU eviction handles size pressure
- Simpler design, no periodic tasks

---

#### 3.7.3 Cache Operations

**3.7.3.1 Cache Get with Automatic Refresh**

**Signature**: `get(file_path: str, line_range: Optional[Tuple[int, int]]) -> str`

**Behavior** (demand-driven refresh):
```python
def get(self, filepath: str, line_range: Optional[Tuple[int, int]] = None) -> str:
    """
    Get cached content, automatically refreshing if stale.

    This is the core operation that integrates staleness detection,
    cache refresh, and relationship graph updates.
    """
    with self._cache_lock:  # Protects cache AND file_last_read_timestamps
        # Check staleness
        if self.is_stale(filepath) or filepath not in self._cache:
            # Stale or miss - refresh from disk
            t = time.time()  # Capture timestamp BEFORE read

            # Retry logic for file locks (see Section 3.11.2)
            content = self._read_from_disk_with_retry(filepath)

            # Update cache AND relationship graph atomically
            self._cache[filepath] = CacheEntry(
                filepath=filepath,
                line_start=line_range[0] if line_range else 0,
                line_end=line_range[1] if line_range else len(content.splitlines()),
                content=content,
                last_accessed=t,
                access_count=1,
                size_bytes=len(content.encode('utf-8'))
            )

            # Synchronize timestamp (uses start time for correctness)
            self._file_last_read_timestamps[filepath] = t

            # Re-analyze relationships (demand-driven)
            self._update_relationships(filepath, content)

            # Update statistics
            self._stats.staleness_refreshes += 1
        else:
            # Cache hit - update access time for LRU
            entry = self._cache[filepath]
            entry.last_accessed = time.time()
            entry.access_count += 1
            self._stats.hits += 1

        return self._cache[filepath].content
```

**Key Design Points**:
1. **Timestamp captured before read** (not after): Correctly handles modifications during I/O
2. **Atomic update**: Cache + timestamps + relationship graph updated under same lock
3. **Demand-driven**: Analysis only happens when file actually accessed
4. **Retry logic**: Handles file locks from concurrent writes (exponential backoff)

**Thread Safety**:
- `_cache_lock` protects: `_cache`, `_file_last_read_timestamps`
- `file_event_timestamps` read without lock (GIL ensures atomic dict reads)
- No deadlock risk: Single lock, no nested locking

---

**3.7.3.2 File Read with Retry**

**Signature**: `_read_from_disk_with_retry(file_path: str, max_retries: int = 3) -> str`

**Behavior**:
```python
def _read_from_disk_with_retry(self, filepath: str, max_retries: int = 3) -> str:
    """
    Read file from disk with retry logic for file locks.

    Exponential backoff: 100ms, 200ms, 400ms
    """
    for attempt in range(max_retries):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except (IOError, OSError) as e:
            if attempt < max_retries - 1:
                delay = 0.1 * (2 ** attempt)  # 100ms, 200ms, 400ms
                time.sleep(delay)
            else:
                # Final failure - log and re-raise
                logger.warning(f"Failed to read {filepath} after {max_retries} attempts: {e}")
                raise
```

**Deferred Details**: Specific retry strategies can be refined during implementation (GitHub Issue).

---

**3.7.3.3 Relationship Graph Update**

**Signature**: `_update_relationships(file_path: str, content: str) -> None`

**Behavior**:
1. Parse file content into AST (see Section 3.5.1)
2. Run relationship detectors
3. Update `RelationshipGraph`:
   - Remove old relationships for this file
   - Add new relationships
4. **Crucially**: This happens under the same `_cache_lock`, ensuring cache and graph stay synchronized

---

**3.7.3.4 Evict LRU**

**Signature**: `_evict_lru(bytes_needed: int) -> None`

**Behavior**:
1. Start from tail of LRU list (least recently used)
2. While `bytes_freed < bytes_needed`:
   a. Remove entry from tail
   b. Remove from `_cache`
   c. Remove from `_file_last_read_timestamps` (stay synchronized!)
   d. Update `current_cache_size_bytes -= entry.size_bytes`
   d. Update `bytes_freed += entry.size_bytes`
3. Log eviction count to statistics

**Invocation**:
- Called during `get()` if cache size would exceed limit after refresh

---

**3.7.3.5 Statistics Collection**

**No longer needed**:
- `evict_expired()` removed (no time-based expiry)
- `invalidate()` removed (staleness detected on read, not proactively)

---

#### 3.7.4 Cache Statistics

**Purpose**: Track cache performance for tuning and analysis (FR-44, FR-49).

**Statistics Tracked**:

**Access Metrics**:
- `total_reads`: Total cache access attempts
- `cache_hits`: Successful cache retrievals (entry fresh)
- `staleness_refreshes`: Cache entries refreshed due to file modifications
- `hit_rate`: `cache_hits / total_reads`

**Size Metrics**:
- `current_size_kb`: Current cache size in KB
- `peak_size_kb`: Maximum cache size reached during session
- `size_limit_kb`: Configured size limit

**Eviction Metrics**:
- `evictions_lru`: Entries evicted due to size limit (LRU policy)

**Per-File Metrics** (optional, for debugging):
- `access_counts`: Dict[file_path, int] (how many times each file accessed)
- `staleness_refresh_counts`: Dict[file_path, int] (refreshes per file)

**Statistics Export**:
- Included in session metrics (FR-44)
- Written to `.cross_file_context_logs/session_metrics.jsonl`
- Used by metrics analysis tool to suggest optimal configuration

**Example Statistics Object**:
```json
{
  "cache_performance": {
    "total_reads": 1000,
    "cache_hits": 700,
    "staleness_refreshes": 300,
    "hit_rate": 0.70,
    "current_size_kb": 42.3,
    "peak_size_kb": 48.7,
    "size_limit_kb": 50,
    "evictions_lru": 5
  }
}
```

**Interpretation**:
- `hit_rate`: Target >60% (lower than time-based expiry, but more correct)
- `staleness_refreshes`: High count indicates frequent file modifications (expected)
- `evictions_lru`: If high count, size limit may be too small

---

### 3.8 Context Injection

This section describes the core user-facing feature: automatically injecting cross-file context when Claude reads a file.

#### 3.8.1 Injection Trigger

**Design Decision (DD-5)**: Context injection is inline with Read tool execution, not a separate tool.

**When Injection Occurs**:
1. User (or Claude) invokes Read tool on `target_file.py`
2. MCP server intercepts Read request
3. Query relationship graph: Does `target_file.py` have cross-file dependencies?
4. If YES: Perform context injection workflow
5. If NO: Return file content without injection (standard Read behavior)

**Advantages of Inline Approach** (DD-5):
- **Natural UX**: Context appears automatically when relevant
- **No extra tool learning**: Claude doesn't need to learn new tool for context
- **Reduced latency**: Single Read call instead of Read + separate context call
- **Better adoption**: Users don't need to explicitly request context

**No Injection Scenarios**:
- Standalone files with no imports or function calls to other project files
- Standard library imports only (no local dependencies)
- User configuration: `enable_context_injection: false`

---

#### 3.8.2 Injection Content Selection

**Content Selection Workflow**:

**Step 1: Query Relationship Graph**
- Query: `get_relationships(target_file)` → List[Relationship]
- Filter for relevant relationships:
  - IMPORT relationships where `target_file` imports from other project files
  - FUNCTION_CALL relationships where `target_file` calls functions defined elsewhere
  - INHERITANCE relationships where `target_file` inherits from classes elsewhere

**Step 2: Prioritize Dependencies**

**Priority Factors** (in order):

1. **Direct dependencies over transitive**:
   - Direct: `target_file` imports from `dependency_file`
   - Transitive: `target_file` → `intermediate` → `dependency_file`
   - Priority: Direct first

2. **Recently edited files**:
   - Files modified within last 10 minutes get higher priority
   - Rationale: User likely working on these files, context most relevant

3. **High usage frequency**:
   - Functions used in 3+ files get higher priority (FR-19, FR-20)
   - Warning emitted for these: "⚠️ Note: `foo()` is used in {N} files"
   - Rationale: Changes to these functions have wider impact

4. **Relationship type**:
   - IMPORT > FUNCTION_CALL > INHERITANCE
   - Rationale: Imports essential for understanding, function calls next, inheritance less immediate

**Step 3: Check Cache for Snippets**

For each dependency (in priority order):
1. Query cache: `cache.get(dependency_file, function_line_range)`
2. If cache hit:
   - Use cached snippet (with cache age metadata)
   - Mark as "fresh" or "stale" based on age
3. If cache miss:
   - Re-read dependency file from disk
   - Extract function/class definition
   - Add to cache for future use

**Step 4: Assemble Context Snippets**

Collect all relevant snippets (see 3.8.4):
- Add snippets in priority order
- Track cumulative token count for metrics
- **v0.1.0**: Include all dependencies (no limit)
- **Rationale**: Gather data on actual token counts before imposing limits

---

#### 3.8.3 Injection Format

**Format Design (FR-10)**: Location + signature only, NOT full implementation.

**Rationale**:
- Full function bodies: Too many tokens, exceeds budget quickly
- Signature only: ~10-20 tokens per function, allows 20-50 functions in budget
- Experiment (PRD Section 7.1): 58% token reduction vs full bodies

**Injection Structure**:

```
[Cross-File Context]

This file imports from:
- retry.py: retry_with_backoff() (line 45)
- utils.py: validate_config() (line 12)

Recent definitions (last read: 3 minutes ago):

From retry.py:45
def retry_with_backoff(func, max_retries=3, initial_delay=1.0):
    """Retry function with exponential backoff."""
    # Implementation in retry.py:45-67

From utils.py:12
def validate_config(config: dict) -> bool:
    """Validate configuration dictionary structure."""
    # Implementation in utils.py:12-28

---

[File Content]
<actual file content here>
```

**Components**:

1. **Section Header**: `[Cross-File Context]`
   - Clearly delineates injected content from file content
   - Claude can easily distinguish context from actual code

2. **Dependency Summary**:
   - List all imported files and key dependencies
   - Provides quick overview without taking many tokens

3. **Snippet Format** (per function):
   ```
   From <file>:<line>
   <function signature>
       """<docstring if present>"""
       # Implementation in <file>:<line_range>
   ```
   - **File + line**: Exact location for reference
   - **Signature**: Function name, parameters, return type (if annotated)
   - **Docstring**: If present and short (<50 chars), include
   - **Implementation pointer**: Line range for full definition

4. **Cache Age Indicator**:
   - "last read: X minutes ago"
   - Helps Claude (and user) assess freshness
   - If >5 minutes old, note may be stale

5. **Separator**: `---`
   - Visual separator between context and file content

**Special Cases**:

**Wildcard Imports** (EC-4):
```
From utils.py:10
from utils import *
    # Note: Wildcard import - specific function tracking unavailable
    # See utils.py for available functions
```

**Large Functions** (EC-12):
```
From processor.py:120
def process_large_dataset(data, options):
    # Function is 200+ lines, showing signature only
    # Full definition: processor.py:120-320
```

**Deleted Files** (EC-14):
```
⚠️ Note: This file imports from helper.py which was deleted on 2025-11-25 10:30
Last known location: src/helper.py
```

---

#### 3.8.4 Token Budget Management

**v0.1.0 Approach**: No token limit - inject all relevant context

**Rationale (FR-10)**:
- **Data-driven decision-making**: Gather real-world metrics before imposing arbitrary limits
- **Avoid premature optimization**: Don't limit context without understanding actual usage patterns
- **User feedback priority**: Let users report if context is excessive rather than under-provide

**Token Counting Method**:

Use `tiktoken` library for accurate token counting (see concern 3.4 resolution):
```python
import tiktoken

# Use Claude's tokenizer encoding
encoder = tiktoken.get_encoding("cl100k_base")  # Claude/GPT-4 encoding

def count_tokens(text: str) -> int:
    return len(encoder.encode(text))
```

**Why tiktoken**:
- Accurate token counting matching Claude's tokenization
- Prevents 20-30% miscalculation from word-splitting approximations
- MIT licensed - compatible with proprietary project (Section 1.5)

**Injection Strategy (No Limit)**:

1. **Include all direct dependencies**:
   - All imports from other project files
   - All function calls to other project files
   - All inheritance relationships

2. **Add in priority order** (Section 3.8.2):
   - Direct dependencies first
   - Recently edited files
   - High usage frequency (3+ files)
   - Relationship type: IMPORT > FUNCTION_CALL > INHERITANCE

3. **Track token counts for metrics** (Section 3.10.1):
   - Count tokens per injection
   - Record: min, max, median, p95, p99
   - Track distribution: How many injections are <100, 100-500, 500-1000, >1000 tokens?

**Metrics-Driven Tuning (v0.1.1+)**:

After gathering real-world data, analyze:
- **p95 token count**: What do 95% of injections fit within?
- **User feedback**: Do users report excessive context clutter?
- **Performance impact**: Does injection latency suffer with large context?

**Decision criteria for adding limit**:
- If p95 > 2000 tokens AND user complaints about clutter → add configurable limit
- If p95 < 500 tokens consistently → no limit needed, current approach works
- If 500 < p95 < 2000 → evaluate user feedback to decide

**Future Configuration** (if limit added in v0.1.1+):
- Parameter: `context_token_limit` (no default in v0.1.0, configurable later)
- Location: `.cross_file_context_links.yml`
- Truncation strategy: Remove lowest-priority dependencies first
- Always include: At least 1 snippet per direct import (minimum viable context)

**Current Behavior**:
- No truncation
- No warnings about exceeding limits
- All relevant context injected
- Comprehensive metrics tracked for future decision-making

---

#### 3.8.5 Injection Logging

**Purpose** (FR-26, FR-27): Log every context injection for analysis and debugging.

**Log Format**: JSONL (JSON Lines) - one JSON object per line

**Log Location**: `.cross_file_context_logs/injections.jsonl`

**Fields Per Injection Event** (FR-27):

```json
{
  "timestamp": "2025-11-25T10:30:45.123Z",
  "event_type": "context_injection",
  "source_file": "/project/src/retry.py",
  "target_file": "/project/src/processor.py",
  "relationship_type": "IMPORT",
  "snippet": "def retry_with_backoff(func, max_retries=3, initial_delay=1.0):\n    \"\"\"Retry function with exponential backoff.\"\"\"",
  "snippet_location": "retry.py:45-67",
  "cache_age_seconds": 180,
  "cache_hit": true,
  "token_count": 15,
  "context_token_total": 285
}
```

**Field Descriptions**:
- `timestamp`: ISO 8601 timestamp of injection event
- `event_type`: Always "context_injection" (allows filtering if log contains other events)
- `source_file`: File providing the context snippet (dependency)
- `target_file`: File being read (where context is injected)
- `relationship_type`: IMPORT, FUNCTION_CALL, or INHERITANCE
- `snippet`: The actual injected content (signature + docstring)
- `snippet_location`: File path and line range of snippet
- `cache_age_seconds`: Age of snippet in cache (null if not cached)
- `cache_hit`: Boolean, true if snippet retrieved from cache
- `token_count`: Approximate token count of this single snippet
- `context_token_total`: Cumulative token count for all snippets in this injection

**Logging Workflow**:
1. After assembling all snippets for injection
2. For each snippet, create one log entry
3. Write to JSONL file (append mode)
4. Flush to disk immediately (ensure durability)

**Log File Management**:
- No automatic rotation in v0.1.0 (keep all events for analysis)
- File size limit: ~10MB per 4-hour session expected (T-5.7)
- If file grows >50MB: Warn user, suggest manual cleanup
- v0.2.0: Implement log rotation (daily or size-based)

**Privacy** (NFR-5, NFR-6):
- Logs stored locally only (no transmission to external servers)
- Snippets contain code but are user's own code (not sensitive)
- If user concerned: Configuration to disable logging or anonymize file paths

**Query API** (FR-29):
- Provide programmatic access to recent injection events
- Example: `get_recent_injections(target_file, limit=10)`
- Use case: Debugging, understanding what context Claude received

**Compatibility** (FR-28):
- JSONL format matches Claude Code session logs
- Enables unified analysis across all session data
- Can be parsed by standard JSON tools (jq, Python json module, etc.)

---

### 3.9 Warning System

This section describes the warning system that alerts users when dynamic Python patterns are detected that cannot be statically analyzed.

#### 3.9.1 Warning Types

The system detects and warns about the following dynamic patterns (see Section 3.5.4 for detailed detection logic):

**1. Dynamic Dispatch** (FR-33, EC-6):
- **Pattern**: `getattr(obj, dynamic_name)()`
- **Detection**: AST node `Call` where `func` is a `Call` to `getattr` with variable as second argument
- **Warning**: "⚠️ Dynamic dispatch detected in {file}:{line} - relationship tracking unavailable for `getattr(obj, '{name}')`"
- **Severity**: Warning
- **Emitted in**: Source modules only (suppressed in test modules)

**2. Monkey Patching** (FR-34, EC-7):
- **Pattern**: `module.attr = replacement` (runtime attribute reassignment)
- **Detection**: AST node `Assign` where target is `Attribute`
- **Warning**: "⚠️ Monkey patching detected in {file}:{line} - `{module}.{attr}` reassigned, relationship tracking may be inaccurate"
- **Severity**: Warning
- **Emitted in**: Source modules only (suppressed in test modules, expected for mocking)

**3. exec/eval** (FR-35, EC-9):
- **Pattern**: `exec(code_string)`, `eval(expression_string)`
- **Detection**: AST node `Call` with `func` = `Name(id='exec')` or `Name(id='eval')`
- **Warning**: "⚠️ Dynamic code execution detected in {file}:{line} - `exec()`/`eval()` prevents static analysis, relationships may be incomplete"
- **Severity**: Warning
- **Emitted in**: Source modules only (suppressed in test modules)
- **Additional action**: Mark file metadata with `"contains_dynamic_execution": true`

**4. Complex Decorators** (FR-36, EC-8):
- **Pattern**: `@decorator_name` with dynamic behavior
- **Detection**: AST node `FunctionDef`/`ClassDef` with non-empty `decorator_list`
- **Warning**: "ℹ️ Decorator `{decorator_name}` in {file}:{line} may modify function behavior - tracking original definition only"
- **Severity**: Info (informational, not critical)
- **Emitted in**: Source modules only
- **Exceptions**: Common test decorators suppressed (`@pytest.mark.*`, `@unittest.skip`, `@mock.patch`)

**5. Metaclasses** (FR-37, EC-10):
- **Pattern**: `class Foo(metaclass=CustomMeta):`
- **Detection**: AST node `ClassDef` with `keywords` containing `keyword(arg='metaclass')`
- **Warning**: "ℹ️ Metaclass detected in {file}:{line} - class `{name}` uses metaclass `{metaclass}`, runtime behavior may differ from static definition"
- **Severity**: Info
- **Emitted in**: All modules (test and source)

**6. Circular Imports** (FR-30, EC-1):
- **Pattern**: File A imports B, B imports A (cycle in import graph)
- **Detection**: Graph traversal after adding IMPORT relationship
- **Warning**: "⚠️ Circular import detected: {A} → {B} → ... → {A} (Google Python Style Guide 3.19.14: code smell, good candidate for refactoring)"
- **Severity**: Warning
- **Emitted in**: All modules (important for both test and source)

---

#### 3.9.2 Test vs Source Module Detection

**Purpose** (DD-3): Many dynamic patterns are common and expected in test modules (mocking, dynamic dispatch in test frameworks) but should be flagged in source modules.

**Detection Strategy**:

**Approach 1: Pattern Matching** (Simple, Always Applied)
- Test module patterns:
  - `**/test_*.py` (pytest convention)
  - `**/*_test.py` (alternate pytest convention)
  - `**/tests/**/*.py` (all files in tests directory)
  - `**/conftest.py` (pytest configuration files)
- Implementation: Use glob pattern matching on file path

**Approach 2: Pytest Configuration Parsing** (DD-3, Advanced)
- Read pytest configuration files in order of precedence:
  1. `pytest.ini`
  2. `pyproject.toml` (section `[tool.pytest.ini_options]`)
  3. `setup.cfg` (section `[tool:pytest]`)
  4. `tox.ini`
- Extract configuration values:
  - `testpaths`: Directories containing tests (e.g., `testpaths = tests integration_tests`)
  - `python_files`: File patterns for test modules (e.g., `python_files = test_*.py *_test.py`)
- Apply custom patterns to file classification

**Fallback**: If no pytest configuration found, use Approach 1 (pattern matching)

**Configuration Parsers**:
- `pytest.ini`: Use Python `configparser` module
- `pyproject.toml`: Use `tomli` library (Python 3.11+ has `tomllib` built-in)
- `setup.cfg`: Use `configparser` module

**Classification Logic**:
```python
def is_test_module(file_path: str) -> bool:
    # Check pytest config patterns (if available)
    if matches_pytest_config_patterns(file_path):
        return True

    # Fallback to default patterns
    default_patterns = [
        "**/test_*.py",
        "**/*_test.py",
        "**/tests/**/*.py",
        "**/conftest.py"
    ]
    return any(matches_pattern(file_path, pattern) for pattern in default_patterns)
```

**No Runtime Dependency**: Parse configuration files statically, do NOT import or execute pytest (DD-3)

---

#### 3.9.3 Warning Message Format

**Structured Format** (FR-38): All warnings are machine-parseable JSON objects.

**Required Fields**:
```json
{
  "type": "dynamic_dispatch",
  "file": "/project/src/module.py",
  "line": 42,
  "column": 10,
  "severity": "warning",
  "pattern": "getattr(obj, 'method')",
  "message": "Dynamic dispatch detected: getattr(obj, 'method')() - relationship tracking unavailable",
  "explanation": "The function name is determined at runtime, preventing static analysis. Consider using explicit function calls if possible.",
  "timestamp": "2025-11-25T10:30:00Z"
}
```

**Field Descriptions**:
- `type`: Pattern identifier (e.g., "dynamic_dispatch", "monkey_patching", "exec_eval", "decorator", "metaclass", "circular_import")
- `file`: Absolute file path
- `line`: Line number where pattern detected
- `column`: Column offset (optional, for precise location)
- `severity`: "warning" (actionable issue) or "info" (informational only)
- `pattern`: Code snippet showing the detected pattern
- `message`: Human-readable summary
- `explanation`: Longer explanation with context and guidance (optional)
- `timestamp`: ISO 8601 timestamp of detection

**Human-Readable Display** (for user output):
```
⚠️ src/module.py:42 - Dynamic dispatch detected
  getattr(obj, 'method')()
  → Relationship tracking unavailable for dynamic function calls
```

**Actionable Guidance** (when applicable):
- Dynamic dispatch: "Consider using explicit function calls if the function name is known"
- Circular imports: "See Google Python Style Guide 3.19.14 for refactoring strategies"
- exec/eval: "Consider using safer alternatives (importlib, ast.literal_eval, or explicit logic)"

---

#### 3.9.4 Warning Suppression

**Configuration File**: `.cross_file_context_links.yml` (project root)

**Suppression Granularity**:

**1. File-Level Suppression** (FR-39):
```yaml
suppress_warnings:
  - "src/legacy/old_module.py"
  - "scripts/migration_script.py"
```
- Suppresses ALL warnings for specific files
- Use case: Legacy code with many unavoidable dynamic patterns

**2. Directory-Level Suppression** (FR-40):
```yaml
suppress_warnings:
  - "tests/**/*"
  - "generated/**/*.py"
  - "vendor/**/*.py"
```
- Suppresses ALL warnings for files matching glob pattern
- Use case: Entire directories with expected dynamic patterns (tests, generated code)

**3. Pattern-Type Suppression**:
```yaml
suppress_dynamic_dispatch_warnings: true
suppress_monkey_patching_warnings: true
suppress_exec_eval_warnings: true
suppress_decorator_warnings: true
suppress_metaclass_warnings: true
suppress_circular_import_warnings: false  # Usually want to keep this
```
- Suppresses specific warning types globally
- Use case: Project-wide policy decision (e.g., "we use metaclasses everywhere, don't warn")

**4. Per-File Pattern-Type Suppression** (Advanced):
```yaml
file_specific_suppressions:
  "src/utils.py":
    - "dynamic_dispatch"
    - "decorator"
  "src/base.py":
    - "metaclass"
```
- Suppresses specific pattern types for specific files
- Use case: Fine-grained control without suppressing all warnings

**Configuration Validation**:
- Invalid file paths: Log warning, continue with valid entries
- Invalid pattern types: Log warning, ignore invalid entries
- Missing configuration file: Use default behavior (emit all warnings)

**Precedence** (if multiple suppressions apply):
1. File-specific pattern-type suppression (most specific)
2. Global pattern-type suppression
3. File-level suppression
4. Directory-level suppression
5. Test vs source module detection (built-in)

---

#### 3.9.5 Warning Logging

**Log Format** (FR-41): JSONL (JSON Lines) - one warning per line

**Log Location**: `.cross_file_context_logs/warnings.jsonl`

**Example Log Entries**:
```jsonl
{"type":"dynamic_dispatch","file":"/project/src/module.py","line":42,"severity":"warning","pattern":"getattr(obj, 'method')","message":"Dynamic dispatch detected","timestamp":"2025-11-25T10:30:00.123Z"}
{"type":"circular_import","file":"/project/src/a.py","line":1,"severity":"warning","pattern":"import b","message":"Circular import detected: a.py → b.py → a.py","timestamp":"2025-11-25T10:30:15.456Z"}
{"type":"metaclass","file":"/project/src/base.py","line":10,"severity":"info","pattern":"class Base(metaclass=Meta)","message":"Metaclass detected","timestamp":"2025-11-25T10:30:20.789Z"}
```

**Logging Workflow**:
1. During AST parsing, detector encounters dynamic pattern
2. Check if warning should be emitted (test vs source, suppression config)
3. If emitting: Create warning object with all fields
4. Write to warnings.jsonl (append mode)
5. Flush to disk immediately
6. Increment warning counter in session metrics

**Integration with Session Metrics**:
- Session metrics include warning statistics (FR-44):
  - Total warning count
  - Count by type (dynamic_dispatch, monkey_patching, etc.)
  - Files with most warnings
- Example:
  ```json
  "warnings": {
    "total_warnings": 8,
    "by_type": {
      "circular_import": 2,
      "dynamic_dispatch": 3,
      "monkey_patching": 1,
      "exec_eval": 2
    },
    "files_with_most_warnings": [
      {"file": "src/legacy.py", "warning_count": 4},
      {"file": "src/utils.py", "warning_count": 2}
    ]
  }
  ```

**Log File Management**:
- No automatic rotation in v0.1.0
- Typical size: <1MB per session (assuming <1000 warnings)
- If file grows >10MB: Warn user, suggest cleanup or enabling suppression
- v0.2.0: Implement log rotation

**Privacy**:
- Warnings contain file paths and code snippets
- All stored locally, never transmitted externally (NFR-5, NFR-6)
- Optional anonymization: Hash file paths if configured

---

### 3.10 Metrics and Logging

This section describes the metrics collection and logging infrastructure that enables data-driven threshold tuning and system observability.

**Note**: Implementation details for MetricsCollector component are in Section 3.4.9. Injection logging details are in Section 3.8.5.

#### 3.10.1 Session Metrics

**Purpose** (FR-43, FR-44): Collect comprehensive session-level metrics to enable data-driven tuning of thresholds (cache expiry, token limits, etc.) as described in PRD Section 7.2.

**Emission Timing**: Metrics written at end of session (MCP server shutdown or explicit trigger)

**Log Format** (FR-45): JSONL (JSON Lines)

**Log Location**: `.cross_file_context_logs/session_metrics.jsonl`

**Metrics Structure** (FR-46):

See Section 3.4.9 for complete metrics structure. Key categories:

1. **Cache Performance**:
   - `hit_rate`, `miss_rate`, `total_reads`, `cache_hits`, `cache_misses`
   - `peak_size_kb`, `average_expiry_seconds`
   - Goal: Validate 10-minute expiry assumption, tune cache size

2. **Context Injection**:
   - Token counts: `min`, `max`, `median`, `p95`
   - `threshold_exceedances`: Count of injections exceeding 500 token limit
   - Goal: Determine if 500-token limit is appropriate

3. **Relationship Graph**:
   - `total_files`, `total_relationships`
   - `most_connected_files`: Files with highest dependency counts
   - Goal: Understand codebase structure, identify central modules

4. **Function Usage Distribution**:
   - Histogram: Functions used in 1-3 files, 4-10 files, 11+ files
   - Goal: Validate "functions used in 3+ files" warning threshold (FR-19, FR-20)

5. **Re-read Patterns**:
   - Files re-read multiple times with counts
   - Goal: Identify frequently-accessed files, validate cache effectiveness

6. **Performance**:
   - Parsing times: `min`, `max`, `median`, `p95` (ms)
   - Injection latency: `min`, `max`, `median`, `p95` (ms)
   - Goal: Ensure performance meets NFR targets (<200ms parsing, <50ms injection)

7. **Warning Statistics**:
   - `total_warnings`, `by_type` (counts per warning type)
   - `files_with_most_warnings`
   - Goal: Understand dynamic pattern prevalence, identify problematic files

8. **Identifier Resolution Effectiveness** (see Section 3.5.6):
   - `function_calls_analyzed`: Total function calls detected
   - `resolved_to_imports`: Count traced to immediate imports (%)
   - `resolved_to_local`: Count traced to local definitions (%)
   - `resolved_to_builtin`: Count traced to Python builtins (%)
   - `unresolved`: Count not traced (%)
   - `unresolved_needed_for_context`: Count of unresolved identifiers that blocked context injection (%)
   - Goal: Determine if AST-based resolution is sufficient or if interpreter fallback needed (v0.2.0+)
   - Decision threshold: If >10% of context injections blocked by unresolved identifiers, consider interpreter inspection fallback

**Metrics Anonymization** (FR-47):
- File paths can be anonymized (hash-based) if configured
- No sensitive code snippets in metrics (only statistics)
- Safe for aggregation across multiple sessions

**Configuration Values Captured** (FR-49):
- Metrics include actual configuration values used during session:
  - `cache_expiry_minutes`, `cache_size_limit_kb`, `context_token_limit`
- Enables correlation between configuration and performance

---

#### 3.10.2 Injection Event Logging

**Purpose** (FR-26): Log every context injection event for debugging and analysis.

**See Section 3.8.5 for complete specification.**

**Summary**:
- Log format: JSONL
- Log location: `.cross_file_context_logs/injections.jsonl`
- Real-time logging: Events written as they occur (not batched)
- Fields per event (FR-27): timestamp, source_file, target_file, relationship_type, snippet, cache_age_seconds, token_count, context_token_total
- Compatibility (FR-28): JSONL format matches Claude Code session logs
- Query API (FR-29): Programmatic access to recent injection events

---

#### 3.10.3 Graph Export

**Purpose** (FR-23): Enable external tools to analyze relationship graph structure.

**Export Trigger**:
- On-demand: User/tool invokes export function
- Automatic: Export at end of session (optional, configurable)
- MCP tool: `get_relationship_graph` returns exported graph

**Export Format** (FR-25): JSON (human-readable, machine-parseable)

**Structure**:
```json
{
  "metadata": {
    "timestamp": "2025-11-25T10:30:00Z",
    "version": "0.1.0",
    "language": "python",
    "project_root": "/project",
    "total_files": 150,
    "total_relationships": 450
  },
  "files": [
    {
      "path": "/project/src/module.py",
      "relative_path": "src/module.py",
      "last_modified": "2025-11-25T09:15:00Z",
      "relationship_count": 12,
      "in_import_cycle": false
    }
  ],
  "relationships": [
    {
      "source_file": "/project/src/a.py",
      "target_file": "/project/src/b.py",
      "relationship_type": "IMPORT",
      "line_number": 5,
      "metadata": {
        "import_style": "from...import",
        "imported_names": ["foo", "bar"],
        "conditional": false,
        "wildcard": false
      }
    }
  ],
  "graph_metadata": {
    "circular_imports": [
      ["src/a.py", "src/b.py", "src/a.py"]
    ],
    "most_connected_files": [
      {"file": "src/utils.py", "dependency_count": 45},
      {"file": "src/base.py", "dependency_count": 32}
    ]
  }
}
```

**Field Descriptions**:
- `metadata`: Graph-level information (timestamp, version, language, project root)
- `files`: All analyzed files with modification times and relationship counts
- `relationships`: All detected relationships with full metadata
- `graph_metadata`: Derived information (circular imports, most-connected files)

**File Path Options**:
- Absolute paths: Full file system paths
- Relative paths: Project-relative paths (more portable)
- Both included for flexibility

**Use Cases**:
- External dependency analysis tools
- Visualization tools (generate dependency graphs)
- CI/CD integration (detect circular imports, enforce architecture rules)
- Documentation generation

---

#### 3.10.4 Query API

**Purpose**: Provide programmatic access to system state and logs without parsing files directly.

**API Methods** (exposed via MCP tools or internal Python API):

1. **`get_recent_injections(target_file: str, limit: int = 10)`** (FR-29):
   - Returns: List of recent context injection events for specified file
   - Use case: Debugging, understanding what context Claude received

2. **`get_relationship_graph()`** (FR-23):
   - Returns: Full graph export structure (see 3.10.3)
   - Use case: External tools, visualization

3. **`get_dependents(file_path: str)`** (FR-18):
   - Returns: List of files that depend on specified file
   - Use case: Impact analysis before editing file

4. **`get_dependencies(file_path: str)`**:
   - Returns: List of files that specified file depends on
   - Use case: Understanding file's context requirements

5. **`get_session_metrics()`**:
   - Returns: Current session metrics (in-progress)
   - Use case: Real-time monitoring, debugging

6. **`get_cache_statistics()`**:
   - Returns: Current cache statistics (hit rate, size, etc.)
   - Use case: Performance monitoring

**Implementation**:
- v0.1.0: Internal Python API (used by MCP server)
- Future: Expose as MCP tools for direct Claude Code access

---

#### 3.10.5 Configuration Parameters

**Purpose** (FR-49): All thresholds are configurable to enable tuning based on session metrics.

**Configuration File**: `.cross_file_context_links.yml` (project root)

**Configurable Parameters**:

```yaml
# Cache settings
cache_expiry_minutes: 10  # Default: 10, FR-14
cache_size_limit_kb: 50   # Default: 50, FR-16

# Context injection settings
context_token_limit: 500  # Default: 500, FR-10
enable_context_injection: true  # Default: true

# Warning settings
warn_on_wildcards: false  # Default: false, EC-4
suppress_warnings: []  # File/directory patterns, FR-39/FR-40
suppress_dynamic_dispatch_warnings: false
suppress_monkey_patching_warnings: false
suppress_exec_eval_warnings: false
suppress_decorator_warnings: false
suppress_metaclass_warnings: false
suppress_circular_import_warnings: false

# File watching settings
ignore_patterns:  # Additional patterns beyond .gitignore
  - "generated/**/*.py"
  - "vendor/**/*.py"

# Function usage threshold
function_usage_warning_threshold: 3  # Warn if function used in N+ files, FR-19

# Metrics and logging
metrics_anonymize_paths: false  # Hash file paths in metrics, FR-47
enable_injection_logging: true  # Log context injections, FR-26
enable_warning_logging: true    # Log warnings, FR-41
```

**Configuration Loading**:
- Load at MCP server startup
- Validate all parameters (type checking, range validation)
- Log warnings for invalid parameters, use defaults
- Missing configuration file: Use all defaults

**Runtime Configuration Update** (v0.2.0+):
- v0.1.0: Configuration read once at startup (no runtime updates)
- v0.2.0: Support runtime configuration reload via MCP command
- Use case: Adjust thresholds during session without restart

**Configuration Validation**:
- `cache_expiry_minutes`: Must be > 0
- `cache_size_limit_kb`: Must be > 0
- `context_token_limit`: Must be > 0 and < 10000 (sanity check)
- `function_usage_warning_threshold`: Must be > 0

---

#### 3.10.6 Metrics Analysis Tool

**Purpose** (FR-48): Analyze session metrics to identify patterns and suggest optimal configuration values.

**Tool Name**: `analyze_metrics.py`

**Functionality**:

1. **Parse Session Metrics**:
   - Read `.cross_file_context_logs/session_metrics.jsonl`
   - Parse JSONL entries
   - Aggregate across multiple sessions (if available)

2. **Compute Aggregate Statistics**:
   - Cache performance: Average hit rate across sessions
   - Token usage: Distribution of injection token counts
   - Performance: Median and p95 parsing/injection latencies
   - Warning patterns: Most common warning types

3. **Identify Outliers**:
   - Sessions with unusually low cache hit rates
   - Files with excessive re-reads
   - Injections exceeding token limit
   - Performance outliers (slow parsing/injection)

4. **Suggest Optimal Configuration**:
   - **Cache expiry**: If average cache age at eviction << expiry threshold, suggest reducing expiry time
   - **Cache size**: If frequent LRU evictions and youngest evicted < 5 min, suggest increasing size
   - **Token limit**: If p95 token count < 400, current limit is adequate; if frequent exceedances, suggest raising
   - **Function usage threshold**: If distribution shows 80% functions used in ≤2 files, threshold of 3 is appropriate

**Example Output**:
```
Session Metrics Analysis (5 sessions analyzed)
================================================

Cache Performance:
  Average hit rate: 72%
  Peak size: 48.5 KB (avg)
  Youngest evicted: 180s (avg)
  → RECOMMENDATION: Cache size adequate, consider reducing expiry to 8 minutes

Context Injection:
  Token counts: min=10, median=150, p95=420, max=480
  Threshold exceedances: 2 (0.4% of injections)
  → RECOMMENDATION: 500-token limit is appropriate

Performance:
  Parsing: median=20ms, p95=80ms (target: <200ms) ✓
  Injection: median=10ms, p95=30ms (target: <50ms) ✓
  → RECOMMENDATION: Performance meets targets

Warnings:
  Most common: circular_import (5), dynamic_dispatch (12)
  Files with most warnings: src/legacy.py (15), src/utils.py (8)
  → RECOMMENDATION: Review src/legacy.py for refactoring opportunities
```

**Usage**:
```bash
python analyze_metrics.py .cross_file_context_logs/session_metrics.jsonl
```

**Implementation**:
- Standalone Python script (not part of MCP server)
- Minimal dependencies (standard library only)
- Output format: Human-readable text report
- Future: JSON output for programmatic consumption

---

### 3.11 Error Handling

This section describes error handling strategies that ensure robust operation and graceful degradation.

**Core Principle** (FR-42): **No incorrect context > No context at all**. When uncertain, emit warning but do NOT track incorrectly.

#### 3.11.1 Parsing Failures

**Scenario** (EC-18): Syntax error in Python file prevents AST parsing.

**Causes**:
- Invalid Python syntax (e.g., incomplete code, typos during editing)
- Encoding errors (non-UTF-8 files)
- Python version incompatibility (e.g., using Python 3.11 syntax with Python 3.8 parser)

**Handling**:
1. **Catch exception**: `ast.parse()` raises `SyntaxError`
2. **Log error**: Write structured error to log
   ```json
   {
     "type": "parsing_error",
     "file": "/project/src/broken.py",
     "error": "SyntaxError: invalid syntax",
     "line": 42,
     "timestamp": "2025-11-25T10:30:00Z"
   }
   ```
3. **Skip file**: Do NOT add relationships for this file
4. **Continue**: Process other files normally
5. **Mark in graph**: Store metadata `"parse_error": true` for this file
6. **User notification**: Warning in context injection if file depends on broken file
   - "⚠️ Note: {broken_file} has syntax errors and could not be analyzed"

**No crash**: Parsing failure in one file does NOT stop analysis of entire project

---

#### 3.11.2 File System Errors

**Scenarios**:

**1. File Not Found**:
- **Cause**: File deleted between indexing and read, or referenced file doesn't exist
- **Handling**:
  - Return error to MCP client (tool invocation failed)
  - If caching: Evict from cache
  - If in relationship graph: See "Deleted Files" below

**2. Permission Denied**:
- **Cause**: File permissions restrict read access
- **Handling**:
  - Log warning
  - Skip file analysis
  - If user requests reading file via MCP: Return error response
  - Security note: Respect file system permissions (see 3.12.2)

**3. Deleted Files** (EC-14):
- **Detection**: File watcher detects deletion event, or file read fails with FileNotFoundError
- **Handling** (see Section 3.6.4 for details):
  - Remove all relationships involving deleted file from graph
  - Evict from cache
  - Mark in metadata: `"deleted": true, "deletion_time": timestamp`
  - Warn files that depend on deleted file:
    - "⚠️ Imported file deleted: {file} imports from {deleted_file} which no longer exists"

**4. Concurrent Modifications** (EC-20):
- **Scenario**: File modified by multiple processes simultaneously
- **Detection**: File mtime changed between cache check and read
- **Handling**:
  - Invalidate cache entry (stale content)
  - Re-read file from disk
  - File watcher will detect modification and trigger re-analysis
- **No data loss**: Rely on file system consistency, eventually reach correct state

**5. Encoding Errors**:
- **Cause**: File not UTF-8 encoded
- **Handling**:
  - Try UTF-8 first (standard Python encoding)
  - Fallback to latin-1 (universal binary-safe encoding)
  - Log warning if non-UTF-8 encoding used
  - If both fail: Skip file, log error, continue with others

---

#### 3.11.3 Graph Corruption

**Scenario** (EC-19): Internal relationship graph data structure becomes inconsistent.

**Causes**:
- Bug in graph update logic
- Concurrent access without proper locking (if multi-threaded)
- Disk corruption (if persisted to SQLite in v0.2.0+)

**Detection**:
- Validation checks run periodically (e.g., every 100 file operations):
  - Check for orphaned references (relationships referencing non-existent files)
  - Check for bidirectional consistency (if A → B exists, B should be in graph)
  - Check for duplicate relationships (same source, target, type, line)
- Validation on export (when generating graph export)

**Handling**:
1. **Log corruption details**: Dump corrupted state to file for debugging
2. **Clear graph**: Remove all relationships and file records
3. **Rebuild from scratch**: Re-analyze all files in project
4. **User notification**: Warning message explaining rebuild
   - "⚠️ Relationship graph inconsistency detected. Rebuilding from scratch..."
   - Show progress during rebuild
5. **Continue operation**: After rebuild, system functions normally

**Prevention**:
- Atomic graph updates (add/remove relationships as single operation)
- Defensive programming (validate inputs before graph modification)
- Unit tests for graph operations to catch bugs early

---

#### 3.11.4 Memory Pressure

**Scenarios**:

**1. Cache Size Exceeded** (EC-15):
- **Detection**: `current_cache_size + new_entry_size > size_limit`
- **Handling**: LRU eviction (see Section 3.7.2.2)
  - Evict least-recently-used entries until space available
  - Log eviction count in statistics
  - No data loss: Can always re-read from disk

**2. Long-Running Sessions** (EC-16):
- **Scenario**: 8-hour session with 500+ file accesses, cache accumulates stale entries
- **Handling**: Rolling window approach (see Section 3.7.2.3)
  - After 2 hours: Clear all entries older than 10 minutes
  - Rationale: Recent work more relevant than work from 2+ hours ago
  - Background task checks timestamps, evicts old entries
- **Memory limit**: Even with no eviction, cache is size-limited (default 50KB)

**3. Massive Files** (EC-17):
- **Scenario**: File >10,000 lines (e.g., generated code, concatenated modules)
- **Detection**: Count lines before parsing
- **Handling**:
  - Skip indexing (do not parse AST or detect relationships)
  - Log warning: "⚠️ Skipping analysis of {file}: {line_count} lines exceeds limit (10,000)"
  - Treat as opaque (no relationships from/to this file)
  - Context injection: Note that file is not analyzed
- **Rationale**: Parsing huge files is slow, uses excessive memory, likely generated code with limited value for context

**4. Relationship Graph Size**:
- **Target**: <500MB for 10,000 files (NFR-4)
- **Monitoring**: Track graph size in session metrics
- **Handling**: If approaching limit, warn user
  - "⚠️ Relationship graph size approaching memory limit. Consider reducing project scope or increasing limits."

---

#### 3.11.5 MCP Protocol Errors

**Scenarios**:

**1. Tool Call Failures**:
- **Cause**: Exception during tool execution (e.g., file read fails, graph query fails)
- **Handling**:
  - Catch exception in MCP server layer
  - Format error response per MCP specification
  - Include error message, error code, stack trace (if debug mode)
  - Return to client (Claude Code)
- **No crash**: Tool failure does NOT crash MCP server

**2. Invalid Parameters**:
- **Cause**: Claude Code passes invalid parameters (e.g., invalid file path, negative limit)
- **Handling**:
  - Validate parameters before processing
  - Return error response with clear message: "Invalid parameter: {param} = {value}"
  - Example: `read_with_context(file_path="")` → Error: "file_path cannot be empty"

**3. Timeout Handling**:
- **Scenario**: Operation takes too long (e.g., indexing 10,000 files)
- **MCP timeout**: MCP protocol may have timeout for tool calls
- **Handling**:
  - For long operations: Show progress updates
  - If timeout occurs: Return partial results if available
  - For initial indexing: Run in background, return immediately, update incrementally

**4. Error Response Format**:
```json
{
  "error": {
    "code": "file_not_found",
    "message": "File not found: /project/src/missing.py",
    "details": {
      "file_path": "/project/src/missing.py",
      "suggestion": "File may have been deleted. Check file system."
    }
  }
}
```

---

#### 3.11.6 Graceful Degradation

**Fail-Safe Principle** (FR-42): System continues operating even when subsystems fail, prioritizing **no incorrect context > no context at all**.

**Degradation Scenarios**:

**1. Some Files Cannot Be Parsed**:
- **Behavior**: Continue analyzing other files, track relationships for parseable files only
- **User experience**: Context injection works for parseable files
- **Notification**: Warn about unparsed files if they appear in imports

**2. Cache is Full**:
- **Behavior**: LRU eviction continues, may increase re-reads
- **User experience**: Context injection still works, may be slightly slower
- **Notification**: None (normal operation within capacity limits)

**3. File Watcher Fails**:
- **Causes**: OS limitation (too many file handles), filesystem doesn't support watching
- **Behavior**: Fall back to polling (check file mtimes periodically)
- **User experience**: Incremental updates may be delayed, but still work
- **Notification**: Log warning, notify user to restart if possible

**4. Relationship Graph Corrupted**:
- **Behavior**: Rebuild graph from scratch (see 3.11.3)
- **User experience**: Brief delay during rebuild, then normal operation
- **Notification**: Progress indicator during rebuild

**5. Configuration File Invalid**:
- **Behavior**: Use default configuration values
- **User experience**: System works with defaults
- **Notification**: Log warnings for invalid parameters, show which defaults used

**Operational Guarantees**:
- **Never crash**: Exceptions caught at component boundaries, logged, operation continues
- **Never block**: Long operations run in background or with timeout
- **Never corrupt**: Atomic updates, validation before modification
- **Never mislead**: If uncertain, emit warning rather than incorrect context

---

### 3.12 Security & Compliance

This section addresses security considerations to ensure safe operation within user environments.

#### 3.12.1 Code Execution Safety

**Principle**: System performs ONLY static analysis. No dynamic code execution.

**Static Analysis Only**:
- Use Python's `ast` module to parse code into Abstract Syntax Tree
- AST parsing is safe: reads code as data structure, does NOT execute it
- All relationship detection operates on AST nodes (data), not running code

**Dynamic Patterns Detected but NOT Executed**:
- **exec/eval** (EC-9): Detect `exec(code_string)` and `eval(expression)` patterns in AST, emit warning, but NEVER call exec/eval ourselves
- **importlib.import_module** (EC-2): Detect dynamic imports, but do NOT execute them to resolve module names
- **getattr** (EC-6): Detect dynamic dispatch patterns, but do NOT execute to determine function names

**No Code Import**:
- Do NOT import user's Python modules into our process (could execute module-level code, trigger side effects)
- Parse files as text → AST, keep analysis isolated from runtime

**Rationale**:
- Executing user code could trigger malicious code, side effects (file deletion, network calls), or bugs
- Static analysis is safe, predictable, and fast

**Security Boundary**: Parser operates on code as data, never as executable instructions.

---

#### 3.12.2 File System Access

**Access Restrictions**:

**1. Respect File Permissions**:
- Use standard Python file operations (`open()`, `os.listdir()`)
- If file read fails with `PermissionError`: Log warning, skip file, do NOT attempt to bypass
- Rationale: User may intentionally restrict access to sensitive files

**2. Stay Within Project Root**:
- Project root: Directory containing `.git/` or user-specified root
- Only index and analyze files within project root
- Do NOT traverse parent directories
- Symbolic links: Follow symlinks ONLY if target within project root
  - Validation MUST occur after symlink resolution to prevent TOCTOU vulnerabilities
  - Use canonical path resolution (e.g., `os.path.realpath()`) to resolve symlink target
  - Verify resolved target path is within canonical project root path
  - Reject symlinks if resolved target falls outside project root
- Rationale: Prevent accidental analysis of system files or unrelated projects

**3. Ignore Patterns**:
- Respect `.gitignore` patterns (files ignored by Git typically not relevant)
- Always ignore sensitive file patterns
- **Recommended approach**: Use existing library or standard pattern list (e.g., GitHub's secret scanning patterns, `detect-secrets` library patterns)
  - Rationale: Leverage security expertise and comprehensive coverage from established sources
  - Avoid maintaining custom sensitive pattern list (complex and prone to gaps)
- **Minimum baseline patterns** (if library not available):
  - `.env`, `*.env`, `.env.*` (environment variables with secrets)
  - `credentials.json`, `*_credentials.json`, `secrets.yaml`, etc.
  - Private keys: `*.pem`, `*.key`, `id_rsa`, etc.
  - `.git/` directory (Git internals, may contain sensitive data in commits)
- Configurable additional ignore patterns via `.cross_file_context_links.yml`

**4. No Modification**:
- System is read-only: ONLY reads files, NEVER writes or modifies user code
- Exception: Write logs to `.cross_file_context_logs/` directory (create if not exist)
- Logs directory: Separate from code, clearly marked as tool output

**5. Sensitive File Detection**:
- If user attempts to commit file with sensitive patterns (e.g., `.env` in git add):
  - Warning: "⚠️ Warning: {file} matches sensitive file pattern. Ensure it doesn't contain secrets before committing."
  - Do NOT block operation (user may have legitimate reason)

**Path Validation**:
- Sanitize file paths to prevent path traversal attacks
- Reject paths containing `..`, absolute paths outside project root
- Example: `/etc/passwd` or `../../secrets` rejected

---

#### 3.12.3 Data Privacy

**Principle** (NFR-5, NFR-6): All data stays local. No transmission to external servers.

**Local Operation**:
- All analysis, caching, and logging happens on user's machine
- No network calls for core functionality
- No telemetry or analytics sent to external servers
- User's code and relationships never leave their machine

**Metrics Anonymization** (FR-47):
- **File paths**: Can be anonymized if configured (`metrics_anonymize_paths: true`)
  - Hash file paths using SHA-256: `/project/src/module.py` → `a3f2b1...`
  - Preserves uniqueness for analysis, prevents exposure of project structure
- **Code snippets**: NOT included in session metrics (only statistics: token counts, hit rates, etc.)
  - Exception: Injection logs contain snippets, but stored locally only
- **Safe for aggregation**: Anonymized metrics can be safely aggregated across sessions without privacy concerns

**Log Privacy**:
- **Injection logs**: Contain code snippets (function signatures, docstrings)
  - Stored locally in `.cross_file_context_logs/injections.jsonl`
  - Never transmitted externally
  - User can disable: `enable_injection_logging: false`
- **Warning logs**: Contain file paths, line numbers, code patterns
  - Stored locally in `.cross_file_context_logs/warnings.jsonl`
  - User can disable: `enable_warning_logging: false`
- **Session metrics**: Contain statistics only, no code snippets
  - Can be anonymized as described above

**User Control**:
- Configuration options to disable all logging
- Configuration options to anonymize file paths
- Logs stored in predictable location (`.cross_file_context_logs/`)
- User can delete logs at any time without affecting functionality

**No Credential Storage**:
- System does NOT store or handle user credentials
- No authentication or authorization (operates on local file system with user's permissions)

---

#### 3.12.4 Resource Limits

**Purpose**: Prevent resource exhaustion (DoS) and ensure predictable performance.

**Memory Limits**:

1. **Cache Size Limit** (FR-16):
   - Default: 50KB per session
   - Configurable: `cache_size_limit_kb`
   - Enforcement: LRU eviction when limit exceeded
   - Rationale: Prevent unbounded memory growth

2. **Relationship Graph Size** (NFR-4):
   - Target: <500MB for 10,000 files
   - Monitoring: Track size in session metrics
   - Enforcement: Warn if approaching limit, suggest reducing scope

3. **Total System Memory** (NFR-4):
   - Target: <500MB sustained memory footprint
   - Includes: Relationship graph + cache + runtime overhead
   - Monitoring: Track in session metrics

**File Size Limits**:

1. **Skip Large Files** (EC-17):
   - Limit: 10,000 lines
   - Detection: Count lines before parsing
   - Handling: Skip parsing, log warning, treat as opaque
   - Rationale: Parsing huge files (generated code, concatenated modules) is slow and memory-intensive

2. **Log File Size**:
   - Expected: <10MB per 4-hour session (injection logs)
   - Warning threshold: 50MB
   - Handling: Warn user, suggest cleanup or disabling logging
   - Future (v0.2.0): Automatic log rotation

**Processing Limits**:

1. **Indexing Timeout**:
   - Target: <10 seconds for 100 files, <2 minutes for 1,000 files
   - Handling: If exceeding targets, show progress indicator
   - No hard timeout (would leave system in inconsistent state)

2. **AST Parsing Limits** (DoS Prevention):
   - **Timeout**: 5 seconds per file (configurable via `ast_parsing_timeout_seconds`)
     - Rationale: Prevent DoS from maliciously complex files
     - Handling: Skip file, log warning, continue with other files
   - **Recursion Depth**: 100 levels (configurable via `ast_max_recursion_depth`)
     - Rationale: Prevent stack overflow from deeply nested expressions (e.g., `((((...))))`)
     - Handling: Skip subtree, log warning, continue with sibling nodes
   - See Section 3.5.1 for implementation details

3. **Circular Dependency Detection**:
   - Depth limit: 50 levels
   - Rationale: Prevent infinite loops in cycle detection algorithm
   - Handling: If depth exceeded, assume no cycle (conservative)

4. **Context Injection Token Limit** (FR-10):
   - Hard limit: 500 tokens (configurable)
   - Enforcement: Truncate snippets if approaching limit
   - Rationale: Prevent context injection from consuming excessive Claude context window

**Rate Limiting** (not applicable):
- No external API calls, so no rate limiting needed
- All operations local and bounded by resource limits above

**DoS Prevention**:
- File size limits prevent memory exhaustion from individual files
- Cache size limits prevent memory exhaustion from accumulated reads
- Circular dependency depth limit prevents infinite loops
- No unbounded loops or recursion in graph traversal

**Graceful Degradation**:
- If resource limits exceeded: Emit warning, continue with degraded functionality
- Example: Cache full → LRU eviction continues, may increase re-reads but system functional
- Example: Large file → Skip parsing, warn user, system continues analyzing other files

**Security Implication**: Resource limits prevent both accidental (large generated files) and intentional (malicious huge files) resource exhaustion.

---

### 3.13 Testing Strategy

**For comprehensive test specifications, see [`prd_testing.md`](./prd_testing.md) which contains detailed test plans including 10 test categories (T-1 through T-10), performance benchmarks, UAT phases, and success criteria.**

This section describes the testing philosophy and approach specific to the implementation architecture.

#### 3.13.1 Testing Philosophy

**Fail-Safe Priority** (FR-42):
- **No incorrect context > No context at all**
- If relationship detection uncertain: Emit warning, don't track incorrectly
- Test philosophy: Validate that system errs on the side of caution

**Component Isolation** (DD-1, DD-2):
- Detector plugins are independent: Test each detector in isolation
- Language analyzers are independent: Test PythonAnalyzer without needing TypeScript support
- Storage abstraction: Test with InMemoryStore, verify SQLiteStore can be swapped later (DD-4)

**Architecture-Driven Testing**:
- **Layered testing** (DD-6):
  - MCP Protocol Layer: Test tool registration and request/response handling
  - Business Logic Layer (Service): Test without MCP dependencies
  - Storage Layer: Test with interface mocks
- **Plugin testing** (DD-1):
  - Each detector plugin tested independently with AST fixtures
  - New detectors added without modifying existing test suites

---

#### 3.13.2 Test Layers

**Unit Tests** (Component Isolation):
- **Relationship Detectors**: Test each detector (ImportDetector, FunctionCallDetector, etc.) with AST node fixtures
- **Cache Operations**: Test LRU eviction, expiry logic, invalidation with mocked timestamps
- **Warning System**: Test pattern detection and suppression logic with fixture files
- **Metrics Collector**: Test aggregation and export with synthetic events
- **Coverage Target**: >80% line coverage for business logic components

**Integration Tests** (Component Interaction):
- **PythonAnalyzer + Detectors**: Test full AST parsing pipeline with real Python files
- **Service + Store + Cache**: Test context injection workflow end-to-end
- **FileWatcher + Analyzer**: Test file change events trigger correct re-analysis
- **MCP Server + Service**: Test tool invocations produce correct responses

**Functional Tests** (Feature Validation):
- **Test Categories**: See prd_testing.md for detailed specifications
  - T-1: Relationship Detection (imports, function calls, inheritance)
  - T-2: Context Injection (correct content, token limits, timing)
  - T-3: Working Memory Cache (hit/miss, invalidation, size limits)
  - T-4: Cross-File Awareness (dependents, warnings, graph queries)
  - T-5: Context Injection Logging (structured format, required fields)
  - T-6: Dynamic Python Handling (warnings for dynamic patterns, test vs source distinction)
  - T-10: Session Metrics (all metrics emitted, parseable format)
- **Test Codebase**: Representative Python project (50-100 files) with known dependencies

**Performance Tests** (NFR Validation):
- **Indexing**: 100 files <10s, 1000 files <2min (prd_testing.md T-7.1, T-7.2)
- **Incremental Updates**: <200ms per file (T-7.3)
- **Context Injection Latency**: <50ms (T-8.1)
- **Memory Footprint**: <500MB for 10,000 files (T-7.4)

**User Acceptance Tests** (Real-World Validation):
- See prd_testing.md Section 8.5 for phased rollout plan (Alpha → Beta → Pilot)

---

#### 3.13.3 Test Data Strategy

**Representative Test Repository**:
- 50-100 Python files with documented cross-file dependencies
- Mix of simple and complex imports
- Known circular dependencies (Python allows these) - EC-1
- Edge cases: wildcards, aliases, TYPE_CHECKING conditionals, dynamic patterns (EC-2 through EC-10)

**Fixture Management**:
- AST node fixtures for detector unit tests
- Mock file systems for file watcher tests
- Synthetic metrics events for metrics collector tests

**Edge Case Coverage**:
- All 20 edge cases (EC-1 through EC-20) have corresponding test cases
- Special focus on dynamic patterns that cannot be tracked (EC-6 through EC-10)

---

#### 3.13.4 Testing Tools

**Test Framework**: pytest
- Native Python testing framework
- Fixture support for complex test setup
- Parametrized tests for detector edge cases

**Mocking**: unittest.mock
- Mock file system operations (avoid dependency on real files)
- Mock timestamps for cache expiry tests
- Mock AST nodes for detector isolation

**Performance Profiling**:
- `cProfile` for CPU profiling
- `memory_profiler` for memory tracking
- Custom metrics collection during test runs

**Test Metrics Collection**:
- Session metrics analyzer validates metrics structure (T-10.1 through T-10.7)
- Cache statistics validator checks hit rates, eviction counts
- Injection log parser validates JSONL format

**Code Quality Tools**:
- `black` - Code formatter (line length 100)
- `isort` - Import statement organizer (black-compatible)
- `ruff` - Fast linter (replaces flake8, pylint, isort checks)
- `mypy` - Static type checker (strict mode for src/)

**Pre-Commit Framework**:
- `pre-commit` tool manages Git hooks
- Configuration: `.pre-commit-config.yaml` with all formatters, linters, fast tests
- Installation: `pre-commit install` during project setup

---

#### 3.13.5 Continuous Testing

**Pre-Commit Tests** (see Section 3.15.2 for detailed requirements):
- **Execution**: Git pre-commit hook (local) + GitHub PR check (remote)
- **Code formatting**: black, isort (auto-fix)
- **Linting**: ruff (Python linting), mypy (type checking)
- **Fast unit tests**: pytest with "not slow" marker (<10s total)
- **Target**: Catch issues before code review, fail fast on quality violations

**CI Pipeline Tests** (see Section 3.15.3 for detailed requirements):
- **Execution**: GitHub PR check (required for merge)
- **Multi-environment matrix**:
  - Python versions: 3.8, 3.9, 3.10, 3.11, 3.12
  - Operating system: Ubuntu only
- **Test scope**: Full unit test suite + integration tests
- **Functional test subset**: Representative cases from T-1 through T-10
- **Performance regression tests**: Compare against baseline

**Nightly Tests**:
- Full functional test suite (all T-1 through T-10 test cases)
- Performance benchmarks
- Long-running session tests (EC-16: 8-hour sessions)
- Memory leak detection

---

#### 3.13.6 Test-Driven Design Validation

**Architecture Validation Through Tests**:
- **DD-1 (Detector Plugins)**: Test adding new detector without modifying existing code
- **DD-2 (Language-Agnostic Watcher)**: Test FileWatcher with mock TypeScriptAnalyzer (future-proofing)
- **DD-4 (Storage Abstraction)**: Test swapping InMemoryStore → MockSQLiteStore with 1-line change
- **DD-6 (Layered Architecture)**: Test MCP layer, Service layer, Storage layer independently

**Edge Case Validation**:
- Each edge case (EC-1 through EC-20) maps to specific test cases
- Test both detection and handling (e.g., EC-1 circular imports: detect, warn, continue)
- Test fail-safe behavior: System never adds incorrect relationships (FR-42)

---

### 3.14 Development Plan

This section outlines the phased implementation roadmap. Each task includes references to enable GitHub issue creation with full traceability to requirements, design decisions, edge cases, and tests.

**Note**: Tasks are organized by dependencies, not strict weekly timelines. Actual implementation may proceed in parallel where dependencies permit.

---

#### 3.14.0 Phase 0: Developer Experience Setup

**Goal**: Establish all developer experience infrastructure before product development begins (Section 3.15.4 requirement).

**Priority**: MUST complete before any Phase 1 tasks.

**Tasks**: See Task 7.5 (moved to Phase 0)
- Task 0.1: Setup pre-commit hooks (.pre-commit-config.yaml)
- Task 0.2: Configure lightweight checks GitHub Action
- Task 0.3: Configure comprehensive tests GitHub Action (multi-environment matrix)
- Task 0.4: Setup branch protection rules
- Task 0.5: Create issue templates
- Task 0.6: Validation - Create test PR to verify all checks

**Dependencies**: None (foundational)

**Success Criteria**: All developer experience components operational before Phase 1 begins.

---

#### 3.14.1 Phase 1: Foundation & Data Models

**Goal**: Establish core data structures and storage abstraction to enable all higher-level features.

**Task 1.1: Define Core Data Models**
- **What**: Implement data classes from Section 3.3
  - `Relationship`, `RelationshipType` (Section 3.3.1)
  - `RelationshipGraph` structure (Section 3.3.2)
  - `CacheEntry`, `CacheStatistics` (Section 3.3.3)
- **Requirements**: DD-4 (JSON-compatible primitives for future persistence)
- **Success Criteria**:
  - All dataclasses instantiate correctly
  - Can serialize to/from dict (for future JSON export)
  - Unit tests pass (T-4.8: validate all required fields)
- **Tests**: T-4.6 (exported graph contains all required fields)
- **Dependencies**: None (foundational)

**Task 1.2: Implement Storage Abstraction**
- **What**: Create `RelationshipStore` interface and `InMemoryStore` implementation (Section 3.4.7)
  - Methods: `add_relationship()`, `remove_relationship()`, `get_relationships()`, `get_all_relationships()`, `export_graph()`
- **Requirements**: DD-4 (enable v0.2.0 SQLite migration with 1-line change), FR-23 (graph export capability)
- **Success Criteria**:
  - Interface defined with type hints
  - `InMemoryStore` implements all interface methods
  - Fast lookups (O(1) for file-based queries)
  - Can swap to mock implementation for testing
- **Tests**: T-4.8 (graph maintained in-memory), test with mock store in isolation
- **Dependencies**: Task 1.1 (needs data models)

**Task 1.3: Implement Relationship Graph Operations**
- **What**: Build graph management logic (Section 3.3.2)
  - Add/remove relationships (atomic operations)
  - Bidirectional indexing (source → targets, target ← sources)
  - Query operations: get_dependents(), get_dependencies()
- **Requirements**: FR-18 (list dependent files), ~~EC-1 (detect circular dependencies - deferred to v0.1.1+)~~
- **Success Criteria**:
  - Atomic updates (no partial state)
  - Bidirectional queries work correctly
  - Validation checks for consistency (no orphaned references)
- **Tests**: T-4.1 through T-4.4 (dependent files listed, warnings for 3+ files, bidirectional tracking, query API)
- **Edge Cases**: ~~EC-1 (circular import detection - deferred)~~, EC-19 (graph corruption recovery)
- **Dependencies**: Task 1.2 (needs storage abstraction)

**Task 1.4: Setup Project Structure and Configuration**
- **What**: Initialize Python project with dependencies, configuration loading
  - Project skeleton: `src/`, `tests/`, `pyproject.toml`
  - Configuration loading: `.cross_file_context_links.yml` parser (Section 3.10.5)
  - Logging setup (structured logging to `.cross_file_context_logs/`)
  - **Dependency license verification** (Section 1.5):
    - Add `pip-licenses` to dev dependencies
    - Create `scripts/check_licenses.py` to verify all dependencies
    - Add pre-commit hook or CI check to fail on prohibited licenses (GPL, AGPL, LGPL)
    - Generate `THIRD_PARTY_LICENSES.txt` documenting all dependency licenses
- **Requirements**: FR-49 (configurable parameters), NFR-5 (local operation only), Section 1.5 (license compatibility)
- **Success Criteria**:
  - Configuration loads with defaults if file missing
  - Invalid parameters logged as warnings, defaults used
  - Configuration validation (ranges, types)
  - License check passes (no GPL/AGPL/LGPL dependencies)
  - All third-party licenses documented
- **Tests**: T-10.5 (configuration parameters adjustable), license verification in CI
- **Dependencies**: None (foundational)

---

#### 3.14.2 Phase 2: AST Parsing & Basic Relationship Detection

**Goal**: Parse Python files and detect import/function call relationships.

**Task 2.1: Implement AST Parser Framework**
- **What**: Build AST parsing pipeline (Section 3.5.1)
  - File reading with UTF-8/latin-1 fallback encoding
  - AST parsing using Python's `ast` module
  - Error recovery for syntax errors (skip file, log, continue)
  - Detector dispatch pattern (DD-1)
- **Requirements**: DD-1 (modular detector plugins), EC-18 (parsing failures gracefully handled)
- **Success Criteria**:
  - Can parse valid Python files into AST
  - Syntax errors logged but don't crash system
  - Detector registry allows adding new detectors without modifying parser
- **Tests**: T-1.8 (incremental updates when file edited), T-6.10 (fail-safe principle)
- **Edge Cases**: EC-18 (syntax errors), encoding errors
- **Dependencies**: Task 1.3 (needs graph to store relationships)

**Task 2.2: Implement ImportDetector**
- **What**: Detect import relationships (Section 3.5.2.1, Section 3.4.4)
  - Patterns: `import module`, `from module import name`
  - Relative imports: `from . import`, `from .. import`
  - Module resolution: project-local vs standard library vs third-party
- **Requirements**: FR-1 (detect imports), DD-1 (detector plugin pattern)
- **Success Criteria**:
  - Detects all import statement types
  - Resolves project-local imports to file paths
  - Tracks import style and imported names in metadata
- **Tests**: T-1.1 (import statements detected), T-1.2 (from...import detected)
- **Dependencies**: Task 2.1 (needs AST parser framework)

**Task 2.3: Implement AliasedImportDetector**
- **What**: Detect aliased imports (Section 3.5.2.4)
  - Patterns: `import foo as bar`, `from foo import baz as qux`
  - Track both original name and alias in metadata
- **Requirements**: EC-3 (aliased imports tracked)
- **Success Criteria**:
  - Detects both module and name aliases
  - Metadata includes original and alias names
  - Function call matching works with both names
- **Tests**: T-1.3 (aliased imports tracked)
- **Edge Cases**: EC-3 (alias usage tracking)
- **Dependencies**: Task 2.2 (extends import detection)

**Task 2.4: Implement ConditionalImportDetector**
- **What**: Detect conditional imports (Section 3.5.2.5)
  - Patterns: `if TYPE_CHECKING:`, `if sys.version_info >=:`
  - Mark as conditional in metadata
- **Requirements**: EC-5 (conditional imports tracked)
- **Success Criteria**:
  - Detects TYPE_CHECKING conditionals
  - Metadata marks relationship as conditional
- **Tests**: T-1.5 (conditional imports tracked)
- **Edge Cases**: EC-5 (conditional import handling)
- **Dependencies**: Task 2.2 (extends import detection)

**Task 2.5: Implement WildcardImportDetector**
- **What**: Detect wildcard imports (Section 3.5.2.6)
  - Pattern: `from module import *`
  - Track at module level (cannot track specific names)
  - Optional warning (configurable, default: false)
- **Requirements**: EC-4 (wildcard imports with limitations)
- **Success Criteria**:
  - Detects wildcard imports
  - Tracks as module-level dependency
  - Warning configurable via `warn_on_wildcards`
  - Context injection notes limitation
- **Tests**: T-1.4 (wildcard imports tracked with limitations)
- **Edge Cases**: EC-4 (wildcard import limitations documented)
- **Dependencies**: Task 2.2 (extends import detection)

**Task 2.6: Implement FunctionCallDetector (Simple Calls Only)**
- **What**: Detect simple function calls (Section 3.5.2.2)
  - Patterns: `function_name(args)`, `module.function(args)` (if module imported)
  - v0.1.0 limitation: NO method chains or nested attributes (deferred to v0.1.1/v0.1.2)
- **Requirements**: FR-2 (detect function calls), DD-1 (incremental complexity via plugins)
- **Success Criteria**:
  - Detects simple direct function calls
  - Resolves function to defining file if imported
  - Does NOT attempt to handle method chains (explicitly out of scope for v0.1.0)
- **Tests**: T-1.6 (function call relationships tracked within codebase)
- **Dependencies**: Task 2.2 (needs import tracking to resolve functions)

**Task 2.7: Implement ClassInheritanceDetector**
- **What**: Detect class inheritance (Section 3.5.2.3)
  - Patterns: single inheritance, multiple inheritance
  - Track parent class names and inheritance order
- **Requirements**: FR-3 (detect class relationships)
- **Success Criteria**:
  - Detects single and multiple inheritance
  - Resolves parent classes to defining files
  - Tracks inheritance order in metadata
- **Tests**: Part of T-1 relationship detection tests
- **Dependencies**: Task 2.2 (needs import tracking to resolve parent classes)

**Task 2.8: ~~Implement Circular Import Detection~~ DEFERRED to v0.1.1+**
- **Deferral Rationale**: See Section 3.5.5 for detailed analysis
  - No infinite loop risk: All graph operations use O(1) index lookups, no deep traversals
  - Cycle detection would be the ONLY deep traversal operation in the system
  - Cost (DFS after every import) outweighs benefit (code quality warning)
- **Original requirements**: ~~FR-30 (warn on circular imports)~~, ~~EC-1 (circular dependency detection)~~
- **If implemented in v0.1.1+**: Use batch approach (Tarjan's algorithm) rather than per-import detection

---

#### 3.14.3 Phase 3: File Watching & Incremental Updates

**Goal**: Monitor file system changes and update relationship graph incrementally.

**Task 3.1: Implement FileWatcher with Language Dispatch**
- **What**: File system monitoring with language-agnostic design (Section 3.6)
  - Library: `watchdog` (cross-platform, Section 3.6.1)
  - Event types: create, modify, delete, move
  - Extension-based analyzer dispatch (`.py` → PythonAnalyzer)
  - Ignore patterns: `.gitignore` + hardcoded sensitive files
- **Requirements**: DD-2 (language-agnostic watcher for future expansion), NFR-7 (respect .gitignore), NFR-8 (ignore dependencies)
- **Success Criteria**:
  - Detects file create/modify/delete events
  - Dispatches to correct analyzer based on extension
  - Respects ignore patterns (.gitignore, .pyc, __pycache__, venv, etc.)
  - No language-specific logic in FileWatcher itself (testable with mock analyzers)
- **Tests**: T-9.3 (file watcher integration), integration tests with mock TypeScript analyzer (validates DD-2)
- **Dependencies**: Task 2.1 (needs PythonAnalyzer to dispatch to)

**Task 3.2: Implement Event Debouncing and Batching**
- **What**: Handle rapid file changes efficiently (Section 3.6.2)
  - Debounce: 200ms silence window before processing
  - Batch: Collect events within 500ms window for bulk operations (e.g., git checkout)
  - Priority queue: User edits prioritized over tool edits
- **Requirements**: NFR-1 (incremental update <200ms), Section 3.6.2 (batch processing)
- **Success Criteria**:
  - Rapid saves collapsed into single analysis pass
  - Bulk operations (git checkout) processed as batch
  - User edits processed first in priority queue
- **Tests**: Performance test for incremental updates (T-7.3)
- **Dependencies**: Task 3.1 (needs FileWatcher)

**Task 3.3: Implement Incremental Graph Updates**
- **What**: Update graph when files change (Section 3.6.3)
  - On modify: Remove old relationships, re-analyze, add new relationships
  - On delete: Remove all relationships, mark as deleted (EC-14)
  - On create: Analyze and add to graph
  - Atomic updates (no partial state)
- **Requirements**: FR-8 (incremental graph updates), NFR-1 (<200ms incremental update)
- **Success Criteria**:
  - File modification triggers re-analysis of only that file
  - Relationships updated correctly
  - Graph remains consistent after updates
  - Performance target met (<200ms per file)
- **Tests**: T-1.8 (incremental updates when file edited), T-7.3 (incremental update <200ms)
- **Edge Cases**: EC-14 (deleted files), EC-20 (concurrent modifications)
- **Dependencies**: Task 3.2 (needs event processing), Task 1.3 (needs graph operations)

**Task 3.4: Implement File Deletion Handling**
- **What**: Clean up graph and warn about broken references (Section 3.6.4)
  - Remove all relationships involving deleted file
  - Mark in metadata: `deleted: true`, `deletion_time`
  - Emit warnings for files that imported from deleted file
- **Requirements**: EC-14 (deleted files handled)
- **Success Criteria**:
  - Deleted file removed from graph
  - Broken references detected
  - Warnings emitted for dependent files
  - Context injection notes deletion if relevant
- **Tests**: Integration test for file deletion workflow
- **Edge Cases**: EC-14 (file deletion, broken references)
- **Dependencies**: Task 3.3 (part of incremental updates)

**Task 3.5: Parse .gitignore and Pytest Configuration**
- **What**: Respect project-specific ignore and test patterns (Section 3.6.1, Section 3.9.2)
  - Parse `.gitignore` using gitignore pattern matching
  - Parse pytest config files: `pytest.ini`, `pyproject.toml`, `setup.cfg` (DD-3)
  - Extract `testpaths` and `python_files` patterns
  - Apply to file watcher ignore list and test module classification
- **Requirements**: DD-3 (pytest config parsing), NFR-7 (respect .gitignore)
- **Success Criteria**:
  - Reads .gitignore, applies patterns to file watcher
  - Reads pytest config (if present), extracts test patterns
  - Falls back to default patterns if config not found
  - No runtime dependency on pytest (static parsing only)
- **Tests**: T-6.1 (test module identification), validation with various pytest configs
- **Dependencies**: Task 3.1 (FileWatcher needs ignore patterns)

---

#### 3.14.4 Phase 4: Context Injection & Caching

**Goal**: Implement core user-facing feature: automatic context injection during file reads.

**Task 4.1: Implement Working Memory Cache**
- **What**: LRU cache with expiry policy (Section 3.7)
  - Data structure: OrderedDict or custom LRU
  - Cache key: (file_path, line_range)
  - Expiry: 10 minutes from last access (configurable)
  - Size limit: 50KB (configurable)
  - Operations: get(), put(), invalidate(), evict_expired(), evict_lru()
- **Requirements**: FR-13 (working memory cache), FR-14 (10-min expiry), FR-16 (size limit), NFR-4 (memory <500MB)
- **Success Criteria**:
  - LRU eviction works correctly
  - Expiry check on every access
  - Size limit enforced
  - Statistics tracked (hit rate, miss rate, peak size)
- **Tests**: T-3.1 through T-3.5 (cache hit/miss, invalidation, size limit, statistics)
- **Edge Cases**: EC-15 (cache size exceeded), EC-16 (long-running sessions)
- **Dependencies**: Task 1.1 (needs CacheEntry data model)

**Task 4.2: Implement MCP Server Protocol Layer**
- **What**: Create MCP server with tool registration (Section 3.4.1)
  - Initialize MCP server
  - Register tools: `read_with_context`, `get_relationship_graph`
  - Request/response handling per MCP specification
  - Error response formatting
- **Requirements**: DD-6 (layered architecture: MCP protocol layer separate from business logic)
- **Success Criteria**:
  - MCP server starts without errors
  - Tools registered correctly
  - Can receive and respond to tool invocations
  - ZERO business logic in this layer (all in CrossFileContextService)
- **Tests**: T-9.1 (MCP server starts), T-9.2 (Read tool works), T-9.4 (no conflicts with other MCP servers)
- **Dependencies**: None (protocol layer is independent, though needs service layer to be useful)

**Task 4.3: Implement CrossFileContextService**
- **What**: Business logic coordinator that owns all components (Section 3.4.2)
  - Owns: PythonAnalyzer, FileWatcher, Cache, Store, WarningSystem, MetricsCollector
  - Context injection workflow (Section 3.8)
  - High-level API: read_file_with_context(), get_relationship_graph(), get_dependents()
- **Requirements**: DD-6 (business logic layer separate from MCP), DD-5 (inline context injection)
- **Success Criteria**:
  - All components initialized correctly
  - Context injection workflow orchestrated properly
  - Storage-agnostic (uses RelationshipStore interface)
  - API methods work correctly
- **Tests**: T-9.2 (Read tool with context injection), integration tests for workflow
- **Dependencies**: Tasks 1.3 (graph), 2.1 (analyzer), 3.1 (watcher), 4.1 (cache)

**Task 4.4: Implement Context Injection Content Selection**
- **What**: Query graph, prioritize dependencies, assemble snippets (Section 3.8.2)
  - Query relationships for target file
  - Prioritize: direct > transitive, recent > old, high-usage > low-usage
  - Check cache for each dependency
  - Assemble snippets until token budget exhausted
- **Requirements**: FR-9 (inject relevant context), FR-10 (token limit 500), FR-19/FR-20 (warn if function used in 3+ files)
- **Success Criteria**:
  - Dependencies prioritized correctly
  - Cache checked before re-reading files
  - Token budget respected (hard limit 500, configurable)
  - High-usage functions identified (3+ files) and warned
- **Tests**: T-2.1 through T-2.3 (context injected, token limit, relevance)
- **Dependencies**: Task 4.3 (needs service orchestration), Task 4.1 (needs cache)

**Task 4.5: Implement Context Injection Formatting**
- **What**: Format injected context (Section 3.8.3)
  - Header: `[Cross-File Context]`
  - Dependency summary
  - Snippets: location + signature only (NOT full implementation)
  - Special cases: wildcard imports, large functions, deleted files
  - Cache age indicator
  - Separator: `---`
- **Requirements**: FR-10 (location + signature only, 58% token reduction vs full bodies), DD-5 (inline injection format)
- **Success Criteria**:
  - Format matches specification (Section 3.8.3)
  - Claude can distinguish context from file content
  - Special cases handled (wildcards, large functions, deletions)
  - Token count accurate
- **Tests**: T-2.2 (injection format correct), visual inspection of output
- **Edge Cases**: EC-4 (wildcard imports noted), EC-12 (large functions truncated), EC-14 (deleted files noted)
- **Dependencies**: Task 4.4 (needs content selection)

**Task 4.6: Implement Cache Invalidation**
- **What**: Invalidate cache on file modification (Section 3.7.3.3)
  - FileWatcher triggers invalidation on modify/delete events
  - Invalidate all entries for modified file
  - Invalidate entries for snippets from modified file
- **Requirements**: FR-15 (invalidate on file edit)
- **Success Criteria**:
  - Modified file triggers cache invalidation
  - Stale entries removed immediately
  - Cache remains consistent with file system
- **Tests**: T-3.3 (cache invalidation on file edit)
- **Edge Cases**: EC-11 (stale cache after external edit)
- **Dependencies**: Task 4.1 (cache), Task 3.1 (file watcher)

---

#### 3.14.5 Phase 5: Warning System & Dynamic Pattern Detection

**Goal**: Detect and warn about unhandled dynamic Python patterns.

**Task 5.1: Implement Test vs Source Module Classification**
- **What**: Distinguish test modules from source modules (Section 3.9.2)
  - Pattern matching: `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`, `**/conftest.py`
  - Pytest config parsing: Extract test patterns from config files
  - Classification function: is_test_module(file_path) → bool
- **Requirements**: DD-3 (pytest config parsing), FR-32 (test module identification)
- **Success Criteria**:
  - Default patterns match test files correctly
  - Pytest config patterns applied if available
  - No runtime pytest dependency (static parsing only)
- **Tests**: T-6.1 (test module identification works correctly)
- **Dependencies**: Task 3.5 (pytest config parsing)

**Task 5.2: Implement Dynamic Pattern Detectors**
- **What**: Detect unhandled dynamic patterns in AST (Section 3.9.1, Section 3.5.4)
  - Dynamic dispatch: `getattr(obj, dynamic_name)()` (EC-6)
  - Monkey patching: `module.attr = replacement` (EC-7)
  - exec/eval: `exec(code_string)`, `eval(expression)` (EC-9)
  - Decorators: Track decorator usage (EC-8)
  - Metaclasses: Detect custom metaclasses (EC-10)
- **Requirements**: FR-33 through FR-37, EC-6 through EC-10, FR-42 (fail-safe: warn but don't track incorrectly)
- **Success Criteria**:
  - All dynamic patterns detected in AST
  - Patterns marked as "untrackable" in metadata
  - NO incorrect relationships added to graph (fail-safe principle)
  - Test vs source distinction applied correctly
- **Tests**: T-6.2 through T-6.6 (warnings emitted correctly for each pattern type)
- **Edge Cases**: EC-6 through EC-10 (all dynamic patterns)
- **Dependencies**: Task 2.1 (AST parser), Task 5.1 (test classification)

**Task 5.3: Implement Warning Emission and Formatting**
- **What**: Format and emit structured warnings (Section 3.9.3)
  - JSON format with all required fields (type, file, line, severity, pattern, message, explanation, timestamp)
  - Human-readable display format
  - Actionable guidance where applicable
- **Requirements**: FR-38 (structured warning format)
- **Success Criteria**:
  - All warnings include required fields
  - Machine-parseable JSON structure
  - Human-readable display
  - Actionable guidance provided
- **Tests**: T-6.7 (warning message format compliance)
- **Dependencies**: Task 5.2 (pattern detection)

**Task 5.4: Implement Warning Suppression**
- **What**: Configuration-based warning suppression (Section 3.9.4)
  - File-level: `suppress_warnings: ["path/to/file.py"]`
  - Directory-level: `suppress_warnings: ["tests/**/*"]`
  - Pattern-type: `suppress_dynamic_dispatch_warnings: true`
  - Per-file pattern-type: `file_specific_suppressions: {...}`
  - Precedence rules
- **Requirements**: FR-39 (file-level suppression), FR-40 (directory-level suppression)
- **Success Criteria**:
  - All suppression granularity levels work
  - Precedence rules applied correctly
  - Invalid config handled gracefully
- **Tests**: T-6.8 (warning suppression configuration works)
- **Dependencies**: Task 5.3 (warning emission), Task 1.4 (configuration loading)

**Task 5.5: Implement Warning Logging**
- **What**: Log warnings to JSONL file (Section 3.9.5)
  - Log location: `.cross_file_context_logs/warnings.jsonl`
  - One JSON object per line
  - Real-time logging (flush immediately)
  - Integration with session metrics
- **Requirements**: FR-41 (structured warning log)
- **Success Criteria**:
  - Warnings logged to JSONL file
  - Format is machine-parseable
  - Session metrics include warning statistics
- **Tests**: T-6.9 (warnings logged to structured format)
- **Dependencies**: Task 5.3 (warning emission)

---

#### 3.14.6 Phase 6: Metrics, Logging & Observability

**Goal**: Implement comprehensive metrics and logging for data-driven tuning.

**Task 6.1: Implement Context Injection Event Logging**
- **What**: Log every context injection event (Section 3.8.5)
  - Log location: `.cross_file_context_logs/injections.jsonl`
  - Fields: timestamp, source_file, target_file, relationship_type, snippet, cache_age_seconds, token_count, context_token_total
  - Real-time logging
- **Requirements**: FR-26 (log all injections), FR-27 (structured format), FR-28 (JSONL compatible with Claude Code logs)
- **Success Criteria**:
  - All injections logged with required fields
  - JSONL format parseable by standard tools
  - File size remains manageable (<10MB per 4-hour session expected)
- **Tests**: T-5.1 through T-5.7 (injection logging comprehensive tests)
- **Dependencies**: Task 4.5 (context injection)

**Task 6.2: Implement Session Metrics Collection**
- **What**: Collect comprehensive session metrics (Section 3.10.1)
  - Cache performance: hit rate, miss rate, peak size, expiry times
  - Context injection: token counts (min, max, median, p95), threshold exceedances
  - Relationship graph: file count, relationship count, most-connected files
  - Function usage distribution
  - Re-read patterns
  - Performance: parsing times, injection latency
  - Warning statistics
- **Requirements**: FR-43 (emit metrics at session end), FR-44 through FR-46 (metrics categories and structure)
- **Success Criteria**:
  - All metrics categories collected
  - Metrics written to `.cross_file_context_logs/session_metrics.jsonl`
  - JSONL format parseable
  - Configuration values captured in metrics
- **Tests**: T-10.1 through T-10.6 (session metrics comprehensive tests)
- **Dependencies**: All previous tasks (collects metrics from all components)

**Task 6.3: Implement Relationship Graph Export**
- **What**: Export graph to structured JSON format (Section 3.10.3)
  - On-demand export via API
  - Automatic export at session end (optional)
  - JSON structure: metadata, files, relationships, graph_metadata
  - Both absolute and relative file paths
- **Requirements**: FR-23 (graph export capability), FR-25 (structured export format)
- **Success Criteria**:
  - Export produces valid JSON
  - Contains all relationships and metadata
  - External tools can parse and analyze
  - Can be invoked via MCP tool `get_relationship_graph`
- **Tests**: T-4.5 through T-4.7 (graph export validation)
- **Dependencies**: Task 1.2 (storage abstraction), Task 4.2 (MCP server for tool exposure)

**Task 6.4: Implement Query API**
- **What**: Programmatic access to system state (Section 3.10.4)
  - Methods: get_recent_injections(), get_relationship_graph(), get_dependents(), get_dependencies(), get_session_metrics(), get_cache_statistics()
  - Expose via internal Python API (v0.1.0)
  - Future: Expose as MCP tools for Claude Code access
- **Requirements**: FR-29 (query API for injection events)
- **Success Criteria**:
  - All API methods work correctly
  - Can query recent injections
  - Can query graph structure
  - Can access metrics in progress
- **Tests**: T-5.5 (API retrieves recent injection events)
- **Dependencies**: Task 6.1 (injection logging), Task 6.2 (metrics), Task 6.3 (graph export)

**Task 6.5: Implement Metrics Analysis Tool**
- **What**: Standalone script to analyze session metrics (Section 3.10.6)
  - Parse session metrics JSONL
  - Compute aggregate statistics across sessions
  - Identify outliers and patterns
  - Suggest optimal configuration values
  - Human-readable report output
- **Requirements**: FR-48 (metrics analysis tool)
- **Success Criteria**:
  - Parses JSONL metrics correctly
  - Produces human-readable report
  - Suggests configuration tuning based on data
  - Example output matches specification
- **Tests**: T-10.7 (analysis tool functionality)
- **Dependencies**: Task 6.2 (session metrics to analyze)

---

#### 3.14.7 Phase 7: Testing & Quality Assurance

**Goal**: Comprehensive test coverage to ensure correctness and performance.

**Task 7.1: Implement Unit Tests for Core Components**
- **What**: Test each component in isolation (Section 3.13.2)
  - Relationship detectors with AST fixtures
  - Cache operations with mocked timestamps
  - Warning system with fixture files
  - Metrics collector with synthetic events
  - Graph operations (add, remove, query)
- **Requirements**: Section 3.13.1 (testing philosophy), coverage >80%
- **Success Criteria**:
  - >80% line coverage for business logic
  - Each detector tested independently
  - All edge cases have test cases (EC-1 through EC-20)
  - Tests run in <10 seconds (pre-commit target)
- **Tests**: Foundation for all T-# test categories
- **Dependencies**: All implementation tasks (tests validate implementation)

**Task 7.2: Implement Integration Tests**
- **What**: Test component interactions (Section 3.13.2)
  - PythonAnalyzer + Detectors (full AST pipeline with real Python files)
  - Service + Store + Cache (context injection workflow end-to-end)
  - FileWatcher + Analyzer (file change events trigger correct analysis)
  - MCP Server + Service (tool invocations produce correct responses)
- **Requirements**: Section 3.13.2 (integration testing)
- **Success Criteria**:
  - End-to-end workflows work correctly
  - Components integrate without errors
  - Real-world scenarios tested (not just unit test mocks)
- **Tests**: T-9.1 through T-9.6 (Claude Code integration tests)
- **Dependencies**: Task 7.1 (unit tests provide foundation)

**Task 7.3: Implement Functional Test Suite**
- **What**: Validate all functional requirements (Section 3.13.2)
  - Create representative test codebase (50-100 Python files with known dependencies)
  - Test all categories T-1 through T-10 from prd_testing.md
  - Edge case coverage for EC-1 through EC-20
- **Requirements**: prd_testing.md test categories, Section 8.2 (functional testing)
- **Success Criteria**:
  - All test categories T-1 through T-10 pass
  - Edge cases handled correctly
  - Test codebase includes circular dependencies, wildcards, dynamic patterns
- **Tests**: All T-# test cases from prd_testing.md
- **Dependencies**: Task 7.2 (builds on integration tests)

**Task 7.4: Implement Performance Tests**
- **What**: Validate performance targets (Section 3.13.2, prd_testing.md Section 8.3)
  - Indexing: 100 files <10s, 1000 files <2min (T-7.1, T-7.2)
  - Incremental updates: <200ms per file (T-7.3)
  - Context injection latency: <50ms (T-8.1)
  - Memory footprint: <500MB for 10,000 files (T-7.4)
- **Requirements**: NFR-1 (<200ms incremental), NFR-2 (<50ms injection), NFR-4 (<500MB memory)
- **Success Criteria**:
  - All performance targets met
  - Benchmarks automated and repeatable
  - Performance regression tests in CI
- **Tests**: T-7.1 through T-7.4, T-8.1 through T-8.4
- **Dependencies**: Task 7.3 (functional tests ensure correctness before optimizing)

**Task 7.5: Setup Developer Experience Infrastructure**
- **What**: Implement all developer experience requirements (Section 3.15)
  - Pre-commit hooks: formatters (black, isort), linters (ruff, mypy), fast unit tests
  - GitHub Actions: lightweight checks workflow, comprehensive tests workflow (multi-environment matrix)
  - Branch protection: main branch requires PR + checks + review
  - Issue templates: with PRD/TDD reference fields
- **Requirements**: Section 3.15 (developer experience requirements), dev_experience.md
- **Success Criteria**:
  - Pre-commit hook runs locally and prevents commits on failures
  - GitHub PR checks run automatically and display results in UI
  - Multi-environment test matrix (Python 3.8-3.12, Ubuntu) passes
  - Main branch cannot accept direct commits
  - All checks are required for PR merge
- **Testing**: Create test PR with intentional formatting/linting/test errors to verify detection
- **Dependencies**: Tasks 7.1 through 7.4 (test suites must exist to run in CI)
- **IMPORTANT**: This task MUST be completed before starting Phase 1 tasks (Section 3.15.4)

---

#### 3.14.8 Phase 8: UAT Preparation & Deployment

**Goal**: Prepare for user acceptance testing and production deployment.

**Task 8.1: Create Test Fixtures and Documentation**
- **What**: Prepare UAT environment
  - Representative test codebase (50-100 files per prd_testing.md Section 8.1)
  - User documentation (installation, configuration, usage)
  - Known issues and limitations documented
  - Quick start guide
- **Requirements**: prd_testing.md Section 8.1 (test environment setup)
- **Success Criteria**:
  - Test codebase has documented dependencies and edge cases
  - Installation guide works for fresh environment
  - Configuration examples provided
  - Limitations clearly documented
- **Dependencies**: Task 7.3 (can reuse functional test fixtures)

**Task 8.2: Alpha Testing (Internal)**
- **What**: Internal developer testing (prd_testing.md Section 8.5, UAT Phase 1)
  - 3-5 internal developers
  - Focus: Basic functionality, major bugs
  - Duration: Week 1 of UAT
  - Collect metrics: re-read reduction, cache hit rate, performance
- **Requirements**: prd_testing.md Section 8.5 (UAT Phase 1)
- **Success Criteria**:
  - No critical bugs
  - 70% re-read reduction achieved
  - Metrics collected for all sessions
- **Dependencies**: Task 8.1 (documentation for testers)

**Task 8.3: Beta Testing (External)**
- **What**: External developer testing (prd_testing.md Section 8.5, UAT Phase 2)
  - 10-15 external developers
  - Focus: Real-world usage, edge cases
  - Duration: Weeks 2-3 of UAT
  - Collect feedback and metrics
- **Requirements**: prd_testing.md Section 8.5 (UAT Phase 2)
- **Success Criteria**:
  - <30% re-read rate
  - >80% satisfaction
  - Edge cases identified and addressed
- **Dependencies**: Task 8.2 (alpha bugs fixed)

**Task 8.4: Pilot Deployment**
- **What**: Larger-scale deployment (prd_testing.md Section 8.5, UAT Phase 3)
  - 50+ developers
  - Focus: Performance at scale, user feedback
  - Duration: Week 4 of UAT
- **Requirements**: prd_testing.md Section 8.5 (UAT Phase 3)
- **Success Criteria**:
  - All primary metrics met (NFR-1 through NFR-8)
  - <5% opt-out rate
  - Scalability validated
- **Dependencies**: Task 8.3 (beta feedback incorporated)

**Task 8.5: Production Release Preparation**
- **What**: Final release prep
  - Version tagging (v0.1.0)
  - Release notes
  - Distribution packaging (PyPI or internal distribution)
  - Monitoring and support plan
- **Success Criteria**:
  - Release package tested
  - Documentation complete
  - Support process defined
- **Dependencies**: Task 8.4 (pilot successful)

---

#### 3.14.9 Cross-Cutting Concerns

These tasks span multiple phases and should be addressed throughout development:

**Task CC-1: Error Handling Implementation**
- **What**: Implement error handling strategies from Section 3.11
  - Parsing failures (EC-18): Skip file, log, continue
  - File system errors: Handle permission denied, not found, concurrent modifications
  - Graph corruption (EC-19): Detect, log, rebuild
  - Memory pressure (EC-15, EC-16, EC-17): LRU eviction, rolling window, file size limits
  - MCP protocol errors: Proper error responses
  - Graceful degradation: Continue operation when subsystems fail
- **Requirements**: FR-42 (fail-safe principle), all EC-# edge cases, NFR-11 (graceful degradation)
- **Success Criteria**:
  - No crashes from exceptions
  - All error scenarios logged
  - System continues operating with degraded functionality
  - Users notified appropriately
- **Tests**: Error injection tests for all scenarios
- **Timeline**: Implement during relevant phases, validate in Phase 7

**Task CC-2: Security & Compliance**
- **What**: Implement security measures from Section 3.12
  - Code execution safety: AST parsing only, no exec/eval
  - File system access: Respect permissions, stay in project root, ignore sensitive files
  - Data privacy: Local operation, metrics anonymization, no credential storage
  - Resource limits: Memory limits, file size limits, DoS prevention
- **Requirements**: NFR-5 (local operation), NFR-6 (no external transmission), all security requirements
- **Success Criteria**:
  - No dynamic code execution
  - Sensitive files ignored
  - All data stays local
  - Resource limits enforced
- **Tests**: Security-focused test cases
- **Timeline**: Implement during relevant phases, security review in Phase 7

**Task CC-3: Performance Optimization**
- **What**: Meet all performance targets
  - Indexing: <10s for 100 files (T-7.1)
  - Incremental: <200ms per file (NFR-1, T-7.3)
  - Injection: <50ms (NFR-2, T-8.1)
  - Memory: <500MB for 10,000 files (NFR-4, T-7.4)
  - Profile and optimize hot paths
- **Requirements**: All NFR performance targets
- **Success Criteria**:
  - All performance targets met
  - No performance regressions
  - Profiling data collected
- **Timeline**: Profile in Phase 5, optimize in Phase 6, validate in Phase 7

---

### 3.15 Developer Experience Requirements

**Reference**: See [dev_experience.md](./dev_experience.md) for general developer experience design principles.

This section specifies the project-specific implementation of developer experience requirements to ensure high-quality, maintainable code and efficient team collaboration.

#### 3.15.1 Development Workflow Requirements

**Issue-Driven Development**:
- **Requirement**: All development MUST be associated with a GitHub Issue
- **Rationale**: Ensures traceability, discussion history, and alignment with PRD/TDD
- **Implementation**: Issue templates in `.github/ISSUE_TEMPLATE/` with required links to PRD/TDD sections

**Feature Branch Workflow**:
- **Requirement**: All development MUST occur in Git feature branches
- **Branch naming**: `issue-<number>-<short-description>` (e.g., `issue-42-add-import-detector`)
- **Protection**: Main branch requires PR approval, no direct commits

**Pull Request Workflow**:
- **Requirement**: All changes MUST go through GitHub Pull Request process
- **PR Description**: Must reference issue number and relevant TDD sections
- **Review**: At least one approval required before merge
- **Checks**: All automated checks must pass (see sections 3.15.2 and 3.15.3)

#### 3.15.2 Lightweight Workflow (Pre-Commit and PR Fast Checks)

**Purpose**: Fast feedback loop to catch issues before code review

**Execution Points**:
1. **Git pre-commit hook**: Runs locally before commit is created
2. **GitHub PR check**: Runs on every push to PR branch
3. **Results accessibility**: PR check results must be viewable in GitHub UI

**Components**:

**Code Formatting** (Auto-fix where possible):
- **Tool**: `black` (Python code formatter)
  - Configuration: Line length 100 characters (aligns with project style)
  - Target: All `.py` files in `src/` and `tests/`
- **Tool**: `isort` (Import statement organizer)
  - Configuration: Compatible with `black`, standard library imports first

**Linting** (Fail on errors, warn on violations):
- **Tool**: `ruff` (Fast Python linter, replaces flake8/pylint)
  - Checks: F (pyflakes), E/W (pycodestyle), I (isort), N (naming), etc.
  - Configuration: `.ruff.toml` with project-specific rules
- **Tool**: `mypy` (Static type checker)
  - Configuration: Strict mode for `src/`, lenient for `tests/`
  - Target: Python 3.8+ compatibility (see Section 1.1)

**Unit Tests** (Fast subset):
- **Tool**: `pytest` with `-m "not slow"` marker
- **Scope**: Core unit tests only (detector plugins, cache operations, warning system)
- **Timeout**: <10 seconds total (see Section 3.13.5)
- **Coverage**: Not enforced at pre-commit (to maintain speed)

**Implementation**:
- **Pre-commit framework**: Use `pre-commit` tool with `.pre-commit-config.yaml`
- **GitHub Action**: `.github/workflows/lightweight-checks.yml`
  - Runs on: `pull_request`, `push` to feature branches
  - Displays: Formatting diffs, linter errors, test failures in PR UI
  - Status: Required check for PR merge

#### 3.15.3 Issue-Level Workflow (PR Comprehensive Checks)

**Purpose**: Environment compatibility validation before merge

**Execution Point**: GitHub PR check (runs in parallel with lightweight checks)

**Components**:

**Multi-Environment Unit Tests**:
- **Python versions**: 3.8, 3.9, 3.10, 3.11, 3.12
  - Rationale: Cover Python 3.8+ constraint (Section 1.1) and latest stable releases
  - Matrix strategy: Test all versions in parallel on GitHub Actions
- **Operating system**: Ubuntu only
  - Rationale: Primary target platform for most Claude Code users
  - Sufficient coverage for core functionality validation
- **Test scope**: Full unit test suite + integration tests (not performance/UAT)
- **Timeout**: <5 minutes per environment

**Implementation**:
- **GitHub Action**: `.github/workflows/comprehensive-tests.yml`
  - Runs on: `pull_request`
  - Matrix: `{python: [3.8, 3.9, 3.10, 3.11, 3.12], os: [ubuntu-latest]}`
  - Displays: Test results per environment in PR checks UI
  - Status: Required check for PR merge

#### 3.15.4 Development Sequencing Requirement

**Requirement**: All developer experience infrastructure (sections 3.15.2 and 3.15.3) MUST be implemented before starting Phase 1 development tasks (Section 3.14.1).

**Rationale** (from dev_experience.md):
- Prevents technical debt accumulation
- Ensures consistent code quality from day one
- Avoids retrofitting CI/CD to existing code

**Implementation Order**:
1. **Task 0.1**: Setup pre-commit hooks (black, isort, ruff, mypy, pytest fast)
2. **Task 0.2**: Configure GitHub Actions (lightweight checks workflow)
3. **Task 0.3**: Configure GitHub Actions (comprehensive tests workflow with matrix)
4. **Task 0.4**: Setup branch protection rules (require PR, require checks, require review)
5. **Task 0.5**: Create issue templates with PRD/TDD reference fields
6. **Task 0.6**: Validation - Create test PR to verify all checks run and report correctly
7. **Then**: Begin Phase 1 tasks (Section 3.14.1)

---

## 4. Alternatives Considered

This section documents alternative approaches that were evaluated but not chosen. Each alternative is mapped to the corresponding design decision (DD-#) for traceability.

### 4.1 Static Analysis Approach

**Context**: How to detect cross-file relationships in Python code

**Alternative 1: Use Existing Static Analysis Tools (Rejected)**
- **Description**: Integrate pylint, mypy, or Jedi as relationship detection backends
- **Pros**:
  - Battle-tested, comprehensive Python analysis
  - Already handle complex edge cases (EC-1 through EC-10)
  - Community-maintained and regularly updated
- **Cons**:
  - Not designed for relationship tracking (focused on linting/type checking)
  - Harder to extract specific relationship data we need
  - Would couple our feature to external tool's API/data structures
  - Limited control over what gets detected/tracked
  - Cannot easily extend to other languages (different tools per language)
- **Decision**: **Rejected in favor of DD-1** (custom AST parsing with modular detector plugin pattern)
- **Rationale**: Custom approach gives precise control over relationship tracking, enables language-agnostic expansion (DD-2), and provides exactly the data we need for context injection (FR-5, FR-6)

**Alternative 2: Custom AST Parsing with Plugin Pattern (Chosen - DD-1)**
- **Description**: Build language-specific detector plugins using AST libraries
- **Pros**:
  - Precise control over what relationships are tracked
  - Can evolve detectors independently (v0.1.0 simple calls → v0.1.1 method chains)
  - Extracts exact data needed for context injection
  - Language-agnostic plugin interface
- **Cons**:
  - Need to implement and maintain our own parsers
  - Edge cases require custom handling
- **Decision**: **Chosen** - documented as DD-1
- **Supporting Requirements**: FR-1, FR-2, FR-3, FR-4 (relationship detection)

---

### 4.2 File Watcher Implementation

**Context**: How to detect file changes for incremental relationship updates

**Alternative 1: Python-Only File Watcher (Rejected)**
- **Description**: Hardcode watcher for .py files only, use Python-specific logic
- **Pros**:
  - Simpler v0.1.0 implementation
  - Can optimize specifically for Python behavior
- **Cons**:
  - Requires rewrite for TypeScript/Go support (v0.3.0+)
  - Tightly couples watcher to Python detector
  - Harder to test watcher in isolation
- **Decision**: **Rejected in favor of DD-2**
- **Rationale**: v0.3.0 (TypeScript), v0.4.0 (Go) roadmap justifies language-agnostic design from start

**Alternative 2: Language-Agnostic File Watcher (Chosen - DD-2)**
- **Description**: File watcher emits generic file change events, detectors subscribe based on file extensions
- **Pros**:
  - Language expansion only requires new detector, watcher unchanged
  - Cleaner separation of concerns
  - Easier to test independently
  - Supports multi-language projects from day 1
- **Cons**:
  - Slightly more complex interface design upfront
- **Decision**: **Chosen** - documented as DD-2
- **Supporting Requirements**: NFR-1 (incremental updates <200ms), NFR-3 (multi-language expansion)

---

### 4.3 Test File Detection

**Context**: How to distinguish test modules from source modules for warning suppression (EC-6, EC-7, EC-9)

**Alternative 1: Hardcoded Patterns Only (Rejected)**
- **Description**: Detect test files using fixed patterns: `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`
- **Pros**:
  - Simple, fast implementation
  - Covers 90% of common cases
- **Cons**:
  - Misses project-specific test locations
  - Inconsistent with what pytest actually uses
  - User frustration if their test patterns differ
  - False positives/negatives on warnings (EC-6, EC-7, EC-9)
- **Decision**: **Rejected in favor of DD-3**
- **Rationale**: Accuracy is critical for warning system (FR-33 through FR-39)

**Alternative 2: Parse Pytest Configuration (Chosen - DD-3)**
- **Description**: Parse `pytest.ini`, `pyproject.toml`, `setup.cfg` to get actual test paths and patterns
- **Pros**:
  - Matches exactly what pytest uses
  - Respects project-specific configurations
  - Higher accuracy for warning suppression
  - Builds user trust (system understands their setup)
- **Cons**:
  - More complex implementation
  - Need to parse multiple config formats
  - Fallback to defaults if config missing
- **Decision**: **Chosen** - documented as DD-3
- **Supporting Requirements**: FR-32 (test module identification), EC-6, EC-7, EC-9 (test vs source distinction)

---

### 4.4 Persistence Strategy

**Context**: How to store relationship graph and cache data

**Alternative 1: In-Memory with Complex Objects (Rejected)**
- **Description**: Store graph as nested Python objects, use pickle for any persistence
- **Pros**:
  - Simple for v0.1.0 (no persistence needed)
  - Can use rich Python types
- **Cons**:
  - Pickle is Python-specific, brittle, insecure
  - Hard to migrate to SQLite in v0.2.0
  - Cannot inspect data with external tools
  - No backward compatibility story
- **Decision**: **Rejected in favor of DD-4**
- **Rationale**: v0.2.0 roadmap requires SQLite persistence, migration path is critical

**Alternative 2: Serializable Primitives + Storage Abstraction (Chosen - DD-4)**
- **Description**: Use JSON-compatible data structures, abstract storage interface
- **Pros**:
  - Easy migration to SQLite (JSON columns + relational tables)
  - Can export graph for external tools (FR-23, FR-25)
  - Human-readable debugging
  - Storage backend swappable (in-memory → SQLite → other)
- **Cons**:
  - Slightly more verbose code (dict access vs object attributes)
  - Need to implement to_dict/from_dict patterns
- **Decision**: **Chosen** - documented as DD-4
- **Supporting Requirements**: FR-23 (graph export), FR-25 (structured format), v0.2.0 persistence roadmap

---

### 4.5 Context Injection Timing

**Context**: When to inject cross-file context into Claude's awareness

**Alternative 1: Inline During Read Tool (Chosen for v0.1.0 - DD-5)**
- **Description**: Augment Read tool response with context snippets immediately
- **Pros**:
  - Context available when Claude first sees the file
  - Single integration point (Read tool hook)
  - Simpler UX (no separate notifications)
  - Context automatically relevant to current file
- **Cons**:
  - User doesn't see context injection happening (transparency concern)
  - Cannot preview context before reading file
- **Decision**: **Chosen for v0.1.0** - documented as DD-5
- **Supporting Requirements**: FR-5 (context injection), FR-10 (token limit), NFR-2 (injection latency <50ms)

**Alternative 2: Separate Notification Before Edit Tool (Rejected for v0.1.0)**
- **Description**: Send explicit notification with context before user edits related file
- **Pros**:
  - More transparent (user sees what context is being provided)
  - Can target Edit operations specifically (higher precision)
- **Cons**:
  - More intrusive UX (extra notification)
  - Need to hook two tools (Read and Edit) instead of one
  - Timing issues (when exactly to notify?)
- **Decision**: **Rejected for v0.1.0** - may reconsider for v0.2.0
- **Rationale**: Prefer simpler, less intrusive approach first; gather user feedback before adding notifications

**Alternative 3: Hybrid (Both Inline and Notifications) (Deferred)**
- **Description**: Inline context during Read + explicit notification before risky edits (e.g., editing function used in 5+ files)
- **Pros**:
  - Best of both worlds
  - Escalating transparency based on impact
- **Cons**:
  - Most complex implementation
  - Risk of notification fatigue
- **Decision**: **Deferred to v0.2.0+** - gather v0.1.0 user feedback first
- **Note**: FR-21 (warn when editing high-impact functions) suggests this may be needed eventually

---

### 4.6 MCP Server Architecture

**Context**: How to structure the MCP server and backend systems

**Alternative 1: Thin MCP Server + Separate Backend from Day 1 (Rejected)**
- **Description**: Create thin MCP protocol adapter + separate backend service (HTTP API, gRPC, or local IPC)
- **Pros**:
  - Clear separation of concerns
  - Backend can be used independently of Claude Code
  - Easier to scale horizontally
  - Multiple frontends possible (CLI, IDE plugins, etc.)
- **Cons**:
  - Over-engineering for v0.1.0 (no other frontends planned)
  - Additional complexity (inter-process communication, API design)
  - Slower time-to-market
  - More moving parts = more failure modes
- **Decision**: **Rejected in favor of DD-6**
- **Rationale**: YAGNI principle - build what's needed for v0.1.0, defer architecture expansion to v0.2.0 when/if needed

**Alternative 2: Thick Self-Contained MCP Server with Abstraction Layers (Chosen - DD-6)**
- **Description**: Single-process MCP server with internal layered architecture (MCP protocol layer → business logic → storage abstraction)
- **Pros**:
  - Faster v0.1.0 delivery (simpler deployment)
  - All logic in one place (easier debugging)
  - Internal layers enable future extraction if needed
  - Sufficient for MCP-only use case
- **Cons**:
  - Requires refactoring if we need separate backend later
  - Cannot reuse backend for non-MCP frontends
- **Decision**: **Chosen** - documented as DD-6
- **Migration Path**: Internal abstraction layers (Section 3.8.3) enable extracting backend in v0.2.0 if multi-frontend support needed
- **Supporting Requirements**: NFR-9 (maintainability), NFR-12 (deployment simplicity)

---

### 4.7 Context Injection Storage

**Context**: Where to store context snippets during a session

**Alternative 1: Store in MCP Server State (Chosen)**
- **Description**: Keep context snippets in MCP server's in-memory working memory cache
- **Pros**:
  - Simple access during Read tool execution
  - Automatic lifecycle management (cache expiry handles cleanup)
  - No additional storage mechanism needed
- **Cons**:
  - Lost on server restart (acceptable for v0.1.0)
- **Decision**: **Chosen** - aligns with DD-4 (in-memory v0.1.0, persistence in v0.2.0)

**Alternative 2: Separate Context Store (Rejected)**
- **Description**: Create dedicated storage for context snippets separate from cache
- **Pros**:
  - Clearer separation of concerns
  - Different expiry policies possible
- **Cons**:
  - Over-engineering for v0.1.0
  - Redundant with cache functionality
- **Decision**: **Rejected** - unnecessary complexity

---

### 4.8 Relationship Type Granularity

**Context**: How fine-grained should relationship tracking be

**Alternative 1: Coarse Granularity (imports only) (Rejected)**
- **Description**: Track only file-level imports, ignore function calls
- **Pros**:
  - Simpler parsing
  - Faster indexing
- **Cons**:
  - Misses key use cases (editing shared utility function)
  - Limited value for context injection
- **Decision**: **Rejected**
- **Rationale**: FR-1, FR-2, FR-3 explicitly require function-level tracking

**Alternative 2: Fine Granularity (imports + function calls) (Chosen)**
- **Description**: Track both module imports and function call relationships
- **Pros**:
  - Comprehensive relationship detection
  - Enables high-value context injection (editing function shows all callers)
  - Supports FR-21 (warn when editing high-impact functions)
- **Cons**:
  - More complex parsing
  - Larger relationship graph
- **Decision**: **Chosen** - documented implicitly in FR-1, FR-2, FR-3
- **Supporting Requirements**: FR-1 (import detection), FR-2 (function call detection), FR-21 (dependent file awareness)

**Alternative 3: Very Fine Granularity (variable references, attribute access) (Rejected for v0.1.0)**
- **Description**: Track every variable reference, attribute access, etc.
- **Pros**:
  - Most comprehensive tracking possible
  - Enables very precise context injection
- **Cons**:
  - Extremely complex parsing
  - Massive relationship graph (performance issues)
  - Diminishing returns (most value in imports + function calls)
  - Edge cases become unmanageable (EC-6: dynamic dispatch everywhere)
- **Decision**: **Rejected** - out of scope for v0.1.0
- **Note**: May reconsider limited form (e.g., class attribute tracking) in v0.2.0 based on user feedback

---

## 5. Open Questions & TODOs

This section tracks remaining uncertainties and action items that need resolution before or during implementation. Items are organized by category with priority levels and resolution owners.

### 5.1 Technical Uncertainties

**Q-1: File Watcher Library Choice**
- **Question**: Which file watcher library should we use for cross-platform support?
- **Options**:
  - `watchdog`: Pure Python, cross-platform, well-maintained
  - `fswatch`: C-based, very fast, requires external binary
  - OS-native: `inotify` (Linux), `FSEvents` (macOS), `ReadDirectoryChangesW` (Windows)
- **Constraints**: Must support macOS, Linux, Windows per NFR-13 (cross-platform)
- **Impact**: Affects Task 3.1 (file watcher core implementation)
- **Priority**: High - needed for Phase 3
- **Resolution Owner**: Implementation team
- **Decision Criteria**:
  - Cross-platform support (all 3 OS)
  - Installation simplicity (minimize external dependencies)
  - Performance meets NFR-1 (<200ms incremental updates)
  - Maintenance status (active community)
- **Recommendation**: Start with `watchdog` (pure Python, good balance), benchmark if performance issues arise
- **References**: Task 3.1, DD-2, NFR-1, NFR-13

**Q-2: Token Counting Implementation**
- **Question**: How to accurately count tokens for context injection limit (FR-10: <500 tokens)?
- **Options**:
  - `tiktoken`: Official OpenAI library, accurate for Claude tokenizer
  - Character-based estimate: `chars / 4` heuristic
  - Word-based estimate: `words * 1.3` heuristic
  - No counting: Use character limits instead
- **Constraints**: Must work offline (NFR-5), must be fast (<10ms per injection per NFR-2)
- **Impact**: Affects Task 4.3 (context injection logic)
- **Priority**: Medium - needed for Phase 4, but estimates may suffice for v0.1.0
- **Resolution Owner**: Implementation team
- **Decision Criteria**:
  - Accuracy vs speed trade-off
  - Offline availability
  - Dependency weight
- **Recommendation**: Use character estimate for v0.1.0 (~2000 chars ≈ 500 tokens), add accurate counting in v0.1.1 if needed
- **References**: Task 4.3, FR-10, NFR-2, NFR-5

**Q-3: MCP Protocol Version and Compatibility**
- **Question**: Which MCP protocol version should we target, and what's the compatibility story?
- **Options**:
  - Target latest stable MCP version only
  - Support multiple MCP versions with feature detection
  - Pin to specific version, document compatibility
- **Constraints**: Must work with current Claude Code release
- **Impact**: Affects Task 1.2 (MCP server skeleton)
- **Priority**: Critical - needed for Phase 1
- **Resolution Owner**: Architect + Claude Code integration team
- **Decision Criteria**:
  - Current Claude Code MCP version
  - Stability of MCP protocol specification
  - Backward compatibility requirements
- **Action Required**: Verify Claude Code's MCP version before starting Task 1.2
- **References**: Task 1.2, NFR-12 (deployment simplicity)

**Q-4: Performance Benchmarking Infrastructure**
- **Question**: What infrastructure is needed to validate performance targets (NFR-1 through NFR-4)?
- **Options**:
  - Manual timing in test cases
  - pytest-benchmark plugin
  - Custom profiling harness
  - Continuous performance monitoring (CI/CD integration)
- **Constraints**: Must measure all NFR targets accurately
- **Impact**: Affects Task 7.4 (performance regression suite)
- **Priority**: Medium - needed for Phase 7, but can defer setup
- **Resolution Owner**: QA team
- **Decision Criteria**:
  - Measurement accuracy
  - Integration with existing test infrastructure
  - CI/CD compatibility
- **Recommendation**: Use `pytest-benchmark` for consistency with pytest-based testing (DD-3)
- **References**: Task 7.4, NFR-1 through NFR-4, T-7.1 through T-8.4

**Q-5: AST Parsing Error Recovery Strategy**
- **Question**: How should we handle files with syntax errors that prevent AST parsing?
- **Options**:
  - Skip file completely, log error (fail-safe approach)
  - Attempt partial parsing using error-tolerant parser
  - Retry with different Python versions (2.x vs 3.x syntax)
- **Constraints**: Must not crash analysis (FR-42 fail-safe principle)
- **Impact**: Affects Task 2.1 (Python import detector), EC-18 (parsing failure handling)
- **Priority**: Medium - needed for Phase 2
- **Resolution Owner**: Implementation team
- **Decision**: Use fail-safe approach (skip file, log error) per Section 3.11.1
- **Rationale**: Aligns with FR-42 (no incorrect context > no context), simple and safe
- **References**: Task 2.1, EC-18, FR-42, Section 3.11.1

---

### 5.2 Design Clarifications Needed

**Q-6: Injection Log JSONL Schema**
- **Question**: What is the exact JSONL schema for context injection logs (FR-26, FR-27)?
- **Current State**: Section 3.10.2 defines fields, but not formal JSON schema
- **Impact**: Affects Task 6.2 (context injection logging)
- **Priority**: Medium - needed for Phase 6
- **Resolution Owner**: Architect
- **Action Required**: Define formal JSON schema with:
  - Required vs optional fields
  - Field types and validation rules
  - Example log entries
  - Version field for schema evolution
- **References**: Task 6.2, FR-26, FR-27, Section 3.10.2

**Q-7: Session Metrics JSONL Schema**
- **Question**: What is the exact JSONL schema for session metrics (FR-43, FR-44)?
- **Current State**: Section 3.10.3 lists metrics, but not formal schema
- **Impact**: Affects Task 6.3 (session metrics export)
- **Priority**: Medium - needed for Phase 6
- **Resolution Owner**: Architect
- **Action Required**: Define formal JSON schema with:
  - Metrics structure (nested objects vs flat keys)
  - Numeric precision (floats vs ints for percentages)
  - Anonymization approach for file paths
  - Schema version field
- **References**: Task 6.3, FR-43, FR-44, FR-45, FR-47, Section 3.10.3

**Q-8: Graph Export JSON Schema**
- **Question**: What is the exact JSON schema for exported relationship graph (FR-23, FR-25)?
- **Current State**: Section 3.10.1 shows example structure
- **Impact**: Affects Task 6.1 (graph export API)
- **Priority**: Medium - needed for Phase 6
- **Resolution Owner**: Architect
- **Action Required**: Formalize schema definition with:
  - Versioning strategy (breaking changes in v0.2.0?)
  - Array vs map structure for relationships
  - Timestamp formats (ISO 8601?)
  - External tool validation (can jq/Python parse it easily?)
- **References**: Task 6.1, FR-23, FR-25, T-4.6, T-4.7, Section 3.10.1

**Q-9: Configuration File Format and Schema**
- **Question**: What is the exact YAML schema for `.cross_file_context_links.yml` (FR-49)?
- **Current State**: Section 3.10.4 shows example config
- **Impact**: Affects Task 4.6 (configuration file parsing)
- **Priority**: Low - needed for Phase 4, but can use defaults initially
- **Resolution Owner**: Implementation team
- **Action Required**: Define schema with:
  - Parameter names and types
  - Default values for all parameters
  - Validation rules (e.g., cache_expiry_minutes > 0)
  - Config file discovery order (project root → home dir → system)
  - Environment variable overrides
- **References**: Task 4.6, FR-49, FR-14, FR-16, Section 3.10.4

---

### 5.3 Implementation Planning TODOs

**TODO-1: Development Environment Setup**
- **Action**: Set up development environment with all required tools
- **Details**:
  - Python 3.8+ (minimum version per NFR-13)
  - Install AST parsing dependencies (`ast` module is built-in)
  - Install file watcher library (pending Q-1 resolution)
  - Install MCP SDK/libraries (pending Q-3 resolution)
  - Install testing frameworks: pytest, pytest-benchmark
  - Set up linting: ruff or pylint
  - Set up type checking: mypy
- **Priority**: Critical - needed before Phase 1
- **Owner**: Developer onboarding
- **References**: Task 1.1, NFR-13

**TODO-2: Test Fixture Repository Creation**
- **Action**: Create representative test codebase for validation (prd_testing.md Section 8.1)
- **Details**:
  - 50-100 Python files with documented dependencies
  - Include all edge cases: circular imports (EC-1), wildcards (EC-4), dynamic imports (EC-2)
  - Include test files using pytest patterns
  - Document expected relationships in fixture metadata
  - Version control test fixtures for regression testing
- **Priority**: High - needed for Phase 2 (relationship detection validation)
- **Owner**: QA team
- **References**: Task 2.9 (comprehensive integration test), T-1.1 through T-1.8, prd_testing.md Section 8.1

**TODO-3: Relationship Graph Validation Tooling**
- **Action**: Build external validator for exported relationship graphs (supports T-4.7)
- **Details**:
  - Script to parse exported JSON graph (FR-23, FR-25)
  - Validate graph structure (no orphaned nodes, valid relationship types)
  - Compare against ground truth from test fixtures
  - Detect graph corruption (EC-19)
- **Priority**: Medium - needed for Phase 4 validation
- **Owner**: QA team
- **References**: Task 6.1, FR-23, FR-25, T-4.7, EC-19

**TODO-4: Metrics Analysis Tool Implementation**
- **Action**: Build tool to analyze session metrics and suggest optimal configuration (FR-48)
- **Details**:
  - Parse session metrics JSONL files
  - Compute summary statistics (percentiles, distributions)
  - Identify outliers and anomalies
  - Suggest configuration changes (cache expiry, token limits, etc.)
  - Generate reports for performance tuning
- **Priority**: Low - needed for Phase 6, helpful for UAT analysis
- **Owner**: Implementation team
- **References**: Task 6.5 (metrics analysis tool), FR-48, T-10.6, T-10.7

**TODO-5: CI/CD Integration**
- **Action**: Set up continuous integration for automated testing
- **Details**:
  - Run unit tests on every commit (Task 7.1)
  - Run integration tests on PRs (Task 7.2)
  - Run performance regression suite on main branch (Task 7.4)
  - Generate coverage reports
  - Block merges on test failures
- **Priority**: Medium - should be set up early in Phase 1
- **Owner**: DevOps team
- **References**: Task 7.5 (continuous testing), NFR-10 (testability)

---

### 5.4 Documentation TODOs

**TODO-6: API Documentation**
- **Action**: Document all public interfaces for developers extending the system
- **Details**:
  - MCP protocol endpoints (Read tool hook)
  - Query API (Section 3.10.1: get_dependents, get_dependencies, etc.)
  - Detector plugin interface (for future language support)
  - Storage abstraction interface (for future backends)
  - Configuration parameters (Section 3.10.4)
- **Format**: Docstrings + generated API docs (Sphinx or similar)
- **Priority**: Medium - needed before beta testing (Task 8.3)
- **Owner**: Documentation team
- **References**: Task 8.1 (UAT documentation), Section 3.8.3 (abstraction layers)

**TODO-7: User Configuration Guide**
- **Action**: Write guide for configuring the cross-file context links feature
- **Details**:
  - How to enable/disable feature
  - Configuration file format and location (`.cross_file_context_links.yml`)
  - All configurable parameters with examples (FR-49)
  - Warning suppression configuration (FR-39, FR-40)
  - Performance tuning guide
  - Troubleshooting common issues
- **Format**: Markdown guide in docs/
- **Priority**: High - needed before alpha testing (Task 8.2)
- **Owner**: Documentation team
- **References**: Task 8.1, FR-49, FR-39, FR-40, Section 3.10.4

**TODO-8: Troubleshooting Guide**
- **Action**: Document common issues and solutions
- **Details**:
  - Cache not working (check file permissions, memory limits)
  - Context not appearing (check relationship detection, enable debug logs)
  - Performance issues (check file count, disable for large files)
  - Warning message meanings and resolutions
  - How to report bugs
- **Format**: Markdown FAQ/troubleshooting doc
- **Priority**: Medium - needed before beta testing (Task 8.3)
- **Owner**: Documentation team + Support team
- **References**: Task 8.1, Section 3.11 (error handling)

**TODO-9: Architecture Diagrams**
- **Action**: Create visual diagrams for system architecture
- **Details**:
  - Component diagram (Section 3.1: MCP server, detectors, cache, graph)
  - Sequence diagram for context injection flow (Section 3.4.7)
  - Data flow diagram (file read → relationship lookup → context injection)
  - Deployment diagram (MCP server ↔ Claude Code integration)
  - State diagram for cache lifecycle (Section 3.4.6)
- **Format**: Mermaid or PlantUML embedded in markdown
- **Priority**: Low - helpful but not critical for v0.1.0
- **Owner**: Documentation team
- **References**: Section 3.1, Section 3.4

---

### 5.5 Pre-Implementation Validation TODOs

**TODO-10: MCP Server Integration Verification**
- **Action**: Validate MCP server can integrate with Claude Code as expected
- **Details**:
  - Confirm MCP protocol version compatibility (Q-3)
  - Test basic MCP server registration with Claude Code
  - Verify Read tool hook mechanism works
  - Test error propagation from MCP server to Claude Code UI
  - Validate context injection appears correctly in Claude's context
- **Priority**: Critical - must validate before Phase 1 starts
- **Owner**: Integration team
- **References**: Task 1.2 (MCP server skeleton), Q-3, T-9.1 through T-9.5

**TODO-11: Metrics Collection Overhead Assessment**
- **Action**: Validate that metrics collection does not impact performance targets
- **Details**:
  - Measure overhead of JSONL logging (Section 3.10.2)
  - Measure overhead of metrics aggregation (Section 3.10.3)
  - Ensure logging does not block main operations
  - Verify log file size stays manageable (T-5.7: <10MB per 4-hour session)
- **Priority**: Medium - needed before Phase 6
- **Owner**: Performance team
- **References**: Task 6.4 (observability), T-5.7, NFR-2 (latency <50ms)

**TODO-12: Real-World Codebase Testing**
- **Action**: Identify 3-5 real-world Python codebases for validation testing
- **Details**:
  - Range of sizes: small (100 files), medium (1,000 files), large (10,000 files)
  - Different domains: web app, data science, CLI tool, library
  - Diverse patterns: Django project, Flask project, pure libraries
  - Use for stress testing (T-7.2, T-7.4) and edge case discovery
- **Priority**: Medium - needed for Phase 7 (functional testing)
- **Owner**: QA team
- **References**: T-7.2, T-7.4, Task 7.3, prd_testing.md Section 8.5

**TODO-13: Warning Message User Feedback**
- **Action**: Validate warning messages are helpful and actionable (FR-33 through FR-39)
- **Details**:
  - Review all 6 warning types (Section 3.9.1) for clarity
  - Ensure warnings explain WHY pattern is untrackable
  - Verify warnings suggest alternatives where applicable
  - Test with developers unfamiliar with system
  - Iterate based on confusion/feedback
- **Priority**: Medium - needed before beta testing (Task 8.3)
- **Owner**: UX team + beta testers
- **References**: Task 5.5 (warning templates), Section 3.9.1, FR-33 through FR-39

---

### 5.6 Design Questions Requiring Decisions

**Q-10: Should v0.1.0 Support Configuration File at All?**
- **Context**: Section 3.10.4 describes extensive configuration, but adds complexity
- **Trade-off**:
  - **With config**: Users can tune parameters (FR-49), but more implementation work
  - **Without config**: Use hardcoded defaults, faster v0.1.0, add config in v0.1.1 based on feedback
- **Impact**: Affects Task 4.6 (config parsing)
- **Recommendation**: **Include basic config** (enable/disable feature, warning suppression only), defer advanced tuning to v0.1.1
- **Decision Needed By**: Phase 4 planning
- **References**: Task 4.6, FR-49, Section 3.10.4

**Q-11: Should Warning Suppression Be File-Level or Pattern-Level?**
- **Context**: Section 3.9.3 describes 4 suppression granularities, increasing complexity
- **Trade-off**:
  - **File/directory level only**: Simpler implementation, covers 80% of use cases
  - **All 4 levels**: More flexible, but complex config parsing and validation
- **Impact**: Affects Task 5.4 (suppression configuration)
- **Recommendation**: **Start with file/directory level** (glob patterns), add pattern-level if users request
- **Decision Needed By**: Phase 5 planning
- **References**: Task 5.4, FR-39, FR-40, Section 3.9.3

**Q-12: Should Relationship Graph Be Queryable During Runtime?**
- **Context**: Section 3.10.1 describes query API with 6 methods
- **Trade-off**:
  - **Yes (as designed)**: Enables external tools, debugging, future features
  - **No (defer)**: Simpler v0.1.0, add API in v0.2.0 if needed
- **Impact**: Affects Task 6.1 (graph export and query API)
- **Current Design**: FR-28, FR-29 require query capability for metrics and debugging
- **Recommendation**: **Implement API** - needed for FR-29 (retrieve injection events) and debugging
- **Decision**: Keep as designed
- **References**: Task 6.1, FR-28, FR-29, Section 3.10.1

---

### 5.7 Known Limitations to Document

**LIMITATION-1: Dynamic Python Patterns Cannot Be Tracked**
- **Description**: getattr(), monkey patching, exec/eval, complex decorators cannot be statically analyzed
- **Impact**: Some relationships will be missed (EC-6, EC-7, EC-9)
- **Mitigation**: Emit warnings to inform users (FR-33 through FR-37), fail-safe principle (FR-42)
- **User Communication**: Must be clearly documented in README and user guide
- **References**: EC-6, EC-7, EC-9, EC-8, FR-42, Section 3.9.1

**LIMITATION-2: No Cross-Language Relationship Tracking in v0.1.0**
- **Description**: Python-only, cannot track Python calling JavaScript or vice versa
- **Impact**: Mixed-language projects have incomplete relationship graphs
- **Mitigation**: Clear documentation that v0.1.0 supports Python only
- **Roadmap**: v0.3.0 (TypeScript), v0.4.0 (Go) will improve but not fully solve (inter-language calls still hard)
- **User Communication**: Document in README with roadmap
- **References**: NFR-3 (multi-language expansion), Section 1.3.3

**LIMITATION-3: No Persistence Across Sessions in v0.1.0**
- **Description**: Relationship graph and cache lost on MCP server restart
- **Impact**: Full re-indexing required each session (mitigated by fast incremental updates)
- **Mitigation**: Fast enough for v0.1.0 (T-7.1: <10s for 100 files), persistence in v0.2.0
- **User Communication**: Document in README, note v0.2.0 improvement
- **References**: DD-4, T-7.1, Section 3.8.3 (storage abstraction for future persistence)

**LIMITATION-4: Large Files Excluded from Indexing**
- **Description**: Files >10,000 lines skipped to prevent performance issues (EC-17)
- **Impact**: Very large generated files or data files won't have relationships tracked
- **Mitigation**: Log warning when skipped, most source files <10k lines
- **User Communication**: Document limit and rationale in user guide
- **References**: EC-17, Section 3.11.1 (massive file handling)

---

### 5.8 Risk Mitigation TODOs

**RISK-1: Cache Hit Rate Lower Than Expected**
- **Risk**: If cache hit rate <50%, context may be stale, negating benefits
- **Mitigation**:
  - Collect metrics during alpha testing (Task 8.2, T-10.2)
  - Tune cache expiry based on real usage (FR-14 configurable)
  - If still low, consider different expiry strategies (adaptive expiry in v0.1.1)
- **Probability**: Medium
- **Impact**: High (affects core value proposition)
- **Owner**: Performance team
- **References**: Task 8.2, FR-14, T-10.2, Section 3.4.6

**RISK-2: Context Injection Exceeds Token Limits Frequently**
- **Risk**: If >20% of injections hit 500-token limit (FR-10), context may be truncated too aggressively
- **Mitigation**:
  - Collect distribution metrics during alpha testing (T-10.2, FR-46)
  - Adjust limit based on p95 actual usage (FR-49 configurable)
  - Improve context selection algorithm if needed (Section 3.4.7)
- **Probability**: Low
- **Impact**: Medium (affects context quality)
- **Owner**: Algorithm team
- **References**: Task 4.3, FR-10, FR-46, FR-49, Section 3.4.7

**RISK-3: File Watcher Performance Issues on Large Codebases**
- **Risk**: File watcher may struggle with projects >10,000 files
- **Mitigation**:
  - Test with large codebases during functional testing (TODO-12)
  - Implement filtering (ignore node_modules, .git, etc.) early
  - Add configurable file count limit with warning
  - Use efficient data structures (Section 3.3.2: adjacency list)
- **Probability**: Low
- **Impact**: High (affects usability for large projects)
- **Owner**: Performance team
- **References**: TODO-12, T-7.4, NFR-4 (memory <500MB for 10k files)

---

## 6. Gaps Discovered During Implementation

**Note**: This section is intentionally empty at TDD completion. It will be populated during implementation (Phases 1-8) to track discrepancies between design and reality.

### Purpose

This living document section tracks:
- Discrepancies between design and implementation reality
- Unexpected technical challenges not covered by EC-1 through EC-20
- Performance bottlenecks discovered during development
- User feedback from UAT requiring design changes (alpha, beta, pilot)
- Missing requirements or edge cases discovered in the field
- Assumptions that proved incorrect

### Update Frequency

- Review and update weekly during Phases 1-7
- Review after each UAT phase (Tasks 8.2, 8.3, 8.4)
- Include in retrospectives and design reviews

### Gap Entry Format

Each gap should be documented using this template:

```
**G-#: [Short Title]**
- **Discovery Date**: YYYY-MM-DD
- **Discovered During**: [Phase/Task/Test ID]
- **Description**: [What was discovered - be specific]
- **Root Cause**: [Why the gap exists - design assumption, requirement miss, etc.]
- **Impact**: [How it affects the design - which sections/requirements affected]
- **Affected Components**: [FR-#, NFR-#, Task #, Section references]
- **Resolution**: [How it was/will be addressed - code change, design update, workaround]
- **Status**: Open / In Progress / Resolved / Deferred
- **Resolution Date**: YYYY-MM-DD (when resolved)
```

### Example Gap (Illustrative Only)

**Example format** (not an actual gap, just to illustrate structure):

```
**G-1: AST Parsing Slower Than Expected for Large Files**
- **Discovery Date**: 2025-12-15
- **Discovered During**: Phase 2, Task 2.1 (Python import detector), T-7.1 performance testing
- **Description**: AST parsing takes 2.5 seconds for 5,000-line file, exceeding NFR-1 target (<200ms incremental)
- **Root Cause**: Assumed Python `ast.parse()` would be faster; didn't account for complex nested structures
- **Impact**: NFR-1 (incremental updates <200ms) at risk for large files
- **Affected Components**: NFR-1, Task 2.1, Section 3.4.2 (incremental updates)
- **Resolution**: Implemented incremental parsing (only parse changed functions, not whole file) + caching parsed AST nodes
- **Status**: Resolved
- **Resolution Date**: 2025-12-18
```

### Gaps Discovered During TDD Creation

These gaps were identified during TDD creation itself, before implementation began:

**G-1: Over-Specification of Data Models (Section 3.3)**
- **Discovery Date**: 2025-11-25
- **Discovered During**: TDD Section 3.3 initial draft and user review
- **Description**: Initial Section 3.3 included implementation methods (`__str__()`, `to_dict()`, `from_dict()`, detailed algorithms) alongside data model definitions
- **Root Cause**: Blurred line between "what data to store" (TDD scope) vs "how to implement methods" (code scope)
- **Impact**: Over-constrains implementation, similar to anti-pattern of "detailed pseudocode in design docs"
- **Affected Components**: Section 3.3 (Data Models)
- **User Feedback**: "There is significant implementation detail which is similar to the 'Don't' of over-specifying algorithms with detailed pseudocode. For example, in 3.3.1, the TDD doesn't need to show the __str__() method which is purely an implementation detail and not part of the semantics of the data model."
- **Resolution**: Removed all implementation methods from Section 3.3, keeping only:
  - Field names and types
  - Semantic meaning of each field
  - Structural relationships (e.g., "adjacency list format")
  - Data invariants and constraints
- **Lesson Learned**: TDD should specify WHAT data to store (semantic contract), not HOW to implement methods (implementation detail)
- **Status**: Resolved
- **Resolution Date**: 2025-11-25

**G-2: Unnecessary Duplication of Large External Documentation**
- **Discovery Date**: 2025-11-25
- **Discovered During**: TDD Section 3.2 and Section 3.13 review
- **Description**: Initial drafts of Section 3.2 (Key Design Decisions) and Section 3.13 (Testing Strategy) duplicated content from `design_decisions.md` (~580 lines) and `prd_testing.md` (~200 lines) respectively
- **Root Cause**: Unclear boundary between TDD content vs referencing external detailed docs
- **Impact**: Document bloat (~800 unnecessary lines), maintenance burden (two places to update), harder for readers to navigate
- **Affected Components**: Section 3.2, Section 3.13
- **User Feedback**: "Did you simply copy/summarize design_decisions.md into section 3.2?... I would like to avoid unnecessary duplication of a very large file (similar to design_decisions.md)."
- **Resolution**:
  - Section 3.2: Replaced verbose duplication with concise summary table (Problem | Solution | Key Impact) + reference to design_decisions.md for full analysis
  - Section 3.13: Wrote TDD-specific testing philosophy (how architecture enables testing) while referencing prd_testing.md for comprehensive test specs
- **Lesson Learned**: TDD should provide TDD-specific content and concise summaries, not duplicate detailed analysis from dedicated reference documents. Use the "summary + pointer" pattern for large external docs.
- **Status**: Resolved
- **Resolution Date**: 2025-11-25

---

### Active Gaps

_(This subsection will be populated during implementation Phases 1-8)_

**Status as of TDD Completion (2025-11-25)**: No implementation gaps discovered yet - implementation has not started.

---

### Resolved Gaps Archive

_(Implementation gaps will be moved here once resolved to keep Active Gaps section clean)_

**Note**: G-1 and G-2 above are design-phase gaps and will remain in "Gaps Discovered During TDD Creation" section.

---

## Appendices

### A. References
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Python AST Documentation](https://docs.python.org/3/library/ast.html)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [pytest Documentation](https://docs.pytest.org/)

### B. Glossary

**Acronyms:**
- **AST**: Abstract Syntax Tree - parsed representation of source code structure
- **MCP**: Model Context Protocol - protocol for Claude Code tool integration
- **LRU**: Least Recently Used (cache eviction strategy)
- **UAT**: User Acceptance Testing
- **JSONL**: JSON Lines - newline-delimited JSON format for logs
- **CI/CD**: Continuous Integration / Continuous Deployment

**Document Identifiers:**
- **FR-#**: Functional Requirement (defined in prd.md Section 4.1)
- **NFR-#**: Non-Functional Requirement (defined in prd.md Section 4.2)
- **EC-#**: Edge Case (defined in prd_edge_cases.md Section 6)
- **DD-#**: Design Decision (defined in design_decisions.md)
- **T-#.#**: Test Case (defined in prd_testing.md Section 8)
- **Q-#**: Open Question (defined in this TDD Section 5)
- **TODO-#**: Action Item (defined in this TDD Section 5)
- **G-#**: Implementation Gap (defined in this TDD Section 6)
- **LIMITATION-#**: Known System Limitation (defined in this TDD Section 5.7)
- **RISK-#**: Project Risk (defined in this TDD Section 5.8)
- **Task #.#**: Development Phase Task (defined in this TDD Section 3.14)

**System Components:**
- **Relationship Graph**: In-memory data structure tracking cross-file dependencies (Section 3.3.2, Section 3.5)
- **Working Memory Cache**: LRU cache storing recently-read file snippets (Section 3.3.3, Section 3.4.6)
- **Detector**: Language-specific plugin for AST parsing and relationship extraction (Section 3.4.1)
- **Context Injection**: Process of augmenting Read tool with cross-file context (Section 3.4.7)

**Domain Terms:**
- **Cross-File Context**: Information about how a file relates to other files in the codebase
- **Context Links**: Relationships between files (imports, function calls, etc.)
- **Incremental Update**: Re-analyzing only changed files, not entire codebase
- **Fail-Safe Principle**: "No incorrect context is better than wrong context" (FR-42)

### C. Change Log

**2025-11-25: TDD Completion**
- Completed Section 3.3 Data Models (trimmed implementation details per user feedback)
- Replaced Section 3.2 Key Design Decisions with concise summary table
- Completed Section 3.13 Testing Strategy with architecture-specific philosophy
- Completed Sections 3.9-3.12 (Warning System, Metrics/Logging, Error Handling, Security)
- Completed Section 3.14 Development Plan with 8 phases and 50+ traceable tasks
- Expanded Section 4 Alternatives Considered with detailed analysis (8 alternatives)
- Completed Section 5 Open Questions & TODOs (13 questions, 13 TODOs, 4 limitations, 3 risks)
- Structured Section 6 Gaps with template and examples for implementation tracking
- Updated Glossary with all document identifiers and system components

**2025-11-24: Initial Draft**
- Created document structure with all major sections
- Completed Sections 1-2 (Constraints, Requirements)
- Completed Section 3.1 Architecture Overview
- Established cross-referencing system with prd.md, design_decisions.md, prd_edge_cases.md, prd_testing.md
