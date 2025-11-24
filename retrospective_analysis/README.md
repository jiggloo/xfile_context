# Claude Code Retrospective Analysis

This directory contains retrospective analysis of Claude Code workflows, including session analysis tools, problem identification, solution proposals, and **Product Requirements Documents (PRDs)** for implementing improvements.

## 📁 Directory Contents

### 🎯 Product Requirements Document (Start Here!)
- **`README_PRD.md`** - PRD overview and supporting analysis guide
- **`cross_file_context_links_prd.md`** - Cross-File Context Links PRD (60-70% re-read reduction)

### 📊 Analysis & Research
- **`sample_analysis_report.md`** - Real session data showing 87.5% file re-read rate
- **`ping_pong_analysis.md`** - Cross-session comparison identifying 3 ping-pong patterns
- **`generalized_solutions.md`** - 4 proposed solutions with implementation roadmap
- **`existing_tools_analysis.md`** - Comparison with 6 existing tools (Cursor, Sourcegraph, etc.)

### 🛠️ Analysis Tools
- **`session_analyzer.py`** - Python script to analyze `.jsonl` session logs
- **`README.md`** (this file) - Overview of the directory

---

## 🚀 Quick Start

**If you want to implement Cross-File Context Links:**
1. Read `README_PRD.md` for an overview of the PRD and supporting research
2. Review the PRD (`cross_file_context_links_prd.md`)
3. Use supporting analysis docs to understand the data and research behind decisions

**If you want to analyze your own sessions:**
1. Run `session_analyzer.py` on your Claude Code session logs
2. Compare results with `sample_analysis_report.md`

---

## 🔍 Session Analyzer Tool

### What It Analyzes

From `.jsonl` session logs in `~/.claude/projects/`, this tool extracts and analyzes:

1. **Search Efficiency**
   - Empty search results (Grep/Glob that found nothing)
   - Search success rate
   - Repeated search patterns (same query multiple times)

2. **File Access Patterns**
   - Total files read
   - Files accessed multiple times (potential context window saturation)
   - Time intervals between re-reads (indicates "forgetting")

3. **Tool Usage Distribution**
   - Breakdown of all tool calls by type
   - Overall session metrics

4. **Discovery Metrics**
   - Session duration
   - Time between search and first file read
   - First tool used

## Usage

```bash
python3 session_analyzer.py <path-to-session.jsonl>
```

### Example

```bash
python3 session_analyzer.py ~/.claude/projects/-Users-henruwang-Code-reaction-requests/1ea0f7d8-716c-4383-8ecd-4b4cbb0b72a5.jsonl
```

Output is written to stdout in markdown format. Redirect to a file to save:

```bash
python3 session_analyzer.py <session.jsonl> > analysis_report.md
```

### Sample Output

See `sample_analysis_report.md` for a real analysis of session `1ea0f7d8`.

**Key Findings from Sample:**
- **261 tool calls** over ~4 hours
- **14 files re-read** (out of 16 unique files accessed)
- Top re-read file: `bot.py` accessed **8 times** with first re-read after ~7.5 seconds
- `claude_workflows.md` re-read after **3.8 hours** (strong signal of context loss)

### Data Source

Session logs are automatically captured by Claude Code at:
- `~/.claude/projects/-<project-path>/<session-id>.jsonl`

Each log contains:
- Tool invocations with full parameters
- Tool results with metadata
- Timestamps (millisecond precision)
- Session context (git branch, working directory)

### Requirements

- Python 3.7+
- Standard library only (no external dependencies)

---

## 📈 Research Findings Summary

### The Problem
From analyzing 3 real Claude Code sessions:
- **60-87% of files are re-read** at least once
- **Files re-read 3.2 times on average**
- **20+ cross-file ping-pong events** per long session
- **Most re-read:** Files with dependencies (imports, shared utilities)

### The 3 Ping-Pong Archetypes
1. **Code Cross-Reference** (60% of sessions) - `bot.py ↔ retry.py ↔ sheets.py`
2. **Doc-Code Shuttle** (40% of sessions) - `tdd.md ↔ implementation files`
3. **Large File Navigation** (20% of sessions) - Sectional reads of `tdd.md`

### Existing Tools Gap
Compared 6 existing tools (Cursor, Sourcegraph, Code Context MCP, etc.):
- **Highest similarity:** Sourcegraph (75%) - but it's navigation, not context management
- **Average similarity:** 57.5% - significant gap in market
- **Missing:** Proactive context injection (none of the tools have it)

### Proposed Solution
**Cross-File Context Links** - See PRD for full details
- Automatically detect file relationships (imports, calls)
- Cache recently-accessed code snippets
- Proactively inject context when switching files
- **Expected impact:** 60-70% reduction in file re-reads

---

## 🔮 Future Retrospective Perspectives

This directory currently focuses on **Information Retrieval Pattern Analysis**. The other 7 proposed perspectives:

2. **Decision Graph Reconstruction** - Map decision points and information gaps
3. **Context Window Utilization Analysis** - Track context saturation patterns
4. **Error Recovery Path Analysis** - Identify failure modes and recovery costs
5. **Cross-Reference Dependency Mapping** - Document/code interconnectedness
6. **Tool Adequacy Assessment** - Where current tools are insufficient
7. **Temporal Workflow Bottleneck Analysis** - Time spent on different activities
8. **Semantic Coherence Drift Tracking** - Understanding divergence from requirements

---

## 📝 Notes

- This directory is a **proof-of-concept** and not part of the main `reaction_requests` project
- May be moved to a separate repository for Claude Code workflow analysis tooling
- PRD is a **draft** ready for iteration and feedback
