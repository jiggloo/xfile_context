# Cross-File Context Links - Open Questions

This document contains detailed open questions referenced in the main PRD (`prd.md`).

## Quick Reference

This document uses identifiers that reference other PRD documents:

- **FR-#**: Functional Requirements → See Section 4.1 in [`prd.md`](./prd.md)
- **NFR-#**: Non-Functional Requirements → See Section 4.2 in [`prd.md`](./prd.md)
- **EC-#**: Edge Cases → See [`prd_edge_cases.md`](./prd_edge_cases.md)
- **T-#.#**: Test Cases → See [`prd_testing.md`](./prd_testing.md)
- **Section #**: Other PRD sections → See [`prd.md`](./prd.md) table of contents

---

## 9. Open Questions

### 9.1 Product Questions

**Q-1: Context Injection UI (UX Preference, Not Architectural Requirement)**
- Given context injections will be logged (FR-26), how should they be visualized by default?
  - Option A: Inline in agent responses - Agent mentions context naturally ("I'll use retry_with_backoff from cached retry.py:120...")
  - Option B: Dedicated context panel - Separate UI sidebar showing active context in real-time
  - Option C: Tooltips/hover states - Context visible on-demand when hovering over function names
  - Option D: No default UI - Log-only, let users/community build visualization tools
  - Option E: Hybrid approach - Enable multiple options (e.g., A + B), users choose preference
- **Note:** This is a UX preference decision, not an architectural requirement. Context injection logging (FR-26) decouples the feature from UI decisions.
- **Decision: Defer until after production launch**
  - Rationale:
    - This is a UX preference, not an architectural requirement
    - Logging infrastructure (FR-26, FR-27, FR-28) already captures all context injection events
    - Better to gather user feedback from production usage before committing to UI approach
    - Community may develop their own visualization tools based on logs
    - v0.1.0 can ship with logging only, UI can be added in v0.2.0+ based on user demand
  - Post-launch approach:
    - Collect user feedback on desired visualization methods
    - Analyze which UI patterns would be most valuable
    - Consider community contributions and existing tool integrations
    - Make informed decision based on real usage patterns
- **Decision made:** Deferred to post-production launch

### 9.2 Technical Questions

**Q-2: AST Parsing Library Choice (Python)**
- Which library should be used for Python parsing?
  - Option A: `ast` (Python stdlib) - Simple, well-documented, no dependencies
  - Option B: `tree-sitter-python` - Universal parser, consistent with future language support
  - Option C: `astroid` (used by pylint) - More powerful, handles dynamic features
- **Trade-offs:**
  - `ast`: Fastest to implement, zero dependencies, works for 90% of cases
  - `tree-sitter`: Consistent pattern for adding v0.2.0+ languages, but adds dependency
  - `astroid`: Most powerful, but heavy dependency (pylint itself)
- **Decision: Use `ast` (Python stdlib) for v0.1.0**
  - Rationale:
    - Fastest to implement - part of Python standard library
    - Zero external dependencies - no installation or compatibility issues
    - Well-documented with extensive examples and community knowledge
    - Works for 90% of cases - sufficient for static import and function call detection
    - Lower complexity for initial implementation
  - Future evolution:
    - Consider `tree-sitter` when adding v0.2.0+ languages (TypeScript, Go, etc.)
    - `tree-sitter` provides consistent parsing interface across languages
    - Can migrate if `ast` limitations become blocking
  - Accepted limitations:
    - `ast` handles static analysis well, which is the primary use case
    - Dynamic Python features (EC-6 through EC-10) are handled via warning system (FR-30+)
    - Standard library is sufficient for v0.1.0 goals
- **Decision made:** `ast` (Python stdlib) for v0.1.0, consider `tree-sitter` for multi-language v0.2.0+

**Q-3: Cache Storage Format**
- How should cached snippets be stored?
  - In-memory dict (simple, non-persistent)
  - SQLite (queryable, persistent)
  - JSON files (debuggable, persistent)
