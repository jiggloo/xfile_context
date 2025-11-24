# Cross-File Context Links - Testing and Validation

This document contains detailed testing plans referenced in the main PRD (`prd.md`).

## Quick Reference

This document uses identifiers that reference other PRD documents:

- **FR-#**: Functional Requirements → See Section 4.1 in [`prd.md`](./prd.md)
- **NFR-#**: Non-Functional Requirements → See Section 4.2 in [`prd.md`](./prd.md)
- **EC-#**: Edge Cases → See [`prd_edge_cases.md`](./prd_edge_cases.md)
- **T-#.#**: Test identifiers defined in this document

---

## 8. Testing and Validation

### 8.1 Test Environment Setup

**Test Codebase:**
- Create representative test repository with:
  - 50-100 Python files (.py)
  - Known cross-file dependencies (documented in test fixture)
  - Mix of simple and complex imports (`import`, `from...import`)
  - Circular dependencies (Python allows these)
  - Edge cases (dynamic imports, wildcards, aliases, `TYPE_CHECKING` conditionals)

**Test Metrics Collection:**
- Session log analyzer to measure re-read rates
- Cache hit/miss tracker
- Relationship detection coverage analyzer
- Performance profiler for indexing and injection latency

### 8.2 Functional Testing

**Test Category 1: Relationship Detection**
- T-1.1: Verify Python `import` statements detected correctly
- T-1.2: Verify Python `from...import` statements detected correctly
- T-1.3: Verify aliased imports tracked (`import foo as bar`, `from foo import bar as baz`)
- T-1.4: Verify wildcard imports tracked at module level (`from utils import *`)
  - Relationship graph shows module-level dependency
  - Context injection notes limitation of function-level tracking
  - Optional warning can be enabled via config
- T-1.5: Verify conditional imports tracked (`if TYPE_CHECKING: ...`)
- T-1.6: Verify function call relationships tracked within Python codebase
- T-1.7: Verify circular dependencies detected and warned without crash
- T-1.8: Verify incremental updates when Python file edited

**Test Category 2: Context Injection**
- T-2.1: Verify context injected when editing related files
- T-2.2: Verify injection token limit respected (<500 tokens)
- T-2.3: Verify relevant context selected (not random snippets)
- T-2.4: Verify injection can be disabled via config
- T-2.5: Verify injection timing (appears when needed)

**Test Category 3: Working Memory Cache**
- T-3.1: Verify cache hit for recently-read files
- T-3.2: Verify cache miss for old files (>10 min)
- T-3.3: Verify cache invalidation on file edit
- T-3.4: Verify cache size limit enforced (LRU eviction)
- T-3.5: Verify cache statistics accurate

**Test Category 4: Cross-File Awareness and Graph Management**
- T-4.1: Verify dependent files listed when editing shared function
- T-4.2: Verify warning when editing function used in 3+ files
- T-4.3: Verify bidirectional relationships tracked
- T-4.4: Verify query API returns correct dependents
- T-4.5: Verify relationship graph can be exported/serialized to structured format (FR-23)
- T-4.6: Verify exported graph contains all required fields per FR-25 (relationships, file paths, types, timestamps, metadata)
- T-4.7: Verify exported graph can be validated by external tools
- T-4.8: Verify graph is maintained in-memory only (no persistence across restarts in v0.1.0)

**Test Category 5: Context Injection Logging**
- T-5.1: Verify all context injections are logged to structured format (FR-26)
- T-5.2: Verify logs contain all required fields per FR-27 (timestamp, source_file, target_file, relationship_type, snippet, cache_age, token_count)
- T-5.3: Verify log format matches Claude Code session logs (.jsonl) for consistency
- T-5.4: Verify logs are parseable by standard JSON parsers
- T-5.5: Verify API/query mechanism can retrieve recent injection events (FR-29)
- T-5.6: Verify logs enable automated metrics calculation (cache hit rate, average context age, etc.)
- T-5.7: Verify log file size remains manageable (<10MB per 4-hour session)

**Test Category 6: Dynamic Python Handling and Warnings**
- T-6.1: Verify test module identification works correctly (FR-32)
  - Files matching `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`, `**/conftest.py` identified as test modules
  - Other `.py` files identified as source modules
- T-6.2: Verify dynamic dispatch warnings emitted correctly (FR-33, EC-6)
  - Source module with `getattr(obj, dynamic_name)()` → warning emitted
  - Test module with `getattr(obj, dynamic_name)()` → no warning
  - Warning includes file path, line number, and explanation
- T-6.3: Verify monkey patching warnings emitted correctly (FR-34, EC-7)
  - Source module with `module.attr = replacement` → warning emitted
  - Test module with `module.attr = replacement` (mocking) → no warning
  - Warning includes file path, line number, modified attribute name
- T-6.4: Verify exec/eval warnings emitted correctly (FR-35, EC-9)
  - Source module with `exec(code_string)` or `eval(expr)` → warning emitted
  - Test module with `exec()`/`eval()` → no warning
  - Warning includes file path, line number, and security/analysis implications
