# Cross-File Context Links - Product Requirements Document (PRD)

**Product Name:** Cross-File Context Links for Claude Code
**Version:** 0.1.0 (MVP)
**Status:** Draft
**Last Updated:** 2025-11-22

---

## Quick Reference

This PRD uses identifiers that may reference supporting documents:

- **FR-#**: Functional Requirements → See Section 4.1 in this document
- **NFR-#**: Non-Functional Requirements → See Section 4.2 in this document
- **EC-#**: Edge Cases → See [`prd_edge_cases.md`](./prd_edge_cases.md)
- **T-#.#**: Test Cases → See [`prd_testing.md`](./prd_testing.md)
- **Q-#**: Open Questions → See [`prd_open_questions.md`](./prd_open_questions.md)

---

## 1. Purpose

### 1.1 Problem Description

Developers using AI coding assistants like Claude Code experience significant inefficiency due to **repeated file re-reads during cross-file workflows**. When working on interconnected codebases, AI agents frequently need to revisit previously-accessed files to recall:

- How a function is defined in File A when editing File B that calls it
- What parameters a shared utility function accepts
- Which files import or use the code being modified
- The context of related documentation when implementing features

**Data from real sessions shows:**
- Files are re-read **5-10 times per session** on average
- **60-80% of re-reads** occur after working on related files (ping-pong pattern)
- Re-read intervals range from **15 seconds to 4 hours**, indicating both immediate verification and context loss
- The most frequently re-read files are those with **cross-file dependencies** (imports, function calls, inheritance)

**Example scenario:**
A developer asks Claude Code to fix a bug in `sheets.py`. The agent:
1. Reads `sheets.py` (initial understanding)
2. Reads `retry.py` because `sheets.py` imports `retry_with_backoff`
3. Edits `sheets.py`
4. Works on `bot.py` for 5 minutes (40 tool calls)
5. **Re-reads `retry.py`** - forgot how `retry_with_backoff` works (WASTE)
6. Edits `bot.py` to use retry logic
7. **Re-reads `sheets.py`** - forgot what was just changed (WASTE)

This wastes time, consumes context window capacity, and reduces agent effectiveness.

### 1.2 Existing Alternative Solutions

Several tools attempt to address codebase context management, but none solve the cross-file ping-pong problem:

#### Cursor's @Codebase (65% similarity)
- **What it does:** Semantic search using embeddings to find relevant code
- **Strengths:** Automatic indexing, integrated workflow, stays in sync with changes
- **Limitations:**
  - Uses semantic similarity (find "similar" code), not structural relationships (find "related" code via imports)
  - Retrieval-based - you must explicitly ask via @Codebase
  - Cloud-dependent (embeddings created on Cursor servers)
  - Won't automatically surface `retry.py` when editing `sheets.py` unless semantically similar

#### Sourcegraph Code Intelligence (75% similarity)
- **What it does:** Cross-repository navigation using compile-time dependency information
- **Strengths:** Actually understands imports/dependencies, "go to definition" across files
- **Limitations:**
  - Navigation tool, not context manager - requires manual clicks
  - Not proactive - you must navigate to see related code
  - Enterprise/cloud-focused, not designed for local IDE use
  - Doesn't cache related snippets in working memory

#### Code Context MCP Server (55% similarity)
- **What it does:** Local semantic code search plugin for Claude Code
- **Strengths:** Local-first (privacy-preserving), works with Claude Code via MCP
- **Limitations:**
  - Search tool, not automatic context awareness
  - Semantic-based, doesn't track "file A imports file B"
  - Query-based - you search, it doesn't proactively inject

**What all alternatives lack:**
- **Proactive context injection** - Automatically surface related code when switching files
- **Relationship-first approach** - Use actual imports/calls, not just semantic similarity
- **Lightweight working memory** - Cache recently-accessed file snippets for instant retrieval
- **Cross-file edit awareness** - Show which files are affected when editing shared code

### 1.3 Target Users

**Primary User Persona: Developer Using AI Coding Assistants**

Characteristics:
- Uses Claude Code or similar AI coding assistants for software development
- Works on codebases with 10-1000+ files with interconnected dependencies
- Spends 30-60% of coding time navigating between related files
- Values fast iteration and reduced context switching

**User Needs:**
- Quickly understand how changes in one file affect others
- Avoid re-reading previously-accessed files
- Maintain awareness of cross-file dependencies without manual navigation
- Reduce cognitive load when working on complex multi-file features

**Success Criteria for User:**
- Spend less time re-reading files
- Maintain context longer across multi-file edits
- Receive relevant information at the right time without asking

---

## 2. Current State

### 2.1 Current Solution (Baseline Behavior)

Currently, when using Claude Code, developers and AI agents experience the following workflow:

**Agent Behavior:**
1. User asks to "fix the retry logic in sheets.py"
2. Agent reads `sheets.py` (full file)
3. Agent discovers import: `from retry import retry_with_backoff`
4. Agent reads `retry.py` to understand the decorator
5. Agent edits `sheets.py`
6. User asks to "apply the same retry pattern in bot.py"
7. Agent reads `bot.py`
8. **Agent re-reads `retry.py`** (forgot the signature after 40 tool calls) ← INEFFICIENCY
9. Agent edits `bot.py`
10. User asks to "verify the changes in sheets.py"
11. **Agent re-reads `sheets.py`** (forgot what was changed) ← INEFFICIENCY

**Current Mitigation Strategies:**
- Users manually remind agents: "Remember that retry.py has retry_with_backoff(backoff_seconds, max_retries)"
- Users paste code snippets into prompts to avoid re-reads
- Agents re-read files whenever uncertain (safe but wasteful)