- **Decision: Start with in-memory dict**
  - Rationale:
    - Simplest implementation for v0.1.0
    - No external dependencies
    - Sufficient for single-session caching (per FR-22: in-memory graph for v0.1.0)
    - Fast lookups with Python built-in dict
    - Aligns with v0.1.0 scope (no persistence across restarts)
  - Can evolve if needed:
    - Design and implementation may reveal need for persistence (v0.2.0+)
    - If metrics show value in cross-session caching, can migrate to SQLite or other storage
    - Initial implementation won't preclude future enhancements
- **Decision made:** In-memory dict for v0.1.0, can evolve in later versions based on learnings

**Q-4: File Watcher Implementation**
- How to detect file changes?
  - Polling (simple, high CPU)
  - OS file system events (efficient, complex)
  - Git hooks (limited to git repos)
- **Decision: Use OS file system events**
  - Rationale:
    - Covers broad range of file-changing edge cases:
      - File changes made by Claude Code before Git commit
      - Git pull/merge operations
      - Changes made by user in IDE (VS Code, vim, etc.)
      - External tools modifying files (linters, formatters, build systems)
      - File moves, renames, deletions
    - More efficient than polling (no constant CPU usage)
    - More comprehensive than Git hooks (works for non-git repos, catches pre-commit changes)
    - Critical for cache invalidation (FR-15) - must detect all file modifications
  - Implementation considerations:
    - Use platform-specific file watchers (e.g., `watchdog` library for cross-platform support)
    - Handle edge cases: rapid successive changes, file system event storms
    - Debounce events to avoid excessive graph rebuilds
    - Watch only project directories, respect .gitignore patterns (NFR-7, NFR-8)
  - Trade-offs accepted:
    - More complex implementation than polling
    - Platform-specific behavior to handle
    - Worth the complexity for correctness and efficiency
- **Decision made:** OS file system events for v0.1.0

**Q-5: Context Injection Log Format and Storage**
- Should context injections use existing Claude Code session log format or separate file?
  - Option A: Append to existing `.jsonl` session logs - Easier integration, single file per session
  - Option B: Separate `.context.jsonl` file - Cleaner separation, easier to parse
  - Option C: Both - Maximum flexibility but redundant
- What fields are essential vs optional in logged events?
  - Essential (FR-27): timestamp, source_file, target_file, relationship_type, snippet, cache_age, token_count
  - Optional candidates: relevance_score, injection_reason, agent_action_taken
- Should logs include full code snippets or just file pointers?
  - Full snippets: Better for post-session analysis, larger file size
  - Pointers only: Smaller logs, requires file access to reconstruct
  - Hybrid: Snippets up to 200 chars, then pointer
- How long should logs be retained?
  - Same as Claude Code session logs (user-controlled)
  - Separate retention policy (e.g., 30 days)
- **Decision: Option A (append to session logs) with full snippets for v0.1.0**
  - Storage format:
    - Append to existing Claude Code `.jsonl` session logs (per FR-28)
    - Single file per session - easier integration and management
    - Consistent with existing Claude Code logging infrastructure
  - Log content:
    - Include full code snippets (not just pointers) for v0.1.0
    - Better for post-session analysis without requiring file access
    - Enables offline analysis and debugging
    - Essential fields per FR-27: timestamp, source_file, target_file, relationship_type, snippet, cache_age, token_count
  - Log retention:
    - Follow same retention policy as Claude Code session logs (user-controlled)
    - No separate retention policy needed - simplifies management
  - Future optimization (v0.2.0+ if needed):
    - Can switch to hybrid approach (snippets up to N chars, then pointer) if log sizes become problematic
    - Can add separate `.context.jsonl` file if parsing/filtering becomes bottleneck
    - Monitor log file sizes via session metrics (FR-46) to inform future decisions
  - Rationale:
    - Simplest integration with existing Claude Code infrastructure
    - Single source of truth for session activity
    - Full snippets provide best debugging/analysis experience for v0.1.0
    - Can optimize later based on observed log sizes and usage patterns
