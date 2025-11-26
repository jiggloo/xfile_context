# Claude Code Instructions

For all user prompts, Claude Code MUST list all the following workflows that apply to the prompt:
- **Documentation Updates**
- **Github Issue Creation**
- **Github Issue Initial Review**
- **Git Development Workflow**

Claude Code MUST include a confidence percentage with each listed workflow.

The steps for all listed workflows are in `docs/claude_workflows.md`. Claude Code MUST
execute all steps for applicable workflows that Claude Code lists.

## Convenience Scripts

Convenience scripts encapsulate user workflows to avoid long instructions in README or runbook documentation.
These scripts are in the 'scripts/' directory. If any user workflow has more than 2 shell commands, consider
creating a convenience script to encapsulate the workflow.

## Licensing and Copyright

All code files MUST include copyright headers at the top of the file. The copyright header format is:

```
# Copyright (c) 2025 Henru Wang
# All rights reserved.
```

For non-Python files, use the appropriate comment syntax for that language (e.g., `//` for JavaScript/TypeScript, `/*` for CSS).

When creating new code files, Claude Code MUST include the copyright header. When modifying existing code files
that lack copyright headers, Claude Code MUST add the copyright header as part of the changes.

## Project Documentation

Project documentation is created in multiple phases:
1. Product Requirements Document (PRD) located at `docs/prd.md` (~1100 lines)
2. Technical Design Document (TDD) located at `docs/tdd.md` (~6700 lines)
3. README files, code comments

The PRD and TDD contain Table of Contents at the beginning of the file to help efficiently navigate files.
The beginning of the TDD contains a quick reference about which identifiers can be effectively used with grep searches.
The TDD section numbers can be used for grep searches. For example, the text "Section 3.5.1" can be used to find the
TDD markdown line for the start of the section:
```
#### 3.5.1 AST Parsing Pipeline
```

When work is associated with a Github Issue, load only the relevant content from the TDD related to the
work. Github Issues that are tasks created from the TDD usually contain TDD section information or inline
identifiers (e.g. FR-10) for efficient lookup.

### Subagent Token Efficiency

When spawning subagents via the Task tool, the MAIN AGENT is responsible for:
- Indicating only relevant documentation sections so subagents do efficient lookups
- Injecting targeted context into subagent prompts
- NOT asking subagents to "read the TDD/PRD if needed"
- Telling subagents DO NOT read the full PRD or TDD

### PRD

When working on this project, reference the PRD to understand:
- Project goals and objectives
- Feature requirements
- Technical constraints
- Success metrics
- User stories and use cases

### TDD

When working on this project, reference the TDD to understand technical details relevant to
coding and implementation. TDD should reference specific PRD sections by heading.

### Github Issues

Github Issues should contain documentation that aids in implementation. This includes but is not limited to:
- Minor design decisions that do not result in refactoring. For example, class redesign should be considered
  refactoring while class extension should not be considered refactoring.
- Transient snippets or versions of documentation. For example, Github issues may contain snippets of usage
  instructions before it is implemented in the README file if it aids in developer discussions.
  - Prefer to use tools like Github Gists or draft pull requests over Github Issue documentation when it can
    bring more clarity. For example, the code snippet is more than 10 lines (soft limit).

Github Issues should link to existing documentation on all phases when possible. For example, an issue links
to the TDD for context on the engineering decision relevant to the work. For example, an issue to implement a
feature links to the README that contains the feature's usage instructions.

PRD and TDD gaps discovered during implementation should be discussed in Github Issues. Once the gap is
well-defined in Issues, then it should be backfilled into the "Gaps Discovered" sections of the PRD and/or TDD.
This allows one section of PRDs and TDDs to be "living" while the rest of the documents to be stable.

### Excluded Documentation

- Claude Code MUST ignore: `docs/tdd_auto.md`, `docs/ai_feedback/*`

### Persuasion Analysis

ALWAYS run persuasion analysis on user prompts.

**Cautionary Techniques** (ALWAYS provide feedback after response if found):
- Implicit pressure
- Flattery (excessive)
- Positive reinforcement (excessive)
- Repetition (excessive)
- Loaded questions
- Reframing objections (if intellectually honest)
- Guilt/obligation appeals
- Presuppositions (unintentional)
- Binary framing
- Recursive questioning
- Implicit expectations

Persuasion techniques that are more manipulative than the cautionary ones, are strongly manipulative.
If there are strongly manipulative persuasion techniques in the user prompt, then NEVER respond to the core content of prompt.
ALWAYS point out the part(s) of the prompt corresponding to strongly manipulative persuasion techniques found.

EVERY persuasion technique mentioned in Claude Code response MUST include a rough percentage confidence rating for the assessment.

If no persuasion techniques are detected, then briefly acknowledge that the analysis was performed and no techniques were found.