**Measured Inefficiency:**
From session analysis of Claude Code usage:
- **Average re-reads per file:** 3.2x
- **Time wasted on re-reads:** ~20-30% of total session time
- **Context window waste:** 40-60% of re-reads are redundant (recently accessed content)

### 2.2 Constraints

**Technical Constraints:**
- Must work within Claude Code's existing tool architecture
- Must respect user privacy - no cloud dependency for core functionality
- Must integrate with existing file Read/Edit/Write tools
- Must handle codebases of varying sizes (10 files to 100K+ files)
- Version 0.1.0 focuses on **Python only** (see Language Support Roadmap below for future languages)

**Performance Constraints:**
- Relationship detection must not significantly slow down file access
- Context injection must not clutter agent responses
- Working memory must fit within Claude Code's context window budget
- Indexing must be incremental (not require full codebase re-scan on every change)

**User Experience Constraints:**
- Must not require manual setup or configuration for basic use
- Must not interrupt user workflow with excessive prompts
- Must degrade gracefully when relationship detection fails
- Must allow users to disable/customize behavior

**Compatibility Constraints:**
- Must work with local codebases (no cloud requirement)
- Must integrate with existing MCP (Model Context Protocol) architecture
- Must not conflict with other Claude Code extensions
- Must support standard project structures (node_modules, venv, git repos)

### 2.3 Language Support Roadmap

**Version 0.1.0: Python Only**
- Focus on Python codebases exclusively
- Detect `import` and `from...import` statements
- Handle Python-specific patterns (type hints with `TYPE_CHECKING`, etc.)
- Rationale: Python is widely used in Claude Code workflows and has well-understood import semantics

**Version 0.2.0: Add Terraform Support**
- Detect Terraform module dependencies
- Handle `module` blocks and `source` references
- Support HCL (HashiCorp Configuration Language) parsing
- Rationale: Infrastructure-as-Code workflows benefit from cross-file context

**Version 0.3.0: Add TypeScript/JavaScript Support**
- Detect ES6 `import`, CommonJS `require()`, and dynamic `import()`
- Handle TypeScript-specific imports (type-only imports, namespaces)
- Support both `.js`, `.ts`, `.jsx`, `.tsx` files
- Rationale: Web development is a major Claude Code use case

**Version 0.4.0: Add Go Support**
- Detect Go `import` statements and package dependencies
- Note: Go prevents circular imports at compile time, simplifying detection
- Handle Go module structure (`go.mod` awareness)
- Rationale: Complete coverage of major languages in session analysis data

### 2.5 Code Style Philosophy

This solution is designed to **work with real-world Python codebases**, including those that follow the Google Python Style Guide:

- **Pragmatic approach:** Support common patterns even if discouraged by style guides
- **Configurable warnings:** Users can enable stricter checks if desired
- **CI-friendly:** Complement existing linters (pylint, flake8) without duplicating their role
- **Focus on high-value detections:** Prioritize circular imports (code smells) over wildcards (style preferences)

**Design Principle:** The tool should help users understand their codebase as it exists today, not enforce an idealized version.