- **Decision made:** Option A with full snippets for v0.1.0, optimize in v0.2.0+ if needed

### 9.3 Data and Validation Questions

**Q-6: Data Sample Sufficiency**
- Is the current data sample (3 sessions) sufficient to validate the problem and solution?
  - Current state: 3 sessions analyzed (4 hours, 46 min, 15 min)
  - Considerations:
    - 87.5% re-read rate comes from single 4-hour session
    - 15-minute session shows 21% re-read rate (significantly different pattern)
    - Session duration and task complexity may affect re-read patterns
  - Research questions:
    - How many sessions needed to establish statistical significance?
    - What's the variance in re-read patterns across different task types?
    - Do longer sessions show different patterns than shorter ones?
  - Investigation approach:
    - Analyze 20-50 additional sessions across different users and task types
    - Segment by session duration, task complexity, codebase size
    - Calculate variance and confidence intervals for re-read metrics
- **Decision needed by:** Before finalizing success metrics and baselines

**Q-7: Snippet Injection Sufficiency**
- Are injected code snippets sufficient for agent to make correct decisions, or does full file context remain necessary?
  - Current assumption: 20-140 line snippets provide adequate context
  - Potential concerns:
    - Agent may need surrounding context to understand snippet semantics
    - Edge cases may require seeing how function is used elsewhere in same file
    - Snippet without broader context could be misleading
  - Research questions:
    - What percentage of time does agent need full file after receiving snippet?
    - Does snippet-based context lead to more incorrect edits vs. full file reads?
    - What snippet size provides optimal balance (too small = insufficient, too large = defeats purpose)?
  - Investigation approach:
    - Leverage existing multi-agent review process used in production Claude Code projects
    - **Baseline methodology** (established from prior projects):
      - Phase 1: Claude Code writes code changes
      - Phase 2: Multiple specialized subagents review and fix errors (first review)
      - Phase 3: Multiple specialized subagents perform second review in new sessions
      - Baseline correctness: Second review finds errors in <1% of PRs
    - **Validation with snippet injection**:
      - Run same three-phase process with snippet injection enabled
      - Measure: Second review error rate with snippet injection vs. baseline
      - Sample size: Minimum 100 PRs to detect statistically significant increase
      - Track: Error severity (logic bugs vs. style issues), error attribution if possible
    - **Success criteria**:
      - Second review error rate remains <1% → snippet injection is sufficient
      - Error rate 1-5% → investigate root causes, consider fallback mechanisms
      - Error rate >5% → snippet injection degrading correctness, reconsider approach
    - **Secondary measurements**:
      - Re-read frequency: Does snippet injection reduce file re-reads as expected?
      - Token consumption: Actual token savings from snippets vs. full file reads
      - Scenarios where snippets work well vs. scenarios requiring full files
- **Decision needed by:** Before alpha testing (Week 1 UAT)

