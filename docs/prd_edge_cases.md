# Cross-File Context Links - Edge Cases

This document contains detailed edge case handling referenced in the main PRD (`prd.md`).

## Quick Reference

This document uses identifiers that reference other PRD documents:

- **EC-#**: Edge Case identifiers defined in this document
- **FR-#**: Functional Requirements → See Section 4.1 in [`prd.md`](./prd.md)
- **NFR-#**: Non-Functional Requirements → See Section 4.2 in [`prd.md`](./prd.md)
- **Section #**: Other PRD sections → See [`prd.md`](./prd.md) table of contents

---

## 6. Edge Cases

### 6.1 Relationship Detection Edge Cases

**EC-1: Circular Dependencies (Python)**
- **Scenario:** Python file A imports B, B imports A (creating an import cycle)
- **Python Reality:** Technically allowed but problematic. Can cause ImportError or undefined values at runtime depending on import style:
  - `import module` works (module exists even when empty)
  - `from module import SomeClass` fails (tries to find SomeClass before it exists)
- **Our Tool's Responsibility:** Detect cycles during graph construction without crashing our own tool
- **Handling:**
  - Limit graph traversal depth to prevent infinite loops in our analysis
  - Detect and track bidirectional relationships (A → B and B → A)
  - **MUST warn users** when circular import detected: "⚠️ Circular import detected: A → B → A (Google Python Style Guide 3.19.14: code smell, good candidate for refactoring)"
  - Continue processing other relationships normally
  - Mark files as part of import cycle in relationship graph metadata
- **Value Add:** Most Python tools don't detect circular imports (only pylint with R0401 does). Flake8 and mypy don't check for this. By warning users, we provide value beyond standard tooling.
- **Note:** We're detecting cycles for user awareness, not preventing or fixing them. The user's Python code may still run, we're just surfacing the dependency structure.
- **Future Languages:**
  - v0.3.0 (TypeScript/JavaScript): Will also need circular dependency detection
  - v0.4.0 (Go): Won't need this - Go compiler prevents circular imports entirely

**EC-2: Dynamic Imports**
- **Scenario:** `importlib.import_module(variable_name)` where module name is runtime-determined
- **Handling:** Skip dynamic imports, log as untrackable, rely on static imports only

**EC-3: Aliased Imports**
- **Scenario:** `from retry import retry_with_backoff as retry_func`
- **Handling:** Track original name and alias, match both when detecting usage

**EC-4: Wildcard Imports (Supported with Limitations)**
- **Scenario:** `from utils import *`
- **Style Guide Context:**
  - Google Python Style Guide discourages (Section 2.2)
  - Google's own [pylintrc](https://github.com/google/styleguide/blob/gh-pages/pylintrc) disables wildcard warnings (pragmatic enforcement)
  - Common in real-world codebases, especially test files
- **Handling:**
  - Detect and track relationship at module level: `file.py imports utils.*`
  - Cannot track specific function usage (limitation of wildcard nature)
  - Store in relationship graph as module-level dependency
  - Optional warning via config: `cross_file_context_links.warn_on_wildcards = false` (default)
- **Context Injection:** When editing file with wildcard import, inject: "Note: This file uses `from utils import *`, so specific function tracking is unavailable"
- **Value Add:** Even with limitations, knowing module-level dependencies helps understand file relationships

**EC-5: Conditional Imports**
- **Scenario:** `if TYPE_CHECKING: from typing import ...`
- **Handling:** Track as conditional dependency, include in relationship graph with metadata

**EC-6: Dynamic Dispatch (Unhandled in v0.1.0)**
- **Scenario:** `getattr(obj, func_name)()` where function name is determined at runtime
- **Python Reality:** Common pattern for plugin systems, dynamic method invocation, reflection-based code
- **Handling:**
  - v0.1.0: Cannot statically analyze - function name unknown until runtime
  - System MUST emit warning when detected: "⚠️ Dynamic dispatch detected in {file}:{line} - relationship tracking unavailable for `getattr(obj, '{name}')`"
  - Log as untrackable in relationship graph metadata
  - Do not attempt to guess relationships
- **Test vs. Source Module Distinction:**
  - Suppress warnings in test modules (common pattern in test frameworks)
  - Emit warnings only in source modules where it may indicate trackable alternatives exist
- **Future consideration:** v0.2.0+ could support hints/annotations to manually specify relationships

**EC-7: Monkey Patching (Unhandled in v0.1.0)**
- **Scenario:** `module.function = my_replacement` - runtime replacement of functions
- **Python Reality:** Common in tests for mocking; discouraged in production code
- **Handling:**
  - v0.1.0: Cannot track runtime modifications to module/class attributes
  - System MUST emit warning when detected in source modules: "⚠️ Monkey patching detected in {file}:{line} - `{module}.{attr}` reassigned, relationship tracking may be inaccurate"
  - Do NOT emit warnings in test modules (expected behavior for mocking)
  - Relationship graph tracks original definitions only, not runtime replacements
