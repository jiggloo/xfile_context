# GitHub Issue Persona Analysis

**Generated**: 2025-12-16
**Issues Analyzed**: 72 closed issues
**Repository**: xfile_context

## Executive Summary

This analysis examines 72 completed GitHub issues to identify patterns that suggest optimal "persona configurations" for Claude Code when working on different types of tasks. The goal is to help prime Claude Code with the right mindset, approach, and focus areas before starting work on specific issue types.

---

## 1. Orthogonal Dimensions Identified

Five independent dimensions emerged from analyzing the issue corpus. Each dimension represents a distinct aspect of how work should be approached:

### Dimension 1: Execution Mode
*How carefully should the work be approached?*

| Value | Description | Indicators |
|-------|-------------|------------|
| **Careful** | Requires methodical review, potential for subtle bugs or breaking changes | `requires_careful_review=true`, medium/high complexity, touches data integrity or core algorithms |
| **Direct** | Straightforward execution, clear path to completion | `requires_careful_review=false`, low complexity, isolated changes |

### Dimension 2: Discovery Mode
*How much upfront exploration is needed?*

| Value | Description | Indicators |
|-------|-------------|------------|
| **Exploratory** | Must investigate codebase before implementation | `requires_exploration=true`, ambiguity not low, root cause unknown |
| **Prescriptive** | Clear specifications, minimal discovery needed | `requires_exploration=false`, `has_clear_acceptance_criteria=true`, low ambiguity |

### Dimension 3: Primary Focus
*What type of work is this?*

| Value | Description | Typical `task_type` |
|-------|-------------|---------------------|
| **Builder** | Creating or enhancing functionality | `feature`, `refactor` |
| **Validator** | Verifying correctness, testing | `testing` |
| **Fixer** | Diagnosing and correcting defects | `bug_fix` |
| **Enabler** | Supporting development workflows | `infrastructure`, `documentation` |

### Dimension 4: Impact Scope
*How many areas of the codebase are affected?*

| Value | Description | Indicators |
|-------|-------------|------------|
| **Surgical** | Focused changes, minimal blast radius | `scope=single_file` or `few_files` |
| **Broad** | Changes span multiple areas or systems | `scope=many_files` or `cross_cutting` |

### Dimension 5: Domain Expertise
*What technical areas are involved?*

| Value | Key Domains |
|-------|-------------|
| **Core Logic** | `core_logic`, `parsing`, `data_model` |
| **Testing** | `testing`, `fixtures`, `validation` |
| **Protocol/API** | `api`, `mcp`, `serialization` |
| **Infrastructure** | `infrastructure`, `config`, `logging` |
| **Performance** | `performance`, `caching`, `optimization` |
| **User Experience** | `ux`, `error_handling`, `output_formatting` |

---

## 2. Persona Histogram

Issues clustered by dominant persona combination, ordered by frequency:

| Rank | Persona | Count | % | Primary Characteristics |
|------|---------|-------|---|-------------------------|
| 1 | **Prescriptive Builder** | 19 | 26% | Direct + Prescriptive + Builder + Surgical |
| 2 | **Prescriptive Validator** | 14 | 19% | Direct + Prescriptive + Validator + Surgical |
| 3 | **Prescriptive Enabler** | 11 | 15% | Direct + Prescriptive + Enabler + Surgical |
| 4 | **Careful Builder** | 10 | 14% | Careful + Prescriptive + Builder + Various |
| 5 | **Surgical Fixer** | 7 | 10% | Direct + Prescriptive + Fixer + Surgical |
| 6 | **Exploratory Builder** | 4 | 6% | Careful + Exploratory + Builder + Broad |
| 7 | **Cross-cutting Validator** | 4 | 6% | Careful + Prescriptive + Validator + Broad |
| 8 | **Exploratory Fixer** | 3 | 4% | Careful + Exploratory + Fixer + Various |

### Histogram Visualization