**Q-8: Token Savings Quantification and Bottleneck Analysis**
- What are the actual token savings from snippet injection, and where do they provide the most value?
  - **Context: The Real Bottleneck**
    - Code writing (v0.1.0 primary use case) is **not** the current token bottleneck
    - **Actual bottleneck**: Multi-agent review sessions (from Q-7 methodology)
      - 4-5 subagents per review phase × 2 phases = 8-10 new independent sessions per PR
      - Each subagent starts fresh and re-reads/re-parses code from scratch
      - Single review phase consumes **25% of session limit** (measured from Claude Code usage)
      - Two review phases consume **~50% of session limit** just for reviews
    - **Business impact**: Currently limited to ~1 PR per session limit
    - **Analogy**: Similar to "full table scans" in database optimization - reading entire files when only snippets are needed
  - **V0.1.0 Value Proposition** (in-memory graph, no persistence):
    - Optimizes single-session code writing (the non-bottleneck)
    - Primary value: Validate the mechanism and generate learnings
    - Secondary value: Improve user experience during initial code writing
    - Strategic value: Learnings can be applied to redesign multi-agent review process or other system components
  - **V0.2.0 Value Proposition** (with persistence, per Section 4.3):
    - Addresses the **actual bottleneck**: subagent session startup overhead
    - Persisted relationship graph enables:
      - Subagents load pre-built graph instead of re-parsing entire codebase
      - Immediate access to cached snippets for relevant code
      - Skip "read all related files to understand context" phase at startup
    - **Target impact**: Reduce review phase from 25% → <20% of session limit
    - **Business value**: Enable 2 PRs per session instead of 1 (100% throughput increase)
  - Research questions:
    - **V0.1.0 validation** (code writing sessions):
      - In session 1ea0f7d8 (bot.py re-read 8x, retry.py re-read 7x), how many tokens would snippet injection save?
      - What's the average snippet size vs. full file size for re-read files?
      - Does mechanism work as expected? (proof of concept)
    - **V0.2.0 impact analysis** (multi-agent review sessions):
      - What percentage of review phase tokens are consumed by file reads at startup?
      - How many files does each subagent read before beginning actual review work?
      - With persisted graph + snippets, what's the projected token reduction per review phase?
      - Can we reduce 25% → <20% per phase to enable 2 PRs per session?
  - Investigation approach:
    - **Phase 1 (V0.1.0 validation)**:
      - Retroactively analyze existing 3 code-writing sessions
      - For each re-read, calculate: (full file tokens) - (snippet tokens that would have been injected)
      - Validate mechanism works and provides measurable savings
    - **Phase 2 (V0.2.0 bottleneck analysis)**:
      - Analyze multi-agent review sessions (if logs available)
      - Measure: Tokens consumed by file reads during subagent startup vs. actual review work
      - Calculate: With persisted graph, how many startup file reads could be replaced with snippet injections?
      - Project: Token reduction per review phase (target: 25% → <20%)
    - **Phase 3 (Real-world validation)**:
      - Implement persistence in v0.2.0
      - Measure actual review phase token consumption with persisted graph
      - Validate: Can 2 PRs fit in single session limit?
  - Success criteria:
    - **V0.1.0**: Mechanism reduces re-read tokens by >30% in code-writing sessions (validates approach)
    - **V0.2.0**: Review phase tokens reduced from 25% → <20% of session limit (enables 2 PRs per session)
    - **Strategic**: Learnings inform improvements to multi-agent review architecture or other high-token processes
  - **Note on flexibility**:
    - Multi-agent review process may be redesigned in the future
    - Cross-File Context Links learnings could optimize other parts of the system beyond reviews
    - Even if specific bottleneck changes, the "avoid full file scans" principle remains valuable
- **Decision needed by:** Before implementation (TDD phase) for v0.1.0 validation plan; during v0.1.0 UAT for v0.2.0 persistence prioritization