- T-6.5: Verify decorator warnings emitted appropriately (FR-36, EC-8)
  - Source module with custom decorator → informational warning if decorator uses dynamic features
  - Test module with `@pytest.mark`, `@unittest.skip` → no warning (common patterns)
  - Warning includes decorator name and explanation of limitation
- T-6.6: Verify metaclass warnings emitted correctly (FR-37, EC-10)
  - Class with custom metaclass → informational warning
  - Warning includes metaclass name and behavior caveat
- T-6.7: Verify warning message format compliance (FR-38)
  - All warnings include: file path, line number, pattern type, explanation
  - Warnings are machine-parseable (structured format)
- T-6.8: Verify warning suppression configuration works (FR-39, FR-40)
  - Configuration file (`.cross_file_context_links.yml`) can suppress warnings
  - Suppression works at file level: `suppress_warnings: ["path/to/file.py"]`
  - Suppression works at directory level: `suppress_warnings: ["tests/**/*"]`
  - Suppression works for specific pattern types: `suppress_dynamic_dispatch_warnings: true`
- T-6.9: Verify warnings are logged to structured format (FR-41)
  - All warnings logged to `.jsonl` file or similar
  - Log entries include timestamp, file, line, pattern type, message
- T-6.10: Verify fail-safe principle (FR-42)
  - System does NOT attempt to track relationships for unhandled dynamic patterns
  - Unhandled patterns marked as "untrackable" in relationship graph metadata
  - No incorrect relationships added to graph

### 8.3 Performance Testing

**Test Category 7: Indexing Performance**
- T-7.1: Benchmark indexing 100 files <5,000 lines each (target: <10 seconds)
- T-7.2: Benchmark indexing 1,000 files (target: <2 minutes)
- T-7.3: Verify incremental update <200ms per file
- T-7.4: Verify memory usage <500MB for 10,000 files

**Test Category 8: Runtime Performance**
- T-8.1: Benchmark context injection latency (target: <50ms)
- T-8.2: Benchmark cache lookup (target: <10ms)
- T-8.3: Verify no slowdown on Read operations without context links
- T-8.4: Stress test with 100 concurrent file accesses

### 8.4 Integration Testing

**Test Category 9: Claude Code Integration**
- T-9.1: Verify MCP server starts without errors
- T-9.2: Verify Read tool works with context injection
- T-9.3: Verify Edit tool invalidates cache correctly
- T-9.4: Verify no conflicts with other MCP servers
- T-9.5: Verify error messages surface properly in Claude Code UI
- T-9.6: Verify context injection logs integrate with Claude Code session logs

**Test Category 10: Session Metrics and Data Collection**
- T-10.1: Verify session metrics are emitted at end of session (FR-43)
  - Metrics written to structured format (`.jsonl` or similar)
  - Metrics file created in expected location
- T-10.2: Verify all required metrics are included (FR-44, FR-46)
  - Cache performance: hit rate, miss rate, peak size, actual expiry times
  - Context injection: token counts (min, max, median, p95), threshold exceedances
  - Relationship graph: file count, relationship count, most-connected files
  - Function usage distribution: dependency counts for edited functions
  - Re-read patterns: files re-read with counts
  - Performance: parsing times, injection latency (min, max, median, p95)
  - Warning statistics: counts by type, files with most warnings
- T-10.3: Verify metrics are properly structured and parseable (FR-45)
  - Valid JSON/JSONL format
  - Schema is consistent across sessions
  - Can be parsed by standard JSON tools
- T-10.4: Verify metrics are anonymized/aggregatable (FR-47)
  - No sensitive code snippets in metrics
  - File paths can be optionally anonymized
  - Metrics can be aggregated across sessions without privacy concerns
- T-10.5: Verify configuration parameters are adjustable (FR-49)
  - Cache expiry time configurable (FR-14)
  - Cache size limit configurable (FR-16)
  - Token injection limit configurable (FR-10)
  - Configuration changes reflected in session behavior
  - Metrics show actual configured values used
- T-10.6: Verify metrics enable data-driven threshold decisions
  - Function dependency distribution shows histogram (e.g., "80% functions used in ≤3 files")
  - Token injection distribution shows percentiles for setting limits
  - Cache performance metrics show optimal expiry times
  - Performance metrics identify outliers for optimization
- T-10.7: Verify metrics analysis tool functionality (FR-48)
  - Tool can parse session metrics
  - Tool produces summary statistics
  - Tool identifies normal vs. outlier patterns
  - Tool suggests optimal configuration values based on observed data

### 8.5 User Acceptance Testing

**UAT Phase 1: Alpha Testing (Week 1)**
- 3-5 internal developers
- Focus: Basic functionality, major bugs
- Success criteria: No critical bugs, 70% re-read reduction

**UAT Phase 2: Beta Testing (Weeks 2-3)**
- 10-15 external developers
- Focus: Real-world usage, edge cases
- Success criteria: <30% re-read rate, >80% satisfaction

**UAT Phase 3: Pilot Deployment (Week 4)**
- 50+ developers
- Focus: Performance at scale, user feedback
- Success criteria: All primary metrics met, <5% opt-out rate

---