- **Test vs. Source Module Distinction (Critical):**
  - Test modules (files matching `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`): Suppress monkey patching warnings
  - Source modules: Emit warnings to help developers understand limitations
- **Value Add:** Even though we can't track monkey patching, warning users helps them understand why context injection might miss runtime-modified relationships

**EC-8: Decorators Modifying Behavior (Partially Handled)**
- **Scenario:** `@decorator` that wraps or modifies function behavior
- **Python Reality:** Extremely common pattern (e.g., `@property`, `@staticmethod`, `@lru_cache`, custom decorators)
- **Handling:**
  - v0.1.0: Track decorated function definitions, but cannot analyze decorator logic
  - System tracks: "function X is decorated with Y, Z"
  - Include decorator information in relationship graph metadata
  - If decorator is imported: Track decorator as dependency
  - Emit warning if decorator uses dynamic features: "⚠️ Decorator `{decorator_name}` in {file}:{line} may modify function behavior - tracking original definition only"
- **Test vs. Source Module Distinction:**
  - Common test decorators (e.g., `@pytest.mark`, `@unittest.skip`) - suppress warnings
  - Source module decorators - emit informational warnings for complex decorators

**EC-9: exec() and eval() Usage (Unhandled in v0.1.0)**
- **Scenario:** `exec(code_string)` or `eval(expression_string)` - arbitrary code execution
- **Python Reality:** Rare in modern Python, usually code smell, common in legacy or metaprogramming-heavy code
- **Handling:**
  - v0.1.0: Cannot analyze string-based code execution
  - System MUST emit warning when detected: "⚠️ Dynamic code execution detected in {file}:{line} - `exec()`/`eval()` prevents static analysis, relationships may be incomplete"
  - Mark file as containing dynamic execution in relationship graph metadata
  - Consider increased re-read frequency for files with exec/eval (less trust in cached snippets)
- **Test vs. Source Module Distinction:**
  - Test modules: Suppress warnings (sometimes used in testing edge cases)
  - Source modules: Emit warnings (likely code smell)

**EC-10: Metaclasses (Partially Handled)**
- **Scenario:** Custom `__metaclass__` or class inheritance from `type` that modifies class creation
- **Python Reality:** Advanced pattern, relatively rare, can completely change class behavior
- **Handling:**
  - v0.1.0: Track metaclass usage in relationship graph metadata
  - Track class definition and metaclass reference, but cannot analyze metaclass logic
  - Emit informational warning: "ℹ️ Metaclass detected in {file}:{line} - class `{name}` uses metaclass `{metaclass}`, runtime behavior may differ from static definition"
  - Include metaclass as dependency if imported from another module
- **Test vs. Source Module Distinction:**
  - Generally treat the same (metaclasses rare in both contexts)
  - Can suppress if specific test frameworks use metaclass patterns

### 6.2 Context Injection Edge Cases

**EC-11: Stale Cache After External Edit**
- **Scenario:** User edits file in external editor, cache contains old content
- **Handling:** File watcher detects modification, invalidates cache, forces re-read

**EC-12: Large Functions**
- **Scenario:** Cached function is 200 lines, injection would exceed token limit
- **Handling:** Inject function signature only, provide pointer to full definition

**EC-13: Multiple Definitions**
- **Scenario:** Function `process()` defined in both `utils.py` and `helpers.py`
- **Handling:** Inject both with disambiguation: "process from utils.py:45 or helpers.py:78"

**EC-14: Deleted Files**
- **Scenario:** File B deleted, but relationship graph still references it
- **Handling:** File watcher detects deletion, removes from graph, logs warning

### 6.3 Memory Management Edge Cases

**EC-15: Memory Pressure**
- **Scenario:** Cache grows beyond 50KB limit
- **Handling:** LRU eviction - remove least-recently-used entries first

**EC-16: Long-Running Sessions**
- **Scenario:** 8-hour session with 500+ file accesses
- **Handling:** Implement rolling window - keep only last 2 hours of context

**EC-17: Massive Files**
- **Scenario:** 50,000-line generated file
- **Handling:** Skip indexing files >10,000 lines, log warning, treat as opaque

### 6.4 Failure Mode Edge Cases

**EC-18: Parsing Failure**
- **Scenario:** Syntax error in file prevents AST parsing
- **Handling:** Skip relationship detection for that file, log error, continue with others

**EC-19: Relationship Graph Corruption**
- **Scenario:** Internal data structure becomes inconsistent
- **Handling:** Detect via validation checks, clear graph, rebuild from scratch

**EC-20: Concurrent File Modifications**
- **Scenario:** Multiple processes editing same file simultaneously
- **Handling:** File watcher detects each change, invalidate cache, rely on filesystem consistency

---