**Q-9: Function Call Detection Feasibility**
- Is FR-2 (function call relationship detection) achievable with acceptable accuracy in Python's dynamic environment?
  - Current requirement: "MUST detect function call relationships" (FR-2)
  - Known challenges (see Edge Cases EC-6 through EC-10 for detailed handling):
    - **Dynamic dispatch** (EC-6): `getattr(obj, func_name)()` - function name unknown until runtime
    - **Monkey patching** (EC-7): `module.function = replacement` - runtime modifications
    - **Decorators** (EC-8): `@decorator` that wraps/modifies behavior
    - **exec/eval** (EC-9): `exec(code_string)`, `eval(expression)` - arbitrary code execution
    - **Metaclasses** (EC-10): Custom class creation logic
  - **Warning strategy** (FR-30 through FR-42):
    - System MUST emit warnings for unhandled patterns in source modules
    - System MUST distinguish test modules (where patterns are expected) from source modules
    - Warnings include file path, line number, pattern type, and limitation explanation
    - Users can suppress warnings via configuration
  - Research questions:
    - What percentage of function calls in typical codebases are statically analyzable?
    - What's acceptable false positive/negative rate for function call detection?
    - Should v0.1.0 focus on imports only (high accuracy) vs. function calls (lower accuracy)?
    - How frequent are dynamic patterns (EC-6 through EC-10) in real-world source code vs. test code?
  - Investigation approach:
    - Analyze representative Python codebases for dynamic vs. static call patterns
    - Measure prevalence of EC-6 through EC-10 patterns in source vs. test modules
    - Prototype function call detection with `ast` module
    - Measure precision/recall on known test cases
    - Validate warning system doesn't generate excessive noise in test suites
  - Options:
    - Option A: FR-2 remains MUST - implement best-effort function call detection, emit warnings for unhandled patterns (FR-30+)
    - Option B: FR-2 downgraded to SHOULD - focus v0.1.0 on imports only (higher accuracy, fewer warnings)
    - Option C: FR-2 split into FR-2a (static calls - MUST) and FR-2b (dynamic calls - emit warnings per FR-30+)
  - **Decision: Option A Selected**
    - FR-2 remains a MUST requirement - system will detect function call relationships
    - Implement best-effort static analysis for function calls using AST parsing
    - Emit warnings for unhandled dynamic patterns (EC-6 through EC-10) per FR-30 through FR-42
    - Distinguish test modules from source modules (FR-31, FR-32)
    - Suppress warnings in test modules to avoid noise
    - Maintain correctness via fail-safe principle (FR-42): never track relationships that cannot be statically analyzed
    - Document limitations clearly in user-facing documentation
    - Track statically-analyzable function calls with high confidence
    - Mark dynamic patterns as "untrackable" in relationship graph metadata
  - **Implementation approach**:
    - Use Python `ast` module to detect direct function calls: `function_name()`, `module.function_name()`
    - Track method calls on imported objects where possible
    - Detect and warn (but do not track) dynamic patterns: `getattr()`, monkey patching, `exec()`, `eval()`
    - Store decorator and metaclass information in metadata without attempting to analyze their runtime behavior
    - Provide clear warning messages that help users understand why certain relationships cannot be tracked
- **Decision made:** Option A selected
- **Cross-references**: See Edge Cases EC-6 through EC-10 for detailed pattern handling, FR-30 through FR-42 for warning requirements, Test Category 6 for validation

**Q-10: Requirement Parameter Justification and Metrics-Driven Thresholds**
- Should numeric limits be hard-coded or determined by data-driven analysis of actual usage patterns?
  - **Context**: No good prior data exists to set optimal thresholds
  - **Problem with fixed thresholds**:
    - FR-14: 10-minute cache expiry - why not 5? why not 20? No data to support this
    - FR-16: 50KB total cache size - arbitrary without understanding actual usage
    - FR-10: 500 tokens per injection limit - may be too low or too high depending on use case
    - Original FR-19: "Warn when function used in 3+ files" - why 3, not 2 or 5?
    - NFR-1: 200ms parsing time - technical constraint (keep as-is)
  - **Decision: Measure First, Set Thresholds Later**
    - Instead of hard-coding thresholds, emit metrics for all measurable values
    - Collect data during alpha/beta/production use
    - Set data-driven thresholds based on understanding of normal vs. outlier patterns
    - Example transformation:
      - Before: "Warn when function used in 3+ files" (arbitrary threshold)
      - After: "Track and emit how many files depend on each function edited" (FR-19, FR-46)
      - Later: Analyze data, discover "90% of functions used in ≤5 files, warn at >10 files" (data-driven)
  - **Implementation approach** (per FR-43 through FR-49):
    - All configurable parameters have initial default values (can be adjusted)
    - System emits comprehensive session metrics at end of each session
    - Metrics include: cache performance, token counts, dependency distributions, performance measurements
    - Metrics written to structured format (`.jsonl`) for aggregation and analysis
    - Provide metrics analysis tool to help identify normal vs. outlier patterns
    - Update default configurations based on observed data
  - **Benefits of metrics-driven approach**:
    - Decisions based on real usage data, not guesses
    - Easy to adjust thresholds as patterns emerge
    - Can set different thresholds for different environments (e.g., large vs. small codebases)
    - Provides transparency into system behavior
    - Enables continuous improvement based on feedback loop
  - **Initial defaults remain configurable**:
    - FR-10: 500 tokens per injection (configurable, measure actual distribution)
    - FR-14: 10 minutes cache expiry (configurable, measure actual cache age patterns)
    - FR-16: 50KB cache size (configurable, measure peak cache sizes)
    - NFR-1: 200ms parsing time (keep as technical performance requirement)
  - **Metrics to collect** (per FR-46):
    - Cache: hit rate, miss rate, peak size, actual expiry times
    - Injection: token counts (min/max/median/p95), threshold exceedances
    - Dependencies: function usage distribution, most-connected files
    - Performance: parsing times, injection latency
    - Warnings: counts by type, files with most warnings