**Relationship to Google Python Style Guide:**
- **Section 2.2 (Imports):** We detect wildcard imports but don't block them (matches Google's own [pylintrc](https://github.com/google/styleguide/blob/gh-pages/pylintrc))
- **Section 3.19.13 (TYPE_CHECKING):** Full support for conditional type-only imports
- **Section 3.19.14 (Circular Dependencies):** Detection and warnings for circular import code smells

---

## 3. Proposed Solution

### 3.1 Solution Overview

**Cross-File Context Links** is a context awareness system for Claude Code that:

1. **Automatically detects relationships** between files (imports, function calls, inheritance)
2. **Maintains a lightweight context graph** of recently-accessed files and their connections
3. **Proactively injects relevant context** when switching between related files
4. **Caches file snippets** in working memory for instant retrieval without re-reads

**How It Works (User Perspective):**

**Before (Current Behavior):**
```
User: "Fix the retry logic in sheets.py"
Agent: [Reads sheets.py, reads retry.py, edits sheets.py]

User: "Apply the same pattern to bot.py"
Agent: [Reads bot.py, RE-READS retry.py ← WASTE, edits bot.py]
```

**After (With Cross-File Context Links):**
```
User: "Fix the retry logic in sheets.py"
Agent: [Reads sheets.py, reads retry.py, edits sheets.py]
  → System: "Cached retry.py:120-140 (retry_with_backoff function)"

User: "Apply the same pattern to bot.py"
Agent: [Reads bot.py, RECALLS cached retry_with_backoff from memory ← EFFICIENT]
Agent: "I'll apply retry_with_backoff (from retry.py:120) to bot.py..."
```

**Key User Benefits:**
- **50-70% reduction in file re-reads** (measured from session analysis)
- **Faster iteration** - Agent spends less time re-reading, more time coding
- **Better context retention** - System remembers relationships even after working elsewhere
- **Reduced context window pressure** - Cached snippets instead of full file re-reads

### 3.2 Core Features

#### Feature 1: Automatic Relationship Detection

**What:** System parses files during first read to extract structural relationships

**How it helps users:**
- Zero configuration required - works automatically
- Detects imports, function calls, class inheritance, module dependencies
- Builds lightweight "context graph" of file-to-file connections

**User-facing behavior:**
```
Agent reads sheets.py → System detects: "sheets.py imports retry_with_backoff from retry.py:120"
  → Creates link: sheets.py:45 ↔ retry.py:120
```

#### Feature 2: Proactive Context Injection

**What:** When agent edits a file, system surfaces related code from connected files

**How it helps users:**
- Agent automatically recalls relevant context without re-reading
- Reduces "I forgot what that function does" moments
- Keeps agent focused on current task

**User-facing behavior:**
```
Agent edits sheets.py line 45 (which calls retry_with_backoff)
  → System injects: "Context: retry_with_backoff from retry.py:120
                     Signature: @decorator(backoff_seconds=5, max_retries=3)"
```

#### Feature 3: Lightweight Working Memory

**What:** System caches recently-accessed file snippets (not full files) with smart expiry

**How it helps users:**
- Instant retrieval of recent file contents without re-read
- Reduces context window consumption (snippets vs full files)
- Automatically expires stale content

**User-facing behavior:**
```
Agent last read retry.py 3 minutes ago
Agent needs to reference retry_with_backoff
  → System provides cached lines 120-140 instantly (no re-read needed)
```

#### Feature 4: Cross-File Edit Awareness

**What:** When editing shared code, system shows which other files depend on it

**How it helps users:**
- Prevents breaking changes to shared utilities
- Increases awareness of change impact
- Helps plan refactoring scope

**User-facing behavior:**
```
Agent edits retry_with_backoff in retry.py
  → System warns: "⚠️  This function is used in: sheets.py:45, bot.py:200, setup.py:67"
```

#### Feature 5: Context Injection Logging and User Visibility

**What:** Provides transparency into context injection through logging, with flexible visualization options

**Architecture: Separation of Concerns**

The system separates context injection (data) from visualization (presentation):

**1. Data Layer: Context Injection Logging (FR-26 through FR-29)**

All context injection events are logged to a structured format, similar to Claude Code's session logs:

```json
{
  "timestamp": "2025-11-23T10:15:23.456Z",
  "event_type": "context_injection",
  "trigger": "agent_read_file",
  "trigger_file": "bot.py",
  "injected_context": [
    {
      "source_file": "retry.py",
      "lines": "120-140",
      "snippet": "def retry_with_backoff(backoff_seconds=5, max_retries=3):\n    ...",
      "relationship_type": "import",
      "cache_age_seconds": 180,
      "relevance_score": 0.95
    }
  ],
  "token_count": 145
}
```

**Benefits of logging:**
- Enables post-session analysis (like `session_analyzer.py` for context patterns)
- Supports multiple visualization approaches simultaneously
- Provides debugging and metrics data
- Decouples UI decisions from core functionality
- Allows users to build custom analysis tools

**2. Presentation Layer: Multiple Visualization Options (See Q-1)**

Multiple UI approaches can read from the same logs (not mutually exclusive):

- **Option A: Inline mentions** - Agent references context in responses
- **Option B: UI panel** - Dedicated sidebar showing active context
- **Option C: Tooltips** - Hover to see context sources
- **Option D: External tools** - Custom analyzers built by users/community
- **Option E: Hybrid** - Combine multiple approaches (e.g., A + B)

**For the Agent (Internal - Always Active):**
- Context is automatically injected into agent's working memory
- Agent uses context to make informed decisions without re-reading files
- All injections logged per FR-26
- Example: Agent knows `retry_with_backoff` signature from cache, uses it correctly

**For the User (External - Flexible):**
- **Minimum:** Logs are available for analysis (FR-26 through FR-29)
- **Optional:** Visual indicators in UI (NFR-10)
- **User choice:** Can build custom visualization tools

**Key Distinctions:**
- **Context injection to agent** = MUST happen (core functionality, FR-8)
- **Context injection logging** = MUST happen (transparency, FR-26)
- **Context visibility in UI** = SHOULD happen (usability, NFR-10, see Q-1)

Even without real-time UI visualization, users benefit from:
- Faster agent responses (no re-reads)
- More accurate code (agent remembers details)
- Fewer mistakes (agent aware of dependencies)
- Post-session analysis capabilities

**See Open Questions Q-1 and Q-5** for UI and logging format decisions.

### 3.3 User Workflows

#### Workflow 1: Multi-File Bug Fix (Primary Use Case)

**User Story:**
"As a developer, I want to fix a bug that spans multiple files without the AI agent wasting time re-reading files, so that I can iterate faster."

**User Flow:**
1. User asks: "Fix the timeout issue in the data fetcher"
2. Agent reads `fetcher.py` and identifies it uses `retry_with_backoff`
3. Agent reads `retry.py` to understand retry logic
4. **System caches** `retry.py` function signature and adds link
5. Agent proposes fix: "Increase backoff_seconds in fetcher.py"
6. User asks: "Apply the same timeout fix to uploader.py"
7. Agent reads `uploader.py` and sees `retry_with_backoff` usage
8. **System recalls cached retry.py context** (no re-read needed)
9. Agent applies fix using cached knowledge
10. User asks: "Make sure all callers use 30-second timeout"
11. **System surfaces**: "retry_with_backoff is used in: fetcher.py, uploader.py, parser.py"
12. Agent updates all three files efficiently

**Success Metric:** Agent completes task in 8 tool calls instead of 15 (46% reduction)

#### Workflow 2: Documentation-Driven Feature Implementation

**User Story:**
"As a developer, I want to implement a feature according to specifications without repeatedly jumping back to docs, so I can stay focused on coding."

**User Flow:**
1. User asks: "Implement the new validation feature per TDD section 4.3"
2. Agent reads `tdd.md` section 4.3
3. **System caches** TDD requirements and detects they reference `validator.py`
4. Agent reads `validator.py` to understand existing validation
5. Agent starts implementing in `user_input.py`
6. User asks: "Make sure it follows the TDD's error handling pattern"
7. **System recalls cached TDD section** (no re-read of long doc)
8. Agent applies pattern from cached TDD context
9. Agent updates `user_input.py` and `validator.py`
10. **System tracks**: "TDD 4.3 → implemented in user_input.py:56, validator.py:123"

**Success Metric:** Agent references TDD once instead of 4 times (75% reduction in doc re-reads)

#### Workflow 3: Refactoring Shared Utilities

**User Story:**
"As a developer, I want to refactor a shared function safely, knowing which files will be affected, so I don't break dependent code."

**User Flow:**
1. User asks: "Refactor retry_with_backoff to add a timeout parameter"
2. Agent reads `retry.py`
3. **System identifies dependents**: "Used in sheets.py, bot.py, setup.py, fetcher.py"
4. Agent proposes: "This will require updating 4 call sites. Proceed?"
5. User confirms
6. Agent edits `retry.py` function signature
7. **System maintains context graph** of all call sites
8. Agent updates each dependent file:
   - `sheets.py:45` - adds timeout=30
   - `bot.py:200` - adds timeout=30
   - `setup.py:67` - adds timeout=60 (different based on context)
   - `fetcher.py:89` - adds timeout=30
9. **System tracks**: All call sites updated, refactor complete

**Success Metric:** Agent updates all dependents without missing any (100% coverage vs. 60-80% without context links)

### 3.4 V0.2.0 Design Context: Multi-Session State Sharing

**Purpose of This Section:**

This section provides critical context for the TDD (Technical Design Document) to ensure v0.1.0 is architected to smoothly transition to v0.2.0 capabilities without requiring unexpected refactoring. The requirements described here are **product requirements**, while implementation details (IPC mechanisms, serialization formats, MCP protocol specifics) should be investigated and decided during the TDD phase.

#### 3.4.1 The V0.2.0 Product Requirement

**Core Requirement:** Enable state sharing between parent Claude Code sessions and subagent sessions to eliminate redundant codebase parsing during concurrent code review workflows.

**User-Facing Problem (V0.2.0):**
- When parent sessions spawn subagents for code review, each subagent currently starts with zero context
- Subagents must re-parse files and rebuild relationship graphs that the parent already constructed
- This redundant work consumes 25% of session token limit per review phase (see Q-8)
- Multi-phase reviews (2+ phases) consume ~50% of session limit just for reviews
- **Business impact:** Users can only complete 1 PR per session due to token exhaustion

**User-Facing Solution (V0.2.0):**
- Subagent sessions inherit the parent's relationship graph and cached snippets
- Subagents start with immediate access to context the parent already discovered
- Subagents can extend the graph by reading additional files not yet accessed by parent
- **Target impact:** Reduce review overhead from 25% → <20% per phase, enabling 2 PRs per session

#### 3.4.2 Architecture Context for TDD

**MCP Server Deployment Model:**

When this tool is implemented as an MCP server:
- The parent Claude Code session runs one instance of the MCP server
- Each subagent session spawns its own separate MCP server instance
- **Key challenge:** Subagent MCP servers must leverage the stateful context (relationship graph, cached snippets) from the parent MCP server instance

**State Sharing Requirement:**

All state built by the parent session should be accessible to subagent sessions, including:
- Relationship graph (file imports, function calls, dependencies)
- Cached code snippets with metadata (line ranges, timestamps, relevance scores)
- File modification timestamps for cache invalidation
- Warning/limitation metadata (files with dynamic patterns, unparseable files)

**Incomplete Graph Assumption (Critical):**

The relationship graph is **always incomplete by design**:
- Parent sessions only scan files relevant to the current feature branch work
- Full codebase scanning would not scale to large repositories (10K+ files)
- Subagents may read additional files during review, extending the graph incrementally
- The system must support concurrent graph extension by multiple subagent readers

**Concurrency Model:**

The v0.2.0 solution should optimize for this common workflow pattern:
- **Single writer:** One parent session making code changes on a Git feature branch
- **Multiple readers:** Multiple concurrent subagent sessions performing read-only code review
- **Conflict avoidance:** Subagents do not write to files, only summarize feedback for the parent
- **Rare case:** Multiple parent sessions on the same feature branch is unlikely (would cause conflicting edits)

#### 3.4.3 Implementation Approaches (For TDD Investigation)

**Note:** The PRD does not prescribe a specific implementation. The TDD should investigate and select the optimal approach based on MCP server capabilities and constraints.

**Approach 1: Persistence-Based State Sharing**
- Parent writes relationship graph and cache to persistent storage (file, database)
- Subagents read from the same persistent storage on startup
- Requires handling concurrent reads/writes and cache invalidation
- **Consideration:** MCP server lifecycle is typically tied to Claude session lifecycle

**Approach 2: MCP-to-MCP Discovery and Communication**
- Subagent MCP servers discover and connect to the parent MCP server
- Parent exposes an API for querying graph state and cached snippets
- Requires inter-process communication mechanism (sockets, named pipes, shared memory)
- **Consideration:** May require extending MCP protocol or using out-of-band communication

**Approach 3: Hybrid Approach**
- Parent maintains hot state in-memory for performance
- Parent periodically snapshots state to persistent storage for subagent startup
- Subagents can query parent directly for fresh data if parent still running
- **Consideration:** Balances performance and reliability

**TDD Action Items:**

The TDD should investigate and answer:
1. What is the MCP server lifecycle model? (Tied to Claude session, long-running service, other?)
2. Does the MCP protocol support server-to-server communication?
3. What IPC mechanisms are available and appropriate for state sharing?
4. What is the optimal state serialization format for sharing graphs and cached snippets?
5. How should concurrent graph extension by subagents be coordinated?
6. What performance characteristics are required (subagent startup latency, graph query latency)?

**V0.1.0 Design Implications:**

To avoid major refactoring when implementing v0.2.0 state sharing, the v0.1.0 architecture should:
- Abstract the state storage layer (avoid tight coupling to in-memory data structures)
- Design the relationship graph data structure to be serializable/shareable
- Consider interfaces or hooks for state export/import even if not implemented in v0.1.0
- Document assumptions about thread safety and concurrent access patterns
- Use data structures that support incremental updates (append-only, versioned, CRDT-like)

However, v0.1.0 implementation should remain simple and focused on validating the core mechanism. Over-engineering for future requirements should be avoided if it adds complexity without immediate value.

---

## 4. Requirements

The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", and "MAY" in this section are to be interpreted as described in RFC 2119.

### 4.1 Functional Requirements

**Relationship Detection:**
- FR-1: The system MUST detect `import` and `from...import` statements in Python files (.py)
- FR-2: The system MUST detect function call relationships within the same Python codebase
- FR-3: The system SHOULD detect class inheritance relationships in Python
- FR-4: The system SHOULD detect module-level dependencies in Python
- FR-5: The system MUST update relationship graph when Python files are edited
- FR-6: The system MUST handle circular dependencies without infinite loops
- FR-7: The system MUST warn users when circular import dependencies are detected in Python code

**Context Injection:**
- FR-8: The system MUST provide cached context when agent accesses related files
- FR-9: The system SHOULD inject function signatures when agent edits call sites
- FR-10: The system MUST have a configurable maximum token limit per injection (initial default: 500 tokens, adjustable via configuration)
- FR-11: The system SHOULD prioritize recently-accessed relationships over older ones
- FR-12: The system MUST allow users to disable context injection via configuration

**Working Memory:**
- FR-13: The system MUST cache file snippets (not full files) for recently-accessed code
- FR-14: The system MUST have a configurable cache expiry time (initial default: 10 minutes of inactivity, adjustable via configuration)
- FR-15: The system MUST invalidate cache when underlying file is modified
- FR-16: The system MUST have a configurable cache size limit (initial default: 50KB per session, adjustable via configuration)
- FR-17: The system MUST provide cache hit/miss statistics for debugging

**Cross-File Awareness:**
- FR-18: The system MUST identify all files that import/call a function being edited
- FR-19: The system MUST track and report the number of files that depend on each function being edited (metric emission, no fixed threshold)
- FR-20: The system SHOULD provide a list of dependent files when requested
- FR-21: The system MUST track bidirectional relationships (A imports B, B imported by A)

**Relationship Graph Management:**
- FR-22: The system MUST maintain relationship graph in-memory during session (v0.1.0 does not persist across restarts)
- FR-23: The system MUST provide serialization/export of relationship graph to structured format (JSON or similar)
- FR-24: The system SHOULD provide API to query relationship graph structure programmatically
- FR-25: Exported graph MUST include: all detected relationships, file paths, relationship types, timestamps, and metadata for validation

**Context Injection Logging:**
- FR-26: The system MUST log all context injection events to a structured format
- FR-27: Context injection logs MUST include: timestamp, source file, target file, relationship type, injected snippet, cache age, and token count
- FR-28: Context injection logs SHOULD use the same format as Claude Code session logs (`.jsonl`) for consistency
- FR-29: The system MUST provide an API or query mechanism to access recent context injection events

**Dynamic Python Handling and Warnings:**
- FR-30: The system MUST emit warnings when encountering Python patterns that cannot be statically analyzed
- FR-31: The system MUST distinguish between test modules and source modules when emitting warnings
- FR-32: Test module identification MUST support common patterns: `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`, `**/conftest.py`
- FR-33: The system MUST emit warnings for dynamic dispatch (`getattr()` with dynamic names) in source modules only (see EC-6)
- FR-34: The system MUST emit warnings for monkey patching (runtime attribute reassignment) in source modules only (see EC-7)
- FR-35: The system MUST emit warnings for `exec()` and `eval()` usage in source modules only (see EC-9)
- FR-36: The system SHOULD emit informational warnings for decorators that may modify behavior in source modules (see EC-8)
- FR-37: The system SHOULD emit informational warnings for metaclass usage (see EC-10)
- FR-38: Warning messages MUST include: file path, line number, pattern type, and explanation of limitation
- FR-39: The system MUST allow users to configure warning suppression via configuration file (e.g., `.cross_file_context_links.yml`)
- FR-40: The system SHOULD support warning suppression at file, directory, or pattern-specific level
- FR-41: All warnings for unhandled dynamic patterns MUST be logged to structured format for analysis
- FR-42: The system MUST NOT attempt to track relationships for patterns it cannot statically analyze (fail-safe principle)

**Session Metrics and Data Collection:**
- FR-43: The system MUST emit structured metrics at the end of each Claude Code session
- FR-44: Session metrics MUST include all measurable values referenced in configurable parameters (see Q-10)
- FR-45: Session metrics MUST be written to a structured format (`.jsonl` or similar) for later analysis
- FR-46: The system MUST track and emit the following metrics per session:
  - Cache performance: actual cache expiry times used, cache hit rate, cache miss rate, total cache size at peak
  - Context injection: actual token counts per injection (min, max, median, p95), number of injections exceeding various token thresholds
  - Relationship graph: number of files in graph, number of relationships, most-connected files (top 10 with dependency counts)
  - Function usage distribution: for all functions edited during session, how many files depend on each (histogram data)
  - Re-read patterns: files re-read during session with re-read counts
  - Performance: actual parsing times per file (min, max, median, p95), injection latency measurements
  - Warning statistics: count of each warning type emitted, files with most warnings
- FR-47: Metrics MUST be anonymized/aggregatable to enable cross-session analysis without exposing sensitive code details
- FR-48: The system SHOULD provide a metrics analysis tool to help users understand normal vs. outlier patterns
- FR-49: Configuration parameters MUST be adjustable based on observed metrics (no hard-coded thresholds that cannot be tuned)

### 4.2 Non-Functional Requirements

**Performance:**
- NFR-1: Relationship detection MUST complete within 200ms for files <5000 lines
- NFR-2: Context injection MUST NOT add more than 50ms latency to Read operations
- NFR-3: The system SHOULD handle codebases up to 10,000 files
- NFR-4: The system MUST NOT consume more than 500MB of memory for relationship graph

**Privacy & Security:**
- NFR-5: The system MUST operate entirely locally (no cloud calls for core functionality)
- NFR-6: The system MUST NOT transmit file contents to external servers
- NFR-7: The system SHOULD respect .gitignore patterns for indexing
- NFR-8: The system MUST NOT index files in node_modules, .venv, or similar dependency directories

**Usability:**
- NFR-9: The system MUST work without manual configuration for standard project layouts
- NFR-10: The system SHOULD provide visual indicators when context is injected
- NFR-11: The system MUST allow users to query the relationship graph
- NFR-12: The system SHOULD log all relationship detections for debugging

**Compatibility:**
- NFR-13: The system MUST integrate with Claude Code's existing MCP architecture
- NFR-14: The system MUST NOT conflict with existing Read/Edit/Write tools
- NFR-15: The system SHOULD support incremental indexing (not require full re-scan)
- NFR-16: The system MUST gracefully degrade when parsing fails for a file

### 4.3 Out of Scope

The following items are explicitly out of scope for version 0.1.0:

**Language Support:**
- Terraform support (deferred to v0.2.0 - see Language Support Roadmap)
- TypeScript/JavaScript support (deferred to v0.3.0 - see Language Support Roadmap)
- Go support (deferred to v0.4.0 - see Language Support Roadmap)
- Full semantic analysis for all programming languages (v0.1.0 focuses on Python only)
- IDE-like refactoring tools (rename across files, extract function, etc.)
- Compile-time type checking or linting integration
- Preventing or fixing circular imports (we detect and warn only, not fix)

**Advanced Features:**
- AI-powered semantic similarity (embeddings) - version 0.1.0 uses structural analysis only
- Cross-repository dependency tracking
- Integration with external code intelligence platforms (Sourcegraph, etc.)
- Real-time collaboration features

**Performance Optimization:**
- Relationship graph persistence across restarts (v0.1.0 uses in-memory only per FR-22; persistence deferred to v0.2.0+)
- Distributed indexing for massive codebases (>100K files)
- GPU acceleration for parsing

**Enterprise Features:**
- Team-wide shared context graphs
- Analytics dashboard for context usage
- Admin controls for organization-wide policies

**Documentation:**
- The relationship graph data structure and storage format (will be in TDD)
- Specific AST parsing libraries and implementation details (will be in TDD)
- MCP server API specification (will be in TDD)

---

## 5. Success Metrics

### 5.1 Primary Metrics

| Metric | Baseline (No Context Links) | Target (With Context Links) | Measurement Method |
|--------|---------------------------|----------------------------|-------------------|
| **File Re-Read Rate** | 87.5% of files re-read | <30% of files re-read | Session log analysis |
| **Re-Reads Per File** | 3.2 re-reads/file on avg | <1.5 re-reads/file | Session log analysis |
| **Cross-File Ping-Pong Events** | ~20 per session | <5 per session | Pattern detection in logs |
| **Edit-Verify Re-Reads** | 100% (always re-read after edit) | <10% (use cached context) | Tool sequence analysis |

### 5.2 Secondary Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Context Injection Accuracy** | >85% relevant injections | User feedback + **automated analysis of injection logs** |
| **Cache Hit Rate** | >60% of potential re-reads served from cache | **Automated from context injection logs (FR-26)** |
| **Average Context Age** | <5 minutes | **Parse injection logs, measure `cache_age_seconds`** |
| **Injection Token Efficiency** | <300 tokens/injection | **Sum `token_count` from injection logs** |
| **Relationship Detection Coverage** | >90% of imports detected | Codebase analysis |
| **User Satisfaction** | >4.0/5.0 rating | Post-session survey |
| **Time to First Relevant Context** | <2 seconds | **Timestamp analysis in injection logs** |

### 5.3 Success Criteria

The MVP (version 0.1.0) will be considered successful if:

1. ✅ **Primary Goal Met:** File re-read rate reduced from 87.5% to <30% (65% reduction)
2. ✅ **User Adoption:** At least 10 developers use it for 1+ week without disabling
3. ✅ **Performance Acceptable:** <5% of users report noticeable slowdown
4. ✅ **Accuracy Acceptable:** <10% of context injections are marked as "not helpful" by users
5. ✅ **No Regressions:** Existing Claude Code workflows continue to work unchanged

---

## 6. Edge Cases

Full details in [`prd_edge_cases.md`](./prd_edge_cases.md).

### Edge Case Categories

- **6.1 Relationship Detection Edge Cases**
  - EC-1: Circular Dependencies (Python)
  - EC-2: Dynamic Imports
  - EC-3: Aliased Imports
  - EC-4: Wildcard Imports (Supported with Limitations)
  - EC-5: Conditional Imports
  - EC-6: Dynamic Dispatch (Unhandled in v0.1.0)
  - EC-7: Monkey Patching (Unhandled in v0.1.0)
  - EC-8: Decorators Modifying Behavior (Partially Handled)
  - EC-9: exec() and eval() Usage (Unhandled in v0.1.0)
  - EC-10: Metaclasses (Partially Handled)
- **6.2 Context Injection Edge Cases**
  - EC-11: Stale Cache After External Edit
  - EC-12: Large Functions
  - EC-13: Multiple Definitions
  - EC-14: Deleted Files
- **6.3 Memory Management Edge Cases**
  - EC-15: Memory Pressure
  - EC-16: Long-Running Sessions
  - EC-17: Massive Files
- **6.4 Failure Mode Edge Cases**
  - EC-18: Parsing Failure
  - EC-19: Relationship Graph Corruption
  - EC-20: Concurrent File Modifications

---

## 7. Error Handling

### 7.1 Parsing Errors

**Error Type:** File contains syntax errors preventing AST parsing

**User Impact:** Relationship detection fails for that file

**Handling Strategy:**
1. Log warning: "Failed to parse {file_path}: {error_message}"
2. Skip relationship detection for that file
3. Continue processing other files
4. Mark file as "unparseable" in relationship graph
5. Retry parsing if file is later modified (syntax error may be fixed)

**User Communication:**
- Silent for users (logged but not surfaced as error)
- Developers can see in debug logs if troubleshooting

**Fallback:**
- Agent can still read/edit file normally
- Just won't have cross-file context links for that file

### 7.2 Relationship Graph Errors

**Error Type:** Internal relationship graph becomes corrupted or inconsistent

**User Impact:** Context injection may provide incorrect or outdated information

**Handling Strategy:**
1. Implement validation checks after each graph update
2. If inconsistency detected:
   - Log critical error: "Relationship graph corrupted, rebuilding..."
   - Clear entire graph
   - Trigger full re-index of workspace
   - Notify user: "Rebuilding code context, may take 30 seconds..."
3. Prevent agent from using corrupted data

**User Communication:**
- Display one-time notification: "Code context is rebuilding..."
- Log details for developers to debug root cause

**Fallback:**
- Agent continues working without context links during rebuild
- Full functionality restored after re-index completes

### 7.3 Cache Inconsistency Errors

**Error Type:** Cached file snippet doesn't match actual file contents (missed external edit)

**User Impact:** Agent may use outdated information leading to incorrect edits

**Handling Strategy:**
1. Implement file modification time checks before using cache
2. If mtime mismatch detected:
   - Invalidate cache entry immediately
   - Force fresh read from filesystem
   - Log warning: "Cache invalidated for {file_path} due to external modification"
3. Update cache with fresh content

**User Communication:**
- Silent for users (handled automatically)
- Logged for debugging

**Fallback:**
- Agent always sees current file contents (no stale data risk)
- Slight performance degradation (re-read instead of cache hit)

### 7.4 Performance Degradation

**Error Type:** Indexing takes >30 seconds on large codebases

**User Impact:** User experiences slowdown when opening workspace

**Handling Strategy:**
1. Implement background indexing with progress indicator
2. Allow agent to start working before indexing completes
3. Incrementally provide context links as files are indexed
4. Show progress: "Indexing codebase... 1,234 / 5,678 files"

**User Communication:**
- Display progress notification during initial indexing
- Allow user to cancel indexing if desired
- Provide option to exclude directories from indexing

**Fallback:**
- Agent works normally without context links until indexing completes
- User can manually disable indexing for faster startup

### 7.5 Language Support Errors

**Error Type:** Unsupported language or file type encountered

**User Impact:** Relationship detection unavailable for that file type

**Handling Strategy:**
1. Maintain whitelist of supported languages (Python only for v0.1.0; see Language Support Roadmap)
2. For unsupported files:
   - Log info: "Skipping {file_path} - unsupported language: {extension}"
   - Do not attempt parsing
   - Mark as "unsupported" in graph
3. Provide clear documentation of supported languages

**User Communication:**
- Silent for users (expected behavior)
- Document supported languages in README

**Fallback:**
- Agent can still read/edit unsupported files
- No context links for those files (graceful degradation)

---

## 8. Testing and Validation

Full details in [`prd_testing.md`](./prd_testing.md).

### Test Categories

- **8.1 Test Environment Setup** - Test codebase and metrics collection
- **8.2 Functional Testing**
  - Test Category 1: Relationship Detection (T-1.1 through T-1.8)
  - Test Category 2: Context Injection (T-2.1 through T-2.5)
  - Test Category 3: Working Memory Cache (T-3.1 through T-3.5)
  - Test Category 4: Cross-File Awareness and Graph Management (T-4.1 through T-4.8)
  - Test Category 5: Context Injection Logging (T-5.1 through T-5.7)
  - Test Category 6: Dynamic Python Handling and Warnings (T-6.1 through T-6.10)
- **8.3 Performance Testing**
  - Test Category 7: Indexing Performance (T-7.1 through T-7.4)
  - Test Category 8: Runtime Performance (T-8.1 through T-8.4)
- **8.4 Integration Testing**
  - Test Category 9: Claude Code Integration (T-9.1 through T-9.6)
  - Test Category 10: Session Metrics and Data Collection (T-10.1 through T-10.7)
- **8.5 User Acceptance Testing** - Alpha, Beta, and Pilot phases

---

## 9. Open Questions

Full details in [`prd_open_questions.md`](./prd_open_questions.md).

### 9.1 Product Questions

- Q-1: Context Injection UI (UX Preference, Not Architectural Requirement)

### 9.2 Technical Questions

- Q-2: AST Parsing Library Choice (Python)
- Q-3: Cache Storage Format
- Q-4: File Watcher Implementation
- Q-5: Context Injection Log Format and Storage

### 9.3 Data and Validation Questions

- Q-6: Data Sample Sufficiency
- Q-7: Snippet Injection Sufficiency
- Q-8: Token Savings Quantification and Bottleneck Analysis
- Q-9: Function Call Detection Feasibility
- Q-10: Requirement Parameter Justification and Metrics-Driven Thresholds
- Q-11: Correctness vs. Efficiency Trade-off
- Q-12: Scope Prioritization for MVP

---

## 10. Gaps Discovered During Implementation

*This section will be populated during development as gaps in the PRD are discovered.*

*Format for each gap:*
- **Gap #:** Title
- **Date discovered:** YYYY-MM-DD
- **Original design:** What the PRD assumed
- **Gap identified:** What was actually needed
- **Impact:** How it affected users or implementation
- **Resolution:** How it was addressed
- **Related TDD sections:** Cross-reference to technical design

---

## Appendix A: User Research Data

### Session Analysis Summary

**Data Source:** 3 Claude Code sessions analyzed from ../retrospective_analysis/

| Session | Duration | Total Tools | Re-Reads | Most Re-Read File | Ping-Pong Events |
|---------|----------|-------------|----------|-------------------|------------------|
| 1ea0f7d8 | 4 hours | 261 | bot.py (8x), retry.py (7x) | 14/16 files (87.5%) | ~20 |
| bb8fdbd8 | 15 min | 95 | tdd.md (5x), README.md (4x) | 3/14 files (21%) | ~8 |
| ac56bc23 | 46 min | 74 | tdd.md (10x), prd.md (2x) | 2/3 files (66%) | 2 |

**Key Insights:**
1. 60-87% of files accessed are re-read at least once
2. Files with cross-file dependencies (imports, shared utilities) are re-read most
3. Documentation files (TDD, PRD, README) are frequently re-read during implementation
4. Ping-pong pattern scales with task complexity (4-hour session has 20 ping-pongs)

### User Pain Points (from analysis)

1. **"I keep forgetting what that function does"**
   - Context: After 40+ tool calls working on other files
   - Impact: Agent re-reads previously accessed files
   - Frequency: 60-80% of multi-file sessions

2. **"Switching between doc and code is tedious"**
   - Context: Implementing feature per TDD specification
   - Impact: TDD re-read 5-10 times during single feature implementation
   - Frequency: 100% of spec-driven development sessions

3. **"I'm afraid of breaking things in shared utilities"**
   - Context: Editing function used across multiple files
   - Impact: Uncertainty leads to conservative changes or extensive manual checking
   - Frequency: 40% of refactoring tasks

---

## Appendix B: Comparison with Existing Tools

See `existing_tools_analysis.md` for detailed comparison of:
- Cursor's @Codebase (65% similarity)
- Sourcegraph Code Intelligence (75% similarity)
- Code Context MCP Server (55% similarity)
- Augment Code (60% similarity)
- Continue.dev (50% similarity)

**Key Differentiator:** Cross-File Context Links uniquely combines:
- Structural relationship tracking (like Sourcegraph)
- Proactive context injection (better than all alternatives)
- Local-first architecture (like Code Context MCP)
- Integrated workflow (like Cursor)

---

**Document Status:** Draft - Ready for review and iteration

**Next Steps:**
1. Review with stakeholders
2. Address remaining open questions (Section 9):
   - Q-6: Gather additional session data (target: 20-50 sessions)
   - Q-7: Validate snippet injection sufficiency via multi-agent review
   - Q-8: Quantify token savings from existing sessions (v0.1.0) and project v0.2.0 bottleneck impact
   - Q-11: Validate correctness vs. efficiency trade-off
   - Q-12: Prioritize MVP scope (imports-only vs. full feature set)
3. Decisions made (documented in Section 9):
   - Q-1: Context injection UI - Deferred to post-production launch (gather user feedback first)
   - Q-2: AST parsing library - Use `ast` (Python stdlib) for v0.1.0
   - Q-3: Cache storage format - In-memory dict for v0.1.0 (can evolve based on learnings)
   - Q-4: File watcher - OS file system events for broad edge case coverage
   - Q-5: Context injection logs - Option A (append to session logs with full snippets for v0.1.0)
   - Q-9: Function call detection - Option A selected (best-effort with warnings)
   - Q-10: Parameter limits - Metrics-driven approach selected (measure first, set thresholds later)
4. Finalize requirements based on feedback and data analysis
5. Proceed to Technical Design Document (TDD)
6. Implementation (including metrics infrastructure per FR-43 through FR-49):
   - Implement core functionality (relationship detection, context injection, caching)
   - Implement session metrics emission at end of each session
   - Implement comprehensive data collection for all configurable parameters
   - Implement metrics analysis tool for identifying normal vs. outlier patterns
7. Deploy and collect metrics from production usage
8. Tune/adjust configurable limits based on observed metrics:
   - Analyze metrics to identify normal vs. outlier patterns
   - Set data-driven thresholds (e.g., cache expiry, token limits, dependency count warnings)
   - Update default configuration values based on real usage data
   - Iterate as usage patterns evolve