```
Prescriptive Builder     ████████████████████████████████████████  26% (19)
Prescriptive Validator   ██████████████████████████████           19% (14)
Prescriptive Enabler     ████████████████████████                 15% (11)
Careful Builder          ██████████████████████                   14% (10)
Surgical Fixer           ████████████████                         10% (7)
Exploratory Builder      ████████                                  6% (4)
Cross-cutting Validator  ████████                                  6% (4)
Exploratory Fixer        ██████                                    4% (3)
```

---

## 3. Example Issues by Persona

### 3.1 Prescriptive Builder (26%)
> *"I know exactly what to build, where it goes, and what success looks like."*

**Example Issues**: #8, #9, #13, #14, #15, #16, #17, #18, #27, #28, #29, #32, #34, #35, #37, #38, #39, #140, #141

**Characteristics**:
- Clear TDD section reference with explicit requirements
- Single-file or few-file scope
- Low complexity, no exploration needed
- Well-defined acceptance criteria

**Sample Issue Titles**:
- "Task 1.1: Define Core Data Models" (#8)
- "Task 2.2: Implement ImportDetector" (#13)
- "Task 4.5: Implement Context Injection Formatting" (#28)

---

### 3.2 Prescriptive Validator (19%)
> *"I have a clear test plan; my job is to verify correctness systematically."*

**Example Issues**: #7, #20, #40, #46, #93, #94, #95, #96, #97, #98, #99, #100, #148, #159

**Characteristics**:
- Testing-focused with explicit test cases (T-1, T-2, etc.)
- Ground truth or acceptance criteria defined
- May span multiple test files but logic is clear
- Coverage metrics or validation checkpoints specified

**Sample Issue Titles**:
- "Task 7.3.1: Create Representative Test Codebase" (#93)
- "Task 7.3.2: Implement T-1 Relationship Detection Tests" (#94)
- "Add 'extended' marker for CI-only redundant tests" (#159)

---

### 3.3 Prescriptive Enabler (15%)
> *"I set up infrastructure that enables others; configuration over code."*

**Example Issues**: #2, #3, #4, #5, #6, #11, #44, #124, #150, #158

**Characteristics**:
- Infrastructure/tooling focus (CI, pre-commit, config)
- Often single-file changes to configuration
- Clear success criteria (e.g., "completes in <2 minutes")
- Low ambiguity, well-documented patterns to follow

**Sample Issue Titles**:
- "Task 0.1: Setup pre-commit hooks" (#2)
- "Task 0.2: Configure lightweight checks GitHub Action" (#3)
- "Run local pre-commit unit tests on multiple cores" (#124)

---

### 3.4 Careful Builder (14%)
> *"I'm building something non-trivial that requires careful thought and review."*

**Example Issues**: #10, #12, #21, #24, #25, #26, #31, #33, #36, #125

**Characteristics**:
- Medium complexity features
- Touches core logic or data integrity
- Requires careful review for edge cases
- Clear specifications but implementation is nuanced

**Sample Issue Titles**:
- "Task 1.3: Implement Relationship Graph Operations" (#10)
- "Task 2.1: Implement AST Parser Framework" (#12)
- "Integrate two-phase analysis into production flow" (#125)

---

### 3.5 Surgical Fixer (10%)
> *"There's a clear bug with known symptoms; I fix it precisely."*

**Example Issues**: #114, #116, #131, #136, #138, #152, #155

**Characteristics**:
- Bug with clear reproduction steps
- Root cause identified or easily discoverable
- Single-file or few-file fix
- Low risk of introducing new issues

**Sample Issue Titles**:
- "Bug: read_with_context MCP tool returns no injected context on first read" (#114)
- "[Bug]: read_with_context() not idempotent when files are unchanged" (#131)
- "[Bug]: MCP Server tool descriptions are inaccurate" (#152)

---

### 3.6 Exploratory Builder (6%)
> *"I need to understand the codebase deeply before I can design the solution."*

**Example Issues**: #19, #22, #122, #125

**Characteristics**:
- Requires codebase exploration first
- Architectural decisions involved
- Medium-to-high complexity
- May touch many files
- Often includes feasibility analysis

**Sample Issue Titles**:
- "Task 3.1: Implement FileWatcher with Language Dispatch" (#19)
- "Add data model for data parsed from AST" (#122)

---

### 3.7 Cross-cutting Validator (6%)
> *"I'm testing across boundaries; integration and end-to-end scenarios."*

**Example Issues**: #41, #42, #45, #46

**Characteristics**:
- Integration or functional testing
- Touches multiple components/layers
- May require test fixtures spanning areas
- Higher complexity test scenarios

**Sample Issue Titles**:
- "Task 7.2: Implement Integration Tests" (#41)
- "Task 7.3: Implement Functional Test Suite" (#42)

---

### 3.8 Exploratory Fixer (4%)
> *"The bug is subtle; I need to investigate before I can fix."*

**Example Issues**: #117, #118, #133

**Characteristics**:
- Bug symptoms known but root cause unclear
- Requires debugging/investigation
- May involve complex interactions
- Higher risk of incomplete fix

**Sample Issue Titles**:
- "Bug: Lazy initialization doesn't re-analyze modified dependency files" (#117)
- "[Bug]: Relationships may be lost on subsequent read_with_context() calls" (#133)

---

## 4. Key Indicators by Persona

### Quick Reference: How to Identify Persona from Issue

| Persona | Keywords/Phrases | Semantic Patterns |
|---------|------------------|-------------------|
| **Prescriptive Builder** | "implement", "Task X.Y", "TDD Section", "acceptance criteria" | Numbered requirements, clear file targets, explicit success conditions |
| **Prescriptive Validator** | "T-1", "test", "coverage", "validate", "ground truth" | Test case IDs, coverage metrics, validation checkpoints |
| **Prescriptive Enabler** | "configure", "setup", "CI", "pre-commit", "GitHub Action" | Config file paths, tooling references, workflow automation |
| **Careful Builder** | "atomic", "thread-safe", "edge cases", "data integrity" | Concurrency concerns, correctness emphasis, architectural patterns |
| **Surgical Fixer** | "[Bug]:", "fix", "incorrect", "should be X but is Y" | Clear before/after, reproduction steps, single-cause identified |
| **Exploratory Builder** | "feasibility", "investigate", "design", "approach" | Open questions, multiple approaches considered, exploration needed |
| **Cross-cutting Validator** | "integration", "end-to-end", "functional", "workflow" | Multi-component interaction, realistic scenarios, broad coverage |
| **Exploratory Fixer** | "root cause unknown", "investigate", "debugging", "complex interaction" | Symptoms without clear cause, investigation steps, multiple hypotheses |

### Indicator Confidence by Signal Type

| Signal Type | Reliability | Notes |
|-------------|-------------|-------|
| Issue title prefix (`[Bug]:`, `Task X.Y:`) | High | Explicit categorization |
| TDD/PRD section references | High | Links to specifications indicate prescriptive work |
| Keywords ("atomic", "thread-safe") | Medium | Suggests careful approach needed |
| File count mentioned | Medium | Indicates scope |
| Presence of debugging steps | High | Indicates exploratory fixer |
| Test case IDs (T-1, T-2, etc.) | High | Indicates validator persona |

---

## 5. Priming Recommendations

### Before Starting an Issue, Consider:

1. **Read the issue completely** - Don't start until you understand which persona fits
2. **Check for TDD/PRD references** - Prescriptive issues link to specifications
3. **Look for scope indicators** - File counts, "single file" vs "cross-cutting" language
4. **Identify complexity signals** - "atomic", "edge cases", "thread-safe" = careful mode
5. **Check for unknown elements** - "investigate", "root cause unclear" = exploratory mode

### Persona-Specific Priming Prompts

**For Prescriptive Builder**:
> "This is a straightforward feature implementation with clear specs. Focus on matching the requirements exactly. Don't over-engineer."

**For Prescriptive Validator**:
> "This is systematic testing work. Follow the test case specifications precisely. Ensure coverage metrics are met."

**For Prescriptive Enabler**:
> "This is infrastructure/configuration work. Follow established patterns. Keep changes minimal and focused."

**For Careful Builder**:
> "This requires careful implementation with attention to edge cases and data integrity. Review thoroughly before marking complete."

**For Surgical Fixer**:
> "This is a targeted bug fix. Reproduce first, fix precisely, verify the fix doesn't break anything else."

**For Exploratory Builder**:
> "This requires investigation first. Explore the codebase, understand the architecture, then design the solution."

**For Cross-cutting Validator**:
> "This is integration/functional testing. Think about component interactions and realistic usage scenarios."

**For Exploratory Fixer**:
> "The root cause is unclear. Investigate systematically, form hypotheses, validate before implementing fix."

---

## 6. Distribution Insights

### Key Observations

1. **60% of issues are "Prescriptive"** - This codebase has strong documentation (TDD/PRD), resulting in most issues having clear specifications.

2. **Only 10% require exploration** - The project's documentation-first approach reduces ambiguity.

3. **"Builder" is the dominant focus (46%)** - The project is in active feature development phase.

4. **Bug fixes are mostly "Surgical" (70%)** - Good architecture means bugs are usually isolated.

5. **Testing work is highly prescriptive (100%)** - Test specifications (T-1, T-2, etc.) are well-defined.

### Implications for Workflow

- **For this specific codebase**: Claude Code can usually operate in "Prescriptive" mode because specifications exist
- **Default to careful review for**: core_logic, parsing, data integrity work
- **Fast-track infrastructure changes**: pre-commit, CI, config are low-risk
- **Watch for exploration signals**: "investigate", "unclear", "feasibility" = slow down

---

## Appendix A: Full Issue Classification

| Issue | Title (truncated) | Persona | Complexity | Scope |
|-------|-------------------|---------|------------|-------|
| #2 | Setup pre-commit hooks | Prescriptive Enabler | low | single_file |
| #3 | Configure lightweight checks GitHub Action | Prescriptive Enabler | low | single_file |
| #4 | Configure comprehensive tests GitHub Action | Prescriptive Enabler | low | single_file |
| #5 | Setup branch protection rules | Prescriptive Enabler | low | single_file |
| #6 | Create issue templates | Prescriptive Enabler | low | few_files |
| #7 | Validation - Create test PR | Prescriptive Validator | low | single_file |
| #8 | Define Core Data Models | Prescriptive Builder | low | single_file |
| #9 | Implement Storage Abstraction | Prescriptive Builder | low | single_file |
| #10 | Implement Relationship Graph Operations | Careful Builder | medium | single_file |
| #11 | Setup Project Structure and Configuration | Prescriptive Enabler | medium | few_files |
| #12 | Implement AST Parser Framework | Careful Builder | medium | few_files |
| #13 | Implement ImportDetector | Prescriptive Builder | medium | single_file |
| #14 | Implement AliasedImportDetector | Prescriptive Builder | low | single_file |
| #15 | Implement ConditionalImportDetector | Prescriptive Builder | low | single_file |
| #16 | Implement WildcardImportDetector | Prescriptive Builder | low | single_file |
| #17 | Implement FunctionCallDetector | Prescriptive Builder | medium | single_file |
| #18 | Implement ClassInheritanceDetector | Prescriptive Builder | low | single_file |
| #19 | Implement FileWatcher with Language Dispatch | Exploratory Builder | medium | few_files |
| #20 | Implement Event Debouncing and Batching | Prescriptive Validator | low | few_files |
| #21 | Implement Incremental Graph Updates | Careful Builder | medium | few_files |
| #22 | Implement File Deletion Handling | Exploratory Builder | medium | few_files |
| #23 | Parse .gitignore and Pytest Configuration | Prescriptive Builder | medium | few_files |
| #24 | Implement Working Memory Cache | Careful Builder | medium | few_files |
| #25 | Implement MCP Server Protocol Layer | Careful Builder | medium | few_files |
| #26 | Implement CrossFileContextService | Careful Builder | medium | many_files |
| #27 | Implement Context Injection Content Selection | Prescriptive Builder | medium | few_files |
| #28 | Implement Context Injection Formatting | Prescriptive Builder | low | single_file |
| #29 | Implement Cache Invalidation | Prescriptive Builder | low | few_files |
| #30 | Implement Test vs Source Module Classification | Prescriptive Builder | low | single_file |
| #31 | Implement Dynamic Pattern Detectors | Careful Builder | medium | few_files |
| #32 | Implement Warning Emission and Formatting | Prescriptive Builder | low | few_files |
| #33 | Implement Warning Suppression | Careful Builder | medium | few_files |
| #34 | Implement Warning Logging | Prescriptive Builder | low | few_files |
| #35 | Implement Context Injection Event Logging | Prescriptive Builder | low | few_files |
| #36 | Implement Session Metrics Collection | Careful Builder | medium | few_files |
| #37 | Implement Relationship Graph Export | Prescriptive Builder | low | few_files |
| #38 | Implement Query API | Prescriptive Builder | low | few_files |
| #39 | Implement Metrics Analysis Tool | Prescriptive Builder | low | single_file |
| #40 | Implement Unit Tests for Core Components | Prescriptive Validator | low | many_files |
| #41 | Implement Integration Tests | Cross-cutting Validator | medium | cross_cutting |
| #42 | Implement Functional Test Suite | Cross-cutting Validator | high | cross_cutting |
| #44 | Setup Developer Experience Infrastructure | Prescriptive Enabler | low | cross_cutting |
| #45 | Create Test Fixtures and Documentation | Cross-cutting Validator | low | few_files |
| #46 | Alpha Testing (Internal) | Prescriptive Validator | low | cross_cutting |
| #93 | Create Representative Test Codebase | Prescriptive Validator | medium | many_files |
| #94 | Implement T-1 Relationship Detection Tests | Prescriptive Validator | medium | single_file |
| #95 | Implement T-2 Context Injection Tests | Prescriptive Validator | medium | single_file |
| #96 | Implement T-3 Working Memory Cache Tests | Prescriptive Validator | low | single_file |
| #97 | Implement T-4 Cross-File Awareness Tests | Prescriptive Validator | low | single_file |
| #98 | Implement T-5 Context Injection Logging Tests | Prescriptive Validator | low | single_file |
| #99 | Implement T-6 Dynamic Python Handling Tests | Prescriptive Validator | low | single_file |
| #100 | Implement T-10 Session Metrics Tests | Prescriptive Validator | medium | single_file |
| #111 | Remove relative imports and enforce absolute imports | Prescriptive Enabler | low | many_files |
| #114 | Bug: read_with_context returns no context on first read | Surgical Fixer | low | single_file |
| #116 | Bug: Incorrect module classification for stdlib | Surgical Fixer | low | few_files |
| #117 | Bug: Lazy initialization doesn't re-analyze modified deps | Exploratory Fixer | medium | few_files |
| #118 | Bug: New function definitions not appearing | Exploratory Fixer | medium | few_files |
| #122 | Add data model for data parsed from AST | Exploratory Builder | medium | many_files |
| #124 | Run local pre-commit unit tests on multiple cores | Prescriptive Enabler | low | few_files |
| #125 | Integrate two-phase analysis into production flow | Careful Builder | high | many_files |
| #131 | Bug: read_with_context() not idempotent | Surgical Fixer | low | single_file |
| #133 | Bug: Relationships may be lost due to staleness resolver | Exploratory Fixer | medium | few_files |
| #136 | Clarify injected context | Surgical Fixer | low | single_file |
| #138 | Bug: Missing relationships in first read_with_context() | Surgical Fixer | low | few_files |
| #140 | Enhancement: Add FunctionDefinitionDetector | Prescriptive Builder | low | few_files |
| #141 | Enhancement: Add reference extraction for decorators | Prescriptive Builder | low | few_files |
| #148 | Optimize pre-commit test speed | Prescriptive Validator | medium | cross_cutting |
| #150 | Clean up logging architecture | Prescriptive Enabler | medium | many_files |
| #152 | Bug: MCP Server tool descriptions are inaccurate | Surgical Fixer | low | single_file |
| #155 | Session metrics not written on ungraceful shutdown | Surgical Fixer | low | few_files |
| #158 | Exclude integration/performance tests from pre-commit | Prescriptive Enabler | low | single_file |
| #159 | Add 'extended' marker for CI-only redundant tests | Prescriptive Validator | low | few_files |

---

*This analysis was generated by examining the full body of all 72 closed GitHub issues in the xfile_context repository.*