- **Decision made:** Use metrics-driven approach - measure everything, set thresholds based on data
- **Requirements updated:** FR-10, FR-14, FR-16, FR-19 now configurable with initial defaults; FR-43 through FR-49 added for metrics emission

**Q-11: Correctness vs. Efficiency Trade-off**
- What's the acceptable error rate when choosing snippet injection speed over full file accuracy?
  - Core trade-off:
    - Full file re-read: Slower, but agent has complete context (baseline accuracy)
    - Snippet injection: Faster, but agent has partial context (potential accuracy loss)
  - Research questions:
    - What percentage of incorrect edits is acceptable for token/time savings?
    - How do users perceive speed gains vs. occasional errors?
    - Can system detect when snippet is insufficient and fall back to full read?
  - Investigation approach:
    - Use multi-agent review methodology from Q-7 to measure error rates
    - Baseline: Second review finds errors in <1% of PRs (no snippet injection)
    - With snippets: Measure second review error rate with snippet injection enabled
    - Additional user feedback: Survey developers on perceived accuracy and speed improvements
  - Acceptance criteria (aligned with Q-7):
    - Second review error rate remains <1%: Ship with snippet injection as default
    - Error rate 1-5%: Investigate root causes, consider fallback mechanism (snippet first, full file on agent request)
    - Error rate >5%: Reconsider approach, make opt-in only, or redesign snippet selection logic
  - Trade-off analysis:
    - If token savings are 50%+ but error rate increases to 2-3%, is it acceptable?
    - Should users be able to configure preference (speed vs. accuracy)?
    - Can we detect specific scenarios where snippets are insufficient and auto-fallback to full files?
- **Decision needed by:** After alpha testing, before beta (between UAT Phase 1 and 2)
- **Note:** This question is closely related to Q-7 (Snippet Injection Sufficiency) and will use the same validation data

**Q-12: Scope Prioritization for MVP**
- Which features are essential for v0.1.0 vs. which can be deferred to validate core value proposition?
  - Current v0.1.0 scope includes:
    - Import detection (FR-1)
    - Function call detection (FR-2)
    - Class inheritance detection (FR-3)
    - Module dependencies (FR-4)
    - Circular import warnings (FR-7)
    - Wildcard import support (EC-4)
  - Research questions:
    - What's the minimum feature set to test "snippet injection reduces re-reads"?
    - Which features add complexity without proportional value?
    - Can v0.1.0 be import-only to maximize accuracy and minimize complexity?
  - Options for scope reduction:
    - Option A: Full scope as written - test all features together
    - Option B: Import-only MVP - defer FR-2, FR-3, FR-4, FR-7, EC-4 to v0.2.0
    - Option C: Two-phase v0.1.0 - Phase 1: imports only, Phase 2: add function calls if Phase 1 succeeds
  - Trade-offs:
    - Broader scope: Tests complete vision, but harder to debug failures
    - Narrower scope: Faster to implement, easier to validate, but may miss interactions
  - Recommendation:
    - Start with import detection only (FR-1, FR-5, FR-6)
    - Validate core hypothesis: "Snippet injection for imported functions reduces re-reads"
    - Add FR-2, FR-3, FR-4 in v0.1.1 if v0.1.0 shows >30% re-read reduction
- **Decision needed by:** Before implementation begins

---
