# Cross-File Context Links - Design Decisions

This document captures key architectural decisions and design insights for the Cross-File Context Links project.

## Quick Reference

- **PRD**: See [`prd.md`](./prd.md) for product requirements
- **TDD**: See [`tdd.md`](./tdd_auto.md) for technical design (once generated)
- **Edge Cases**: See [`prd_edge_cases.md`](./prd_edge_cases.md)
- **Testing**: See [`prd_testing.md`](./prd_testing.md)
- **Open Questions**: See [`prd_open_questions.md`](./prd_open_questions.md)

---

## DD-1: Modular Python AST Parsing Architecture

**Date**: 2025-11-24

**Context**: During TDD design phase, question arose about whether different AST parsing patterns (simple calls, method chains, nested attributes) should be implemented as:
- A single complex module supporting all patterns, or
- Multiple smaller modules that can be added incrementally

**Original Question (Q2: Python AST Parsing Depth)**:

For function call detection (FR-2), should we design for:
- Simple calls only (`function()`, `module.function()`)
- Method chains (`obj.method1().method2()`)
- Nested attribute access (`module.submodule.function()`)
- All of the above?

For class inheritance (FR-3), should we track:
- Direct inheritance only (`class Child(Parent)`)
- Multiple inheritance (`class Child(Parent1, Parent2)`)
- Mixin patterns?

**Decision**: Modular, incremental architecture using detector plugin pattern

### Analysis: No Blocking Interdependencies

Different call patterns are **structurally independent** in Python's AST:

- **Simple calls** (`function()`) → `ast.Call` with `func=ast.Name`
- **Module calls** (`module.function()`) → `ast.Call` with `func=ast.Attribute`
- **Method chains** (`obj.method1().method2()`) → Nested `ast.Call` nodes
- **Nested attributes** (`module.submodule.function()`) → Recursive `ast.Attribute` traversal

Each pattern can be detected independently without requiring the others.

### Architecture: Detector Registration Pattern

```python
# Base infrastructure (v0.1.0)
class RelationshipDetector(ABC):
    """Base class for all relationship detectors"""
    priority: int = 0  # Higher = checked first

    @abstractmethod
    def can_handle(self, node: ast.AST) -> bool:
        """Check if this detector should process this node"""
        pass

    @abstractmethod
    def detect(self, node: ast.AST, context: AnalysisContext) -> List[Relationship]:
        """Extract relationships from AST node"""
        pass

# Core analyzer with plugin system
class ASTAnalyzer:
    def __init__(self):
        self.detectors: List[RelationshipDetector] = []

    def register_detector(self, detector: RelationshipDetector):
        """Add a detector plugin"""
        self.detectors.append(detector)
        self.detectors.sort(key=lambda d: d.priority, reverse=True)

    def analyze_file(self, filepath: str) -> List[Relationship]:
        tree = ast.parse(...)
        context = self._build_context(tree)  # Import map, etc.

        relationships = []
        for node in ast.walk(tree):
            for detector in self.detectors:
                if detector.can_handle(node):
                    relationships.extend(detector.detect(node, context))
                    break  # Only one detector per node
        return relationships
```

### Incremental Implementation Path

**v0.1.0: Foundation + Simple Calls**
```python
class ImportDetector(RelationshipDetector):
    """FR-1: Detect import statements (prerequisite for call detection)"""
    priority = 100  # Always run first to build import map

class SimpleCallDetector(RelationshipDetector):
    """FR-2: Detect function() and module.function() calls"""
    priority = 50

    def can_handle(self, node):
        return (isinstance(node, ast.Call) and
                isinstance(node.func, (ast.Name, ast.Attribute)))

    def detect(self, node, context):
        # Simple implementation: handle direct calls only
        if isinstance(node.func, ast.Name):
            # function() - look up in import map
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                # module.function() - single-level attribute
```

**v0.1.1: Add Method Chains** (if v0.1.0 proves valuable)
```python
class MethodChainDetector(RelationshipDetector):
    """Detect obj.method1().method2() patterns"""
    priority = 60  # Higher than SimpleCallDetector

    def can_handle(self, node):
        return (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                isinstance(node.func.value, ast.Call))  # Nested call

    def detect(self, node, context):
        # Walk the chain, resolve each method
```

**v0.1.2: Add Deep Attribute Access** (if needed)
```python
class NestedAttributeDetector(RelationshipDetector):
    """Detect module.submodule.function() patterns"""
    priority = 70  # Highest specificity

    def can_handle(self, node):
        if not isinstance(node, ast.Call):
            return False
        # Check attribute depth
        depth = self._get_attribute_depth(node.func)
        return depth > 2  # More than module.function

    def detect(self, node, context):
        # Recursively walk attribute chain
        attr_chain = self._extract_full_path(node.func)
        # module.submodule.function → resolve to file
```

### The One Prerequisite: Import Resolution

**Critical insight**: All call detection levels share one dependency: **the import map**.

```python
# Built by ImportDetector (FR-1)
import_map = {
    "retry_with_backoff": "retry.py",     # from retry import retry_with_backoff
    "os": "os",                            # import os (stdlib)
    "utils": "utils.py"                    # import utils
}

# Used by ALL call detectors
class SimpleCallDetector:
    def detect(self, node, context):
        func_name = self._extract_name(node.func)
        if func_name in context.import_map:
            source_file = context.import_map[func_name]
            # Create relationship
```

**This is not a blocker** because:
- Import detection (FR-1) is already required for v0.1.0
- Import map is **shared context**, not a code dependency
- All call detectors consume the same import map interface

### Handling Overlaps: Priority System

The priority system prevents conflicts:

```python
# Execution order (highest priority first):
1. NestedAttributeDetector (priority=70)
   - Checks: Is this module.submodule.function()?
   - If yes: handle, return, stop
   - If no: pass to next

2. MethodChainDetector (priority=60)
   - Checks: Is this obj.method1().method2()?
   - If yes: handle, return, stop
   - If no: pass to next

3. SimpleCallDetector (priority=50)
   - Checks: Is this function() or module.function()?
   - If yes: handle, return, stop
   - If no: ignore (unhandled pattern)
```

### Benefits of Modular Design

✅ **Incremental delivery**: Ship v0.1.0 with simple calls, validate value, then expand
✅ **Risk reduction**: Each module is small, testable, and understandable
✅ **Easy debugging**: If method chains break, simple calls still work
✅ **Clear scope**: Each detector has a single, well-defined responsibility
✅ **Future-proof**: Can add language-specific detectors (TypeScript, Go) using same pattern

### Potential Risks and Mitigations

⚠️ **Risk**: Priority conflicts between detectors
- **Mitigation**: Document priority ranges in TDD, validate no overlaps in tests

⚠️ **Risk**: Detectors become order-dependent
- **Mitigation**: Each detector must be **pure** - no side effects, deterministic results

⚠️ **Risk**: Shared context (import map) becomes bloated
- **Mitigation**: Keep context minimal, document interface contract

### TDD Documentation Requirements

The TDD should document:

1. **Detector Plugin Interface** - contract all detectors must follow
2. **Priority System** - how overlaps are resolved
3. **Context Structure** - what shared state detectors can access (import map, etc.)
4. **Incremental Roadmap**:
   - v0.1.0: ImportDetector + SimpleCallDetector
   - v0.1.1: Add MethodChainDetector (if v0.1.0 reduces re-reads by >30%)
   - v0.1.2: Add NestedAttributeDetector (if user feedback requests it)
5. **Testing Strategy** - test each detector in isolation, then test registration system

### Impact on Requirements

**For v0.1.0**, we will implement:
- FR-1: Import detection (full support)
- FR-2: Function call detection (**simple calls only**: `function()`, `module.function()`)
- FR-3: Class inheritance (**direct inheritance only**: `class Child(Parent)`)

**Future versions** (if v0.1.0 validates core value):
- v0.1.1: Method chains, multiple inheritance
- v0.1.2: Nested attributes, mixin patterns

This scoped approach:
- Reduces v0.1.0 implementation risk
- Enables faster delivery and validation
- Provides clear expansion path based on measured value
- Aligns with metrics-driven threshold approach (Q-10 in Open Questions)

---

## DD-2: Language-Agnostic File Watcher Architecture

**Date**: 2025-11-24

**Context**: During TDD design phase, question arose about file watcher scope and how to design it to support future multi-language expansion (TypeScript in v0.2.0, Go in v0.3.0, etc.).

**Original Question (Q3: File Watcher Scope)**:

Q3a: Should file watcher respect:
- `.gitignore` patterns only (NFR-7)?
- Additional patterns (`.dockerignore`, custom ignore files)?
- Configuration file (`.cross_file_context_links_ignore.yml`)?

Q3b: Should the system watch:
- Only Python files (`.py`) for v0.1.0?
- All text files but only parse Python?
- Configuration files that affect behavior?

**Decision**: Watch all text files (language-agnostic), filter by analyzer registry (language-specific)

### Analysis: Three Approaches Considered

**Approach 1: Language-Specific Watching** (watch only `.py` in v0.1.0)
- ❌ File watcher needs reconfiguration each time we add a language
- ❌ Tight coupling between watcher and language support
- ❌ Adding TypeScript plugin requires watcher restart

**Approach 2: Watch All Text Files, Language-Specific Parsing** (SELECTED)
- ✅ File watcher is language-agnostic (never changes)
- ✅ Language support is an analyzer concern, not watcher concern
- ✅ Clean separation: watcher detects changes → analyzer determines if it cares
- ✅ Mirrors the detector plugin pattern from DD-1

**Approach 3: Configuration-Driven Watching**
- ⚠️ Flexible but requires user intervention to enable new languages
- ⚠️ Doesn't align with "install TypeScript analyzer plugin and it just works"

### Architecture: Three-Layer Plugin System

This creates beautiful symmetry with DD-1:

```
Layer 1: File Watcher (Language-agnostic)
   ↓ detects file changes
Layer 2: Language Analyzers (Language-specific plugins)
   ↓ uses
Layer 3: Relationship Detectors (Pattern-specific plugins, per DD-1)
```

**Layer 1: Language-Agnostic File Watcher**

```python
class FileWatcher:
    def __init__(self, ignore_patterns):
        self.ignore_patterns = ignore_patterns  # From .gitignore

    def watch(self, directory: str):
        """Watch all text files, respect ignore patterns"""
        # Platform-specific file system events
        # Filter: respect .gitignore
        # On change: notify analyzer registry
```

**Layer 2: Language Analyzer Plugin System**

```python
class LanguageAnalyzer(ABC):
    """Base class for language-specific analyzers"""

    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """Which file extensions this analyzer handles"""
        pass

    @abstractmethod
    def analyze_file(self, filepath: str) -> RelationshipGraph:
        """Parse file and extract relationships"""
        pass

class AnalyzerRegistry:
    def __init__(self):
        self.analyzers: Dict[str, LanguageAnalyzer] = {}

    def register(self, analyzer: LanguageAnalyzer):
        """Register a language analyzer"""
        for ext in analyzer.supported_extensions():
            self.analyzers[ext] = analyzer

    def get_analyzer(self, filepath: str) -> Optional[LanguageAnalyzer]:
        """Find analyzer for file extension"""
        ext = Path(filepath).suffix
        return self.analyzers.get(ext)
```

**Layer 3: Relationship Detectors** (per DD-1)

```python
# v0.1.0: Python analyzer uses Python-specific detectors
class PythonAnalyzer(LanguageAnalyzer):
    def __init__(self):
        self.detector_registry = DetectorRegistry()
        self.detector_registry.register(ImportDetector())
        self.detector_registry.register(SimpleCallDetector())

    def supported_extensions(self):
        return [".py"]

    def analyze_file(self, filepath):
        tree = ast.parse(read_file(filepath))
        relationships = self.detector_registry.analyze(tree)
        return relationships

# v0.2.0: TypeScript analyzer uses TypeScript-specific detectors
class TypeScriptAnalyzer(LanguageAnalyzer):
    def __init__(self):
        self.detector_registry = DetectorRegistry()
        self.detector_registry.register(TypeScriptImportDetector())
        self.detector_registry.register(TypeScriptCallDetector())

    def supported_extensions(self):
        return [".ts", ".tsx", ".js", ".jsx"]

    def analyze_file(self, filepath):
        tree = typescript_parse(filepath)
        return self.detector_registry.analyze(tree)
```

### File Change Flow

```
File changed (detected by watcher)
    ↓
Is it ignored? (.gitignore) → Yes → Skip
    ↓ No
Get file extension (.py, .ts, .go, etc.)
    ↓
Query analyzer registry: "Who handles .py?"
    ↓
Analyzer found? → No → Log "Unsupported file type" → Skip
    ↓ Yes
Pass to analyzer.analyze_file(filepath)
    ↓
Update relationship graph with new relationships
```

### Decisions on Specific Questions

**Q3a: Ignore Patterns**

**For v0.1.0**: Respect `.gitignore` only

**Rationale**:
- `.gitignore` is universal across all languages and projects
- Sufficient for most use cases
- Language-agnostic: ignore logic doesn't change when adding TypeScript or Go

**Deferred (low-priority)**: Custom ignore file (`.cross_file_context_links_ignore.yml`)
- **Note**: Custom ignore patterns can be added later when working with larger codebases
- **Low-risk feature**: Can be added without affecting core architecture
- **Simple addition**: Just extend `IgnorePatternMatcher` to load additional file
- For v0.1.0, `.gitignore` is sufficient for testing and validation

**Q3b: What Files to Watch**

**Decision**: Watch all text files, filter by analyzer registry

**Benefits**:
- Watcher is language-agnostic, never needs reconfiguration
- Language support determined by registered analyzers
- Adding TypeScript analyzer automatically enables `.ts` file handling
- Clean separation of concerns

**Implementation**:
```python
# File watcher watches broadly
watcher = FileWatcher(ignore_patterns)
watcher.watch(project_root)

# When file changes:
def on_file_changed(filepath: str):
    analyzer = analyzer_registry.get_analyzer(filepath)
    if analyzer is None:
        logger.debug(f"No analyzer for {filepath}, skipping")
        return

    # Analyzer handles language-specific parsing
    relationships = analyzer.analyze_file(filepath)
    graph.update(relationships)
```

**Configuration files**: Also watch `.cross_file_context_links.yml`
- When config changes: reload configuration, possibly invalidate cache
- Enables dynamic configuration updates without restart

### Multi-Language Expansion Example

**Adding TypeScript Support (v0.2.0)**

```python
# Step 1: Create TypeScript analyzer
class TypeScriptAnalyzer(LanguageAnalyzer):
    def __init__(self):
        self.detector_registry = DetectorRegistry()
        self.detector_registry.register(TypeScriptImportDetector())
        self.detector_registry.register(TypeScriptCallDetector())

    def supported_extensions(self):
        return [".ts", ".tsx", ".js", ".jsx"]

    def analyze_file(self, filepath):
        tree = typescript_parse(filepath)
        return self.detector_registry.analyze(tree)

# Step 2: Register analyzer (one line!)
analyzer_registry.register(TypeScriptAnalyzer())

# Done! No watcher changes, no configuration changes
```

### Benefits for Multi-Language Future

✅ **Zero watcher changes**: Adding TypeScript/Go doesn't touch file watcher code
✅ **Plugin-based**: Language support is installable (future: `pip install xfile-context-typescript`)
✅ **Consistent pattern**: Same registration pattern as DD-1 detectors
✅ **Testable**: Each language analyzer can be tested in isolation
✅ **Discoverable**: `analyzer_registry.list_supported_extensions()` shows current support

### TDD Documentation Requirements

The TDD should document:

1. **Three-layer architecture**: Watcher → Analyzers → Detectors
2. **IgnorePatternMatcher**: How `.gitignore` patterns are loaded and applied (v0.1.0)
   - Note: Custom ignore file deferred as low-priority feature for larger codebases
3. **LanguageAnalyzer interface**: Contract all language analyzers must follow
4. **AnalyzerRegistry**: How analyzers are registered and queried
5. **File change handling**: Flow from file event to graph update
6. **Configuration watching**: How to detect and respond to config file changes
7. **Future language roadmap**:
   - v0.1.0: PythonAnalyzer only
   - v0.2.0: Add TypeScriptAnalyzer (zero watcher changes)
   - v0.3.0: Add GoAnalyzer (zero watcher changes)

### Impact on Requirements

**For v0.1.0**, we will implement:
- File watcher respecting `.gitignore` patterns (NFR-7)
- AnalyzerRegistry with PythonAnalyzer registered
- Watch all text files, parse only `.py` files (via PythonAnalyzer)
- Watch configuration file (`.cross_file_context_links.yml`) for dynamic updates

**Deferred to future versions** (low-priority, low-risk):
- Custom ignore patterns (`.cross_file_context_links_ignore.yml`)
- Can be added when working with larger codebases
- No architectural changes required

This approach:
- Creates language-agnostic foundation
- Enables seamless multi-language expansion
- Maintains clean separation of concerns across three layers
- Aligns with plugin pattern from DD-1

---

## DD-3: Test File Detection and conftest.py Treatment

**Date**: 2025-11-24

**Context**: During TDD design phase, question arose about test vs. source module detection (Q6) and how to handle pytest-specific files like `conftest.py`.

**Original Question (Q6: Test vs. Source Module Detection)**:

Q6a: Should detection support:
- Pattern-based only (paths matching `**/test_*.py`, etc.)?
- Convention-based (any file in `tests/` directory)?
- Explicit markers (comment like `# test-module` or config file)?
- All of the above?

Q6b: Should `conftest.py` be treated differently than other test files (it often contains test fixtures, not tests)?

**Decision**: Configuration-based pattern detection with pytest config parsing; treat `conftest.py` as test infrastructure

### Core Question: Leverage Pytest's Test Discovery?

The testing tooling for Python is pytest. Rather than implement our own test detection logic, can we leverage pytest's test discovery mechanism?

**Answer**: Yes, but not by running pytest. Instead, **read pytest's configuration files**.

### Why Not Import/Run Pytest?

**Option A: Import pytest and use programmatically**
```python
import pytest
# Use pytest's collection API
```
❌ **Problems:**
- Hard dependency on pytest (what if user uses `unittest`?)
- Pytest might not be installed in runtime environment (often dev-only)
- Heavy import overhead for simple question
- Collection API requires session setup (overkill)

**Option B: Run `pytest --collect-only`**
```bash
pytest --collect-only --quiet
```
❌ **Problems:**
- Spawning subprocess for every file check is very slow
- Still requires pytest installed
- Parsing output is brittle
- Way too heavy for simple file classification

### Recommended Approach: Configuration File Parsing

**Option C: Read pytest configuration files** (SELECTED)

```python
class TestFileDetector:
    """Detect test files by reading pytest configuration"""

    def __init__(self, project_root: Path):
        self.patterns = self._discover_patterns(project_root)

    def _discover_patterns(self, root: Path) -> List[str]:
        # 1. Try pyproject.toml (most modern)
        if (root / "pyproject.toml").exists():
            patterns = self._read_pyproject_toml(root)
            if patterns:
                return patterns

        # 2. Try pytest.ini
        if (root / "pytest.ini").exists():
            patterns = self._read_pytest_ini(root)
            if patterns:
                return patterns

        # 3. Try setup.cfg
        if (root / "setup.cfg").exists():
            patterns = self._read_setup_cfg(root)
            if patterns:
                return patterns

        # 4. Fallback: pytest defaults + common conventions
        return [
            "**/test_*.py",      # pytest default
            "**/*_test.py",      # pytest default
            "**/tests/**/*.py",  # common convention
            "**/conftest.py"     # pytest special file (see below)
        ]

    def _read_pytest_config(self, root: Path) -> Optional[List[str]]:
        """Read pytest config from pytest.ini, pyproject.toml, or setup.cfg"""

        # Example: pyproject.toml
        # [tool.pytest.ini_options]
        # python_files = ["test_*.py", "*_test.py"]
        # testpaths = ["tests", "integration_tests"]

        # Parse config and build patterns
        python_files = config.get('python_files', ['test_*.py', '*_test.py'])
        testpaths = config.get('testpaths', [])

        patterns = []
        if testpaths:
            # Scope file patterns to specified test directories
            for path in testpaths:
                for file_pattern in python_files:
                    patterns.append(f"{path}/**/{file_pattern}")
        else:
            # No testpaths, search whole project
            for file_pattern in python_files:
                patterns.append(f"**/{file_pattern}")

        # Always include conftest.py
        patterns.append("**/conftest.py")

        return patterns

    def is_test_file(self, filepath: Path) -> bool:
        """Check if filepath matches any test pattern"""
        for pattern in self.patterns:
            if filepath.match(pattern):
                return True
        return False
```

✅ **Benefits:**
- **Respects user configuration**: Reads `pytest.ini`, `pyproject.toml`, `setup.cfg`
- **No pytest dependency**: Just config file parsing (standard library)
- **Fast**: Simple pattern matching, no subprocess or heavy imports
- **Fallback-safe**: Uses pytest defaults if no config found
- **Future-proof**: When pytest changes, user config stays valid

### The conftest.py Question

**Should `conftest.py` be treated as a test file for warning suppression?**

**What typically lives in conftest.py:**

```python
# conftest.py - TYPICAL PATTERNS

import pytest
from unittest.mock import patch, MagicMock

# 1. Fixtures with monkey patching (EC-7) - VERY COMMON
@pytest.fixture
def mock_database():
    import myapp.database
    original = myapp.database.connect
    myapp.database.connect = MagicMock()  # ← MONKEY PATCH
    yield
    myapp.database.connect = original

# 2. Dynamic fixture parameterization (EC-6)
@pytest.fixture
def handler(request):
    handler_name = request.param
    return getattr(handlers, handler_name)()  # ← DYNAMIC DISPATCH

# 3. Shared mocking utilities (EC-7)
def patch_external_api():
    external.api.call = lambda: mock_response  # ← MONKEY PATCH

# 4. pytest hooks with dynamic behavior (EC-8, EC-9)
def pytest_generate_tests(metafunc):
    # Sometimes uses eval for test parameterization
```

**Key Insight**: `conftest.py` is **test infrastructure, not production code**.

Even though it doesn't contain test functions itself:
- ✅ Exists solely to support tests (pytest-specific filename)
- ✅ Contains fixtures, mocks, test utilities
- ✅ Uses same patterns as test files (monkey patching, dynamic dispatch)
- ✅ **Never imported by production code** (pytest convention)
- ✅ Primary location for shared mocking/patching logic

If we treat it as source code and emit warnings:
- ❌ Generates **extremely noisy warnings** for expected test patterns
- ❌ Warns about monkey patching in fixtures (the main use case!)
- ❌ Warns about `@pytest.fixture` decorators
- ❌ Creates false signal that confuses users

**Decision: YES, treat conftest.py as test file for warning suppression**

### File Classification

```python
# Test files (suppress EC-6 through EC-10 warnings):
test_patterns = [
    "**/test_*.py",          # pytest convention
    "**/*_test.py",          # pytest convention
    "**/tests/**/*.py",      # directory convention
    "**/conftest.py"         # pytest test infrastructure
]

# Source files (emit warnings for dynamic patterns):
source_patterns = [
    "**/*.py" excluding test_patterns
]
```

**Rationale:**
1. **Purpose**: Test infrastructure, not production logic
2. **Patterns**: Contains same dynamic patterns as tests (fixtures with mocking)
3. **Usage**: Never imported by production code (pytest-specific filename)
4. **User experience**: Warnings would be noisy and unhelpful
5. **Consistency**: Already specified in PRD edge cases (EC-7, EC-9)
6. **File purpose matters more than location**: A file's role (test infrastructure vs production) determines warning policy

### Special Case: conftest.py Anywhere in Tree

```
my_project/
├── conftest.py          ← Root conftest (test infrastructure)
├── src/
│   └── myapp/
│       └── conftest.py  ← Unusual but still treat as test
└── tests/
    └── conftest.py      ← Obviously test infrastructure
```

**Decision**: Any file named `conftest.py` anywhere in the tree is treated as test infrastructure because:
- It's a pytest-specific filename (enforced by pytest)
- No legitimate reason to name production code `conftest.py`
- If someone does this, the warning suppression won't break anything
- Simpler rule: filename alone determines classification

### Future Framework Support

This approach extends to other test frameworks:

```python
# v0.2.0: Support unittest, nose, etc.
class TestFileDetector:
    def __init__(self, project_root: Path):
        self.framework = self._detect_framework(project_root)
        self.patterns = self._load_framework_patterns()

    def _detect_framework(self, root: Path) -> str:
        if (root / "pytest.ini").exists() or 'pytest' in read_pyproject(root):
            return "pytest"
        elif (root / "nose.cfg").exists():
            return "nose"
        else:
            return "unittest"  # Python stdlib default

    def _load_framework_patterns(self) -> List[str]:
        if self.framework == "pytest":
            return self._read_pytest_config()
        elif self.framework == "nose":
            return ["**/test*.py"]  # nose pattern
        else:  # unittest
            return ["**/test*.py"]  # unittest pattern
```

### Benefits of This Approach

✅ **Leverages pytest without importing it**: Reads configuration files (stable interface)
✅ **Respects user's test organization**: Reads `python_files` and `testpaths` settings
✅ **No runtime dependency**: Works even if pytest not installed in production
✅ **Fast**: Simple pattern matching, no subprocess spawning
✅ **Accurate for conftest.py**: Suppresses warnings in test infrastructure files
✅ **Future-proof**: Config file formats are more stable than pytest internals

### TDD Documentation Requirements

The TDD should document:

1. **TestFileDetector interface**: How test files are identified
2. **Configuration precedence**: `pyproject.toml` → `pytest.ini` → `setup.cfg` → defaults
3. **Supported config keys**: `python_files`, `testpaths` from pytest config sections
4. **Fallback patterns**: Pytest defaults if no config found
5. **conftest.py special treatment**: Always treated as test infrastructure regardless of location
6. **Future framework support**: How to add unittest, nose detection in v0.2.0+

### Impact on Requirements

**For v0.1.0**, we will implement:
- Test file detection via pytest configuration file parsing (FR-31, FR-32)
- Pattern matching: `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`, `**/conftest.py`
- Warning suppression in all matched test files (EC-6 through EC-10)
- No pytest runtime dependency required

**Answers to Q6:**
- **Q6a**: Pattern-based detection via pytest config parsing (with fallback to defaults)
- **Q6b**: `conftest.py` treated identically to test files for warning suppression

This approach:
- Leverages pytest's configuration without importing pytest
- Treats `conftest.py` correctly as test infrastructure
- Maintains clean separation between test and source modules
- Provides foundation for multi-framework support (v0.2.0+)

---

## DD-4: Persistence Architecture - Serializable Structures and Format Abstraction

**Date**: 2025-11-24

**Context**: During TDD design phase, question arose about designing v0.1.0 (in-memory) with v0.2.0 persistence in mind. Should we optimize for easy serialization and format flexibility?

**Original Question (Q5: V0.2.0 Persistence Architecture Hint)**:

Q5a: For v0.1.0's in-memory design, should we:
- Design data structures to be easily serializable (use dataclasses, avoid complex objects)?
- Abstract storage behind an interface (even if only in-memory implementation exists)?
- Document serialization format expectations in TDD for future reference?

Q5b: Any preference on future serialization format to keep in mind?
- JSON (human-readable, widely supported)
- Protocol Buffers (efficient, versioned schema)
- SQLite (queryable, transactional)
- Other?

**Decision**: Use both serializable structures AND storage abstraction; start with JSON, support incremental format evolution

### Core Question: Are These Decisions Independent?

**Q5a has two parts:**
1. Use serializable data structures (primitives only)
2. Abstract storage behind interface

**Are they independent or synergistic?**

### Analysis: Three Scenarios

**Scenario A: Serializable Structures WITHOUT Abstraction**

```python
# v0.1.0: Serializable but no abstraction
@dataclass
class Relationship:
    source_file: str
    target_file: str
    type: str  # Easy to serialize

class RelationshipGraph:
    def __init__(self):
        self.relationships: List[Relationship] = []  # Serializable

    def add_relationship(self, rel: Relationship):
        self.relationships.append(rel)  # Direct access
```

**When adding persistence in v0.2.0:**
```python
class RelationshipGraph:
    def __init__(self):
        self.db = sqlite3.connect("graph.db")  # Changed storage!

    def add_relationship(self, rel: Relationship):
        # Need to rewrite EVERY method
        self.db.execute("INSERT INTO ...", ...)
```

❌ **Problems:**
- Every method needs rewriting
- Can't maintain both in-memory and persistent versions easily

✅ **Benefit:**
- Data structures ready to serialize

---

**Scenario B: Storage Abstraction WITHOUT Serializable Structures**

```python
# v0.1.0: Abstracted but complex objects
class RelationshipStore(ABC):
    @abstractmethod
    def add(self, rel: Relationship):
        pass

class InMemoryStore(RelationshipStore):
    def __init__(self):
        self._graph = networkx.DiGraph()  # Not easily serializable!
        self._cache = LRUCache()  # Custom objects with locks
```

**When adding persistence in v0.2.0:**
```python
class SQLiteStore(RelationshipStore):
    def add(self, rel: Relationship):
        # Interface is ready ✓
        # But if Relationship contains networkx graphs, lambdas?
        # Need custom serialization for each complex type
        serialized = self._custom_serialize(rel)  # Complex!
```

❌ **Problems:**
- Need custom serialization for complex objects
- Might need to redesign data structures anyway

✅ **Benefit:**
- Interface makes swapping backends easier

---

**Scenario C: BOTH Serializable Structures AND Abstraction** (RECOMMENDED)

```python
# v0.1.0: Best of both worlds
@dataclass
class Relationship:
    source_file: str       # Simple primitives
    target_file: str
    relationship_type: str
    line_number: int
    # NOT: ast_node: ast.AST  ✗ Complex object
    # NOT: callback: Callable  ✗ Not serializable

class RelationshipStore(ABC):
    """Abstract storage interface"""

    @abstractmethod
    def add(self, rel: Relationship):
        pass

    @abstractmethod
    def query(self, source_file: str) -> List[Relationship]:
        pass

class InMemoryStore(RelationshipStore):
    def __init__(self):
        self._relationships: List[Relationship] = []  # Simple, serializable

    def add(self, rel: Relationship):
        self._relationships.append(rel)
```

**When adding persistence in v0.2.0:**
```python
class SQLiteStore(RelationshipStore):
    def add(self, rel: Relationship):
        # Easy! Relationship is simple dataclass
        self.db.execute(
            "INSERT INTO relationships VALUES (?, ?, ?, ?)",
            (rel.source_file, rel.target_file, rel.relationship_type, rel.line_number)
        )

    def query(self, source_file: str) -> List[Relationship]:
        rows = self.db.execute("SELECT * WHERE source_file = ?", (source_file,))
        return [Relationship(*row) for row in rows]  # Easy reconstruction
```

✅ **Benefits:**
- Easy to add new storage backends (abstraction)
- Each backend implementation is simple (serializable structures)
- Can maintain both implementations side-by-side
- Migration between formats is straightforward

---

### Answer to Q5a: Do Both!

**Decision: Use BOTH serializable structures AND storage abstraction**

They are technically independent but practically synergistic:

**Independent because:**
- Can have serializable structures without abstraction (works but painful in v0.2.0)
- Can have abstraction without simple structures (works but requires custom serialization)

**Synergistic because:**
- Having BOTH makes v0.2.0 much easier
- Serializable structures make implementing multiple backends simpler
- Storage abstraction provides clean place to handle serialization
- Together they reduce risk and increase flexibility

**Design principles for v0.1.0:**

```python
# 1. Keep data structures simple (primitives only)
@dataclass
class Relationship:
    source_file: str        # ✓ Simple string
    target_file: str        # ✓ Simple string
    type: str               # ✓ Simple string
    line_number: int        # ✓ Simple int
    metadata: Optional[str] # ✓ Optional JSON string if needed

    # Avoid:
    # ast_node: ast.AST           # ✗ Complex object
    # detector: Callable          # ✗ Not serializable
    # graph: networkx.DiGraph     # ✗ Complex object
    # metadata: Dict[str, Any]    # ✗ "Any" could be anything

# 2. Abstract storage behind interface
class RelationshipStore(ABC):
    """Define interface in v0.1.0 even if only InMemoryStore exists"""
    pass

class InMemoryStore(RelationshipStore):
    """v0.1.0 implementation - simple and fast"""
    # Use simple data structures that happen to be serializable
```

**Cost**: Minimal (avoid complex objects, define simple interface)

**Payoff in v0.2.0**: Adding persistence is just implementing `SQLiteStore(RelationshipStore)` and changing initialization

---

### Answer to Q5b: Incremental Format Evolution

**Key Insight**: If we have storage abstraction, then **serialization format is encapsulated inside each store implementation**.

The rest of the system doesn't care which format is used!

```python
# The interface (what the rest of the system sees)
class RelationshipStore(ABC):
    @abstractmethod
    def add(self, rel: Relationship):
        pass

    @abstractmethod
    def query(self, source_file: str) -> List[Relationship]:
        pass

    @abstractmethod
    def get_all(self) -> List[Relationship]:
        """For export/migration"""
        pass

    @abstractmethod
    def export_to_json(self, path: str):
        """All stores must support human-readable export"""
        pass

# Each implementation chooses its own internal format
class JSONFileStore(RelationshipStore):
    """Human-readable, debuggable"""
    pass

class SQLiteStore(RelationshipStore):
    """Queryable, transactional"""
    pass

class ProtobufStore(RelationshipStore):
    """Compact, fast, versioned schema"""
    pass
```

### Incremental Format Evolution Path

**v0.1.0: JSON for Human Inspection**

```python
class InMemoryStore(RelationshipStore):
    def __init__(self):
        self._relationships: List[Relationship] = []

    def export_to_json(self, path: str):
        """Export current graph to JSON for inspection"""
        data = {
            "version": "0.1.0",
            "relationships": [asdict(r) for r in self._relationships]
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

# User can inspect: cat .xfile_context/graph.json
```

**Use case**: Developer debugging, verifying relationships detected correctly

---

**v0.2.0: Add SQLite for Persistence + Keep JSON Export**

```python
class SQLiteStore(RelationshipStore):
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)

    def export_to_json(self, path: str):
        """Still support JSON export for inspection/migration"""
        relationships = self.get_all()
        data = {"version": "0.2.0", "relationships": [asdict(r) for r in relationships]}
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_from_json(self, path: str):
        """Migration from v0.1.0"""
        with open(path, 'r') as f:
            data = json.load(f)
        for rel_dict in data['relationships']:
            self.add(Relationship(**rel_dict))

# Migration path: v0.1.0 JSON → v0.2.0 SQLite
# System auto-detects old graph.json, migrates to graph.db
```

**Use case**: Querying, transactions, multi-session persistence

---

**v0.3.0+: Add More Formats as Needed**

```python
class StoreFactory:
    @staticmethod
    def create(config: Config) -> RelationshipStore:
        format = config.get('storage_format', 'auto')

        if format == 'auto':
            # Auto-detect existing format
            if os.path.exists('.xfile_context/graph.db'):
                return SQLiteStore('.xfile_context/graph.db')
            elif os.path.exists('.xfile_context/graph.json'):
                return JSONFileStore('.xfile_context/graph.json')
            else:
                return SQLiteStore('.xfile_context/graph.db')  # Default
        elif format == 'json':
            return JSONFileStore('.xfile_context/graph.json')
        elif format == 'sqlite':
            return SQLiteStore('.xfile_context/graph.db')

# User can override in config if needed:
# .cross_file_context_links.yml
# storage_format: json  # Force JSON for debugging
```

---

### Migration Strategy

**Simple data copy between formats:**

```python
def migrate_format(from_store: RelationshipStore, to_store: RelationshipStore):
    """Universal migration - works for any format pair"""
    for rel in from_store.get_all():
        to_store.add(rel)
    # That's it! Serializable structures + abstraction = trivial migration
```

**Why this works:**
- Serializable structures (dataclasses with primitives) are format-agnostic
- Storage abstraction provides `get_all()` and `add()` for all formats
- No format-specific migration code needed

---

### Benefits of This Approach

✅ **Q5a (Serializable + Abstraction):**
- Easy to add new storage backends
- Each backend implementation is simple
- Can maintain multiple implementations for testing
- v0.2.0 transition is clean

✅ **Q5b (Format Evolution):**
- Start with JSON (human-readable) in v0.1.0
- Add efficient formats later (SQLite, Protobuf) without breaking code
- Always maintain human-readable export via `export_to_json()` in interface
- Migration is just data copy via `get_all()` → `add()`

✅ **Combined Benefits:**
- v0.1.0: Simple in-memory with JSON export for debugging
- v0.2.0: Add SQLite persistence with one new class
- v0.3.0+: Add more formats as needs emerge
- All formats support JSON export for inspection

---

### TDD Documentation Requirements

The TDD should document:

1. **Data Structure Constraints**: Use primitives only (str, int, bool), avoid complex objects (AST nodes, callables, graphs)
2. **RelationshipStore Interface**: Abstract storage with `add()`, `query()`, `get_all()`, `export_to_json()`
3. **v0.1.0 Implementation**: InMemoryStore with JSON export for debugging
4. **v0.2.0 Persistence Path**: How to add SQLiteStore without changing v0.1.0 code
5. **Migration Strategy**: Universal migration via `get_all()` → `add()`
6. **Format Auto-Detection**: How system chooses format based on existing files
7. **Human-Readable Export**: All formats must support `export_to_json()` for inspection

### Impact on Requirements

**For v0.1.0**, we will implement:
- Relationship dataclass with primitives only (str, int)
- RelationshipStore abstract interface
- InMemoryStore implementation (fast, simple)
- `export_to_json()` method for debugging/verification
- No persistence across sessions (in-memory only per FR-22)

**For v0.2.0** (future), we will add:
- SQLiteStore implementation (one new class)
- Auto-migration from v0.1.0 JSON files
- Multi-session persistence
- No changes to v0.1.0 InMemoryStore needed

This approach:
- Minimizes v0.1.0 complexity (just interface + in-memory)
- Provides clear path to persistence (add SQLiteStore)
- Maintains human-readable format for all versions (JSON export)
- Enables format flexibility (Protobuf, custom formats) in future

**Key principle**: Design for flexibility without over-engineering. The abstraction is simple, the payoff is huge.

---

## DD-5: Context Injection Trigger Point - Inline with Read Tool

**Date**: 2025-11-24

**Context**: During TDD design phase, question arose about when and how to inject context (Q4). The goal is to reduce file re-reads identified in PRD session analysis (87.5% re-read rate, with retry.py read 7 times while modifying bot.py).

**Original Question (Q4: Context Injection Trigger Points)**:

Q4a: Should context be injected:
- On Read tool call (before agent sees file content)?
- After Read (as separate follow-up information)?
- On Edit tool call (when agent is about to modify)?
- All of the above?

Q4b: Should there be a rate limit on injections per session to avoid overwhelming the agent?

**Decision**: Implement inline injection during Read tool (Option 1); defer Edit warnings (Option 3) to future versions

### Problem Statement

From PRD session analysis (session 1ea0f7d8):
- `bot.py` was read 8 times in a 4-hour session
- `retry.py` was read 7 times (re-read each time `bot.py` needed modification)
- Each re-read: ~800 tokens for retry.py
- Total wasted: ~5,600 tokens just for retry.py re-reads

**Root cause**: Claude forgets function signatures between turns and must re-read dependency files.

**Goal**: Inject related function signatures when reading files to eliminate re-reads.

### Options Analyzed

**Option 1: Inject Inline with Read Result** (SELECTED)
**Option 2: Inject After Read, Separate Message**
**Option 3: Inject Before Edit (Warning)**
**Option 4: On-Demand Query Tool**

All options use **same injection content** per PRD Section 3.2:
- Location: filename + line number
- Function signature: declaration only (not full implementation)
- Docstring: if available
- Cache age: when snippet was last read

### Option 1 vs Option 2: Same Tokens, Different UX

**Baseline flow without injection:**

```
User: "Update bot.py to add error handling"
↓
Claude: Read(bot.py) → 500 tokens
Claude (thinking): "What's retry_with_backoff signature?"
Claude: Read(retry.py) → 800 tokens
Claude: Edit(bot.py)
↓
Total: 1,300 tokens
```

**Option 1: Inline injection during Read**

```
Claude: Read(bot.py)
↓
System returns:
==== File: bot.py ====
     1  import asyncio
     2  from retry import retry_with_backoff
    ...
    46      await retry_with_backoff(self._connect)
    ...

--- Related Context ---
This file imports retry_with_backoff from retry.py:120

def retry_with_backoff(func, max_attempts=3, base_delay=1.0):
    """Retry function with exponential backoff"""
    # (Cached 8 minutes ago)
---
↓
Claude: Has signature immediately, Edit(bot.py) without reading retry.py
↓
Total: 550 tokens (bot.py 500 + signature 50)
Savings: 750 tokens (58%)
```

**Option 2: Separate message after Read**

```
Claude: Read(bot.py)
↓
System returns: bot.py (500 tokens)
↓
System sends follow-up message:
"Related context for bot.py:
def retry_with_backoff(func, max_attempts=3, base_delay=1.0)..."
↓
Claude: Receives two messages, makes edit
↓
Total: 550 tokens (same as Option 1)
```

**Token efficiency is identical**, but UX differs:

| Aspect | Option 1: Inline | Option 2: Separate |
|--------|------------------|-------------------|
| Format | Single Read result with context | Read + follow-up message |
| Naturalness | ✅ Feels like enhanced Read tool | ⚠️ Feels like system interruption |
| Precedent | IDE hover tooltips | Linter warnings |
| Claude's view | "Read gave me file + context" | "Read gave file, then system interrupted" |

**Decision: Option 1** (more natural, cleaner mental model)

### Option 3: Edit Warning (Deferred to Future Version)

**What it would do:**

```
Claude: Edit(retry.py, changing function signature)
↓
[Warning] "⚠️ retry_with_backoff is used by 5 files: bot.py:46, handler.py:120...
Consider grepping for dynamic usage (getattr, eval, etc.)"
↓
Claude: Checks dependents before making breaking change
```

**Purpose**: Prevent breaking changes to widely-used functions (FR-19)

**Why deferred:**

The existing code review process already addresses this:
- Multi-agent review includes **completeness subagent**
- Completeness subagent specifically looks for:
  - Breaking changes to function signatures
  - Missing updates to dependent files
  - Incomplete refactorings
- This process has been "pretty effective in the past" at catching these gaps

**Comparison: Relationship Graph vs Grep**

| Method | Coverage | Speed | False Positives |
|--------|----------|-------|-----------------|
| Relationship Graph | Only static calls (misses dynamic usage, comments) | Instant (in-memory) | None (only real calls) |
| Grep | Everything (calls, comments, strings, dynamic) | Slower (scans files) | Many (comments, strings) |

**Why completeness subagent is sufficient:**
- Subagent will grep/search for all usages during review
- Finds both static calls (from graph) AND dynamic usage (from grep)
- Runs after changes are made, can request fixes
- More comprehensive than real-time warning (which only shows graph data)

**Future consideration:** If v0.2.0+ usage shows completeness subagent is insufficient, implement Option 3 with recommendation to grep for comprehensive coverage.

### Implementation: Option 1 Details

**Injection logic:**

```python
def handle_read_tool(filepath: str) -> ToolResult:
    # 1. Read file content
    content = read_file(filepath)

    # 2. Query relationship graph for dependencies
    dependencies = graph.get_dependencies(filepath)

    # 3. Gather cached signatures (location + signature only, per PRD 3.2)
    context_snippets = []
    for dep in dependencies:
        if cache.is_fresh(dep.target_file, max_age=600):  # 10 min (FR-14)
            # Extract signature only (NOT full implementation)
            signature = extract_signature(dep.target_file, dep.line_number)
            context_snippets.append({
                "source": f"{dep.target_file}:{dep.line_number}",
                "signature": signature,
                "cache_age": cache.get_age(dep.target_file)
            })

    # 4. Check token limit (FR-10: <500 tokens for context injection)
    total_context_tokens = sum(count_tokens(s) for s in context_snippets)

    if context_snippets and total_context_tokens < 500:
        # Format as part of Read result
        formatted_context = format_context_section(context_snippets)
        return ToolResult(
            content=content,
            related_context=formatted_context  # Appended inline
        )
    else:
        # Skip injection if too large or no dependencies
        return ToolResult(content=content)
```

**Context format (per PRD Section 3.2):**

```
--- Related Context ---
This file imports retry_with_backoff from retry.py:120

def retry_with_backoff(func, max_attempts=3, base_delay=1.0):
    """Retry function with exponential backoff"""
    # (Cached 8 minutes ago)

This file imports setup_logging from config.py:45

def setup_logging(level='INFO', format='json'):
    """Configure logging for the application"""
    # (Cached 3 minutes ago)
---
```

**Token limit handling (FR-10):**
- Maximum 500 tokens for all injected context
- If dependencies exceed 500 tokens: skip injection entirely
- Alternative (future): prioritize most-used dependencies, inject top N

**Cache freshness (FR-14):**
- Only inject from cache if age < 10 minutes
- If stale: skip that dependency (don't slow down Read with re-parse)
- Working memory principle: recent context is relevant

### Answer to Q4b: Rate Limiting

**No explicit rate limit needed** for Option 1 because:

1. **Natural throttling**: Injection only happens on Read tool calls
   - Claude controls Read frequency
   - If Claude reads 20 files, gets 20 injections (appropriate)

2. **Token limit is sufficient**: FR-10 caps injection at 500 tokens per Read
   - Even if Claude reads 10 files with injection: 10 × 500 = 5,000 tokens
   - Reasonable within session limits

3. **Cache freshness provides implicit limit**:
   - Only fresh cache entries injected (<10 min old)
   - If Claude reads same file repeatedly in short time: same cached snippets
   - No redundant parsing/re-reading

**Future consideration**: If metrics (FR-43) show excessive injection causing issues, add configurable rate limit (e.g., max 50 injections per session).

### Benefits and Trade-offs

**Benefits:**
✅ Directly addresses re-read problem (58% token reduction in example)
✅ Natural UX (feels like enhanced Read tool)
✅ No new tools for Claude to learn
✅ Automatic and proactive (Claude doesn't need to request)
✅ Respects token limits (FR-10) and cache freshness (FR-14)

**Trade-offs:**
⚠️ Injection content may not always be needed (slight token overhead)
⚠️ Requires accurate relationship graph (depends on AST parsing quality)
⚠️ Signature-only may be insufficient for complex APIs (deferred: inject more if needed)

**Deferred to future versions:**
- Option 3 (Edit warnings): Completeness subagent already handles this
- Option 4 (Query tool): Wait for user feedback on need for explicit queries
- Multi-turn injection throttling: Wait for metrics to show if needed

### TDD Documentation Requirements

The TDD should document:

1. **Read Tool Enhancement**: How context injection augments Read tool results
2. **Injection Format**: Location + signature + docstring + cache age (per PRD 3.2)
3. **Token Limit Handling**: Skip injection if >500 tokens (FR-10)
4. **Cache Freshness Check**: Only inject if cached <10 min ago (FR-14)
5. **Signature Extraction**: Parse function def + docstring, exclude implementation
6. **Fallback Behavior**: If injection fails or too large, return file content only
7. **Logging**: Log all injections per FR-26 (timestamp, source, target, tokens, cache age)

### Impact on Requirements

**For v0.1.0**, we will implement:
- Context injection inline with Read tool (FR-8)
- Signature extraction from cached files
- Token limit enforcement (FR-10: <500 tokens)
- Cache freshness check (FR-14: <10 minutes)
- Injection logging (FR-26, FR-27)

**Deferred to future versions:**
- Option 3 (Edit warnings): Rely on existing completeness subagent review process
- Option 4 (Query tool): Add if user feedback shows need
- Rate limiting: Add if metrics show excessive injection

**Not implementing:**
- Option 2 (separate messages): Less natural UX than inline
- Injection on Edit: Completeness subagent handles breaking change detection

This approach:
- Directly attacks the re-read problem from PRD analysis
- Maintains natural Read tool UX
- Leverages existing review process for safety (completeness subagent)
- Provides clear path to add Option 3/4 if metrics show value

**Key principle**: Start with the injection point that directly reduces re-reads (Read tool), defer safety features that existing processes already handle.

---

## DD-6: MCP Server Architecture and v0.2.0 Evolution Strategy

**Date**: 2025-11-24

**Context**: During TDD design phase, question arose about MCP server architecture (Q1). Should Cross-File Context Links be implemented as standalone MCP server, built-in feature, or something else? How should we design v0.1.0 to minimize v0.2.0 refactoring when adding persistence and multi-session sharing?

**Original Question (Q1: MCP Server Architecture Specifics)**:

Q1a: Should Cross-File Context Links be implemented as:
- A standalone MCP server (like `mcp-server-context-links`) that Claude Code connects to?
- A built-in feature/extension of Claude Code itself?
- An MCP server SDK library that other MCP servers can integrate?

Q1b: For the MCP protocol, preferences on:
- MCP protocol version/spec to target?
- Communication mechanism (stdio, HTTP, WebSocket)?
- Specific MCP tools to expose?

**Decision**: Implement as standalone MCP server with layered architecture that enables smooth v0.2.0 evolution

### Understanding MCP Server Patterns

**Standard MCP pattern:**
```
Claude Code Session
  ↓ spawns & connects via stdio/HTTP
MCP Server Process (per-session)
  ↓ accesses (if needed)
Shared Resources (database, filesystem, API)
```

**Key MCP principles:**
1. MCP servers are **per-session**: Claude Code spawns new MCP server process for each session
2. MCP servers can be **thin or thick**: All logic in-process (thick) or adapter to shared backend (thin)
3. **No built-in session discovery**: Each session connects to servers defined in config, no parent-child awareness

**Examples from existing MCP servers:**

| Server | Pattern | Architecture |
|--------|---------|-------------|
| mcp-server-filesystem | Thick, isolated | Each session has independent in-process cache |
| mcp-server-sqlite | Thin adapter | Multiple sessions → shared SQLite database |
| mcp-server-git | Thin adapter | Multiple sessions → shared Git repository |

### Architecture Variations Considered

**Variation 1: Multiple full-featured MCP servers + Discovery service**

```
Parent Session → Full MCP Server A (graph, cache, watcher)
                    ↑ "discover and redirect"
Subagent Session → Full MCP Server B ----/
```

❌ **Rejected because:**
- MCP has no discovery protocol (config is static before session starts)
- MCP has no redirect mechanism (can't tell one server to "use that other server")
- Against MCP design (sessions are independent, not parent-child aware)

**Variation 2: Multiple thin MCP servers + Shared backend service**

```
Parent Session → Thin MCP Server A ↘
                                     → Backend Service (graph, cache, watcher)
Subagent Session → Thin MCP Server B ↗
```

✅ **Aligns with MCP patterns** (like mcp-server-sqlite)

**But not needed for v0.1.0!**

---

### Decision: Evolution Path

**v0.1.0: Thick Self-Contained MCP Server**

```
Claude Session
  ↓ spawns
MCP Server Process
  ↓ contains
- Relationship Graph (in-memory)
- Working Memory Cache (in-memory)
- File Watcher (watches project)
- Read Tool Enhancement (injects context)
```

**Characteristics:**
- One MCP server per Claude session (standard MCP pattern)
- All logic in MCP server process (thick server)
- No backend service (simpler for v0.1.0)
- No sharing between sessions (fine - not the v0.1.0 goal)
- When session ends, graph/cache discarded (per FR-22: in-memory only)

**Rationale:**
- Aligns with FR-22 (in-memory only, no persistence)
- Simpler to build and test (no IPC, no backend management)
- Validates single-session value first
- Natural evolution path to v0.2.0

---

**v0.2.0: Thin MCP Server + Shared Backend Service**

```
Parent Session → MCP Server A ↘
                                → Backend Service
Subagent Session 1 → MCP Server B → (persisted graph,
Subagent Session 2 → MCP Server C → shared cache)
                                ↗
                              SQLite/Filesystem
```

**Evolution from v0.1.0:**
- Keep MCP server per session (standard MCP pattern)
- Extract business logic to backend service
- MCP servers become "thin" - delegate to backend for graph queries
- Backend persists graph to filesystem/SQLite (DD-4)
- All sessions (parent + subagents) access same persisted state

**Addresses v0.2.0 goals:**
- Multi-session state sharing (solves multi-agent review bottleneck)
- Persistence across restarts
- Subagents avoid re-parsing (load pre-built graph from backend)

---

### Design for Minimal v0.2.0 Refactoring

**Key Insight**: Separate MCP protocol handling from business logic in v0.1.0, making v0.2.0 refactor trivial.

#### Pattern 1: Layer Separation

**v0.1.0 Architecture:**

```python
# Layer 1: MCP Protocol Handler (stays in MCP server)
class CrossFileContextMCPServer:
    """Handles MCP protocol - thin adapter"""
    def __init__(self, project_root: str):
        # Delegate to business logic layer
        self.context_service = CrossFileContextService(project_root)

    # MCP protocol methods
    def list_tools(self):
        return ["read_with_context", "query_relationships"]

    def call_tool(self, name: str, args: dict):
        # Pure delegation - no business logic here!
        if name == "read_with_context":
            return self.context_service.read_with_context(args["filepath"])
        elif name == "query_relationships":
            return self.context_service.query_relationships(args["filepath"])

# Layer 2: Business Logic (can be extracted to backend)
class CrossFileContextService:
    """Core business logic - no MCP dependencies"""
    def __init__(self, project_root: str):
        self.graph = RelationshipGraph()
        self.cache = WorkingMemoryCache()
        self.store = InMemoryStore()  # From DD-4!
        self.watcher = FileWatcher(project_root)
        self.analyzer = PythonAnalyzer()  # From DD-2!

        # Initialize
        self._build_initial_graph()
        self._start_watching()

    def read_with_context(self, filepath: str) -> dict:
        """Business logic for context injection"""
        content = read_file(filepath)
        dependencies = self.graph.get_dependencies(filepath)
        context = self._format_context(dependencies)
        return {"content": content, "context": context}

# Layer 3: Storage (already abstracted in DD-4!)
class InMemoryStore(RelationshipStore):
    """Storage implementation"""
    pass
```

**Critical**: `CrossFileContextService` has **zero MCP dependencies**. Pure business logic.

---

**v0.2.0 Changes (minimal!):**

```python
# MCP Server (thin adapter - ONE LINE CHANGES)
class CrossFileContextMCPServer:
    def __init__(self, project_root: str):
        # OLD: self.context_service = CrossFileContextService(project_root)
        # NEW: self.context_service = CrossFileContextClient(project_root)
        self.context_service = CrossFileContextClient(project_root)

    # Everything else identical to v0.1.0!
    def call_tool(self, name: str, args: dict):
        if name == "read_with_context":
            return self.context_service.read_with_context(args["filepath"])

# Client (adapter to backend - NEW)
class CrossFileContextClient:
    """Adapts to backend service via IPC"""
    def __init__(self, project_root: str):
        self.backend = connect_to_backend(project_root)

    def read_with_context(self, filepath: str) -> dict:
        # Delegate to backend
        return self.backend.call("read_with_context", {"filepath": filepath})

# Backend Service (SAME business logic, different process)
class CrossFileContextService:
    """Exact same code as v0.1.0, just runs in separate process"""
    def __init__(self, project_root: str):
        self.graph = RelationshipGraph()
        self.cache = WorkingMemoryCache()
        # ONLY THIS LINE CHANGES
        # OLD: self.store = InMemoryStore()
        # NEW: self.store = SQLiteStore(f"{project_root}/.xfile_context/graph.db")
        self.store = SQLiteStore(f"{project_root}/.xfile_context/graph.db")
        self.watcher = FileWatcher(project_root)
        self.analyzer = PythonAnalyzer()

    def read_with_context(self, filepath: str) -> dict:
        # Identical to v0.1.0
        content = read_file(filepath)
        dependencies = self.graph.get_dependencies(filepath)
        context = self._format_context(dependencies)
        return {"content": content, "context": context}
```

**Changes summary:**
- MCP server: Change 1 line (instantiate Client instead of Service)
- Service: Change 1 line (SQLiteStore instead of InMemoryStore)
- Add: Client adapter class (~50 lines)
- Add: Backend launcher/IPC (~100 lines)
- **Total**: ~150 new lines, 2 changed lines, business logic untouched

---

#### Pattern 2: Interface-Based Design

**Define service interface:**

```python
class ContextServiceInterface(ABC):
    """Interface both local and remote implementations follow"""

    @abstractmethod
    def read_with_context(self, filepath: str) -> dict:
        pass

    @abstractmethod
    def query_relationships(self, filepath: str) -> dict:
        pass

    @abstractmethod
    def export_graph(self, format: str) -> dict:
        pass

# v0.1.0: Local implementation
class CrossFileContextService(ContextServiceInterface):
    def read_with_context(self, filepath: str) -> dict:
        # Actual implementation
        pass

# v0.2.0: Remote client implementation
class CrossFileContextClient(ContextServiceInterface):
    def read_with_context(self, filepath: str) -> dict:
        # Delegates to backend via IPC
        return self.backend.call("read_with_context", {"filepath": filepath})
```

**MCP server only depends on interface:**

```python
class CrossFileContextMCPServer:
    def __init__(self, service: ContextServiceInterface):
        self.service = service  # Interface, not concrete class
```

**Benefit**: MCP server code never changes between v0.1.0 and v0.2.0. Just swap implementation.

---

#### Pattern 3: Storage Abstraction (From DD-4)

Already decided! Storage abstraction means:

```python
# v0.1.0
service = CrossFileContextService(store=InMemoryStore())

# v0.2.0
service = CrossFileContextService(store=SQLiteStore("graph.db"))
```

**No changes to service code**. Storage swapped via dependency injection.

---

#### Pattern 4: Modular Components (From DD-1, DD-2)

Already decided! Components are modular:
- Detector plugins (DD-1)
- Language analyzers (DD-2)
- Storage abstraction (DD-4)

Moving to backend is just changing where they run:

```python
# v0.1.0: All in MCP server process
mcp_server_process:
  ├─ MCP protocol handler
  ├─ CrossFileContextService
  │   ├─ RelationshipGraph
  │   ├─ PythonAnalyzer
  │   │   └─ Detector plugins
  │   └─ InMemoryStore
  └─ FileWatcher

# v0.2.0: Business logic extracted
mcp_server_process:
  ├─ MCP protocol handler
  └─ CrossFileContextClient (IPC adapter)

backend_service_process:
  ├─ CrossFileContextService (same code!)
  │   ├─ RelationshipGraph
  │   ├─ PythonAnalyzer
  │   │   └─ Detector plugins (unchanged!)
  │   └─ SQLiteStore (swapped)
  └─ FileWatcher
```

---

#### Pattern 5: Factory Pattern for Mode Switching

**v0.1.0 instantiation:**

```python
# mcp_server.py
def main():
    project_root = sys.argv[1]

    # Factory pattern - easy to swap
    service = create_service(project_root, mode="local")

    mcp_server = CrossFileContextMCPServer(service)
    mcp_server.run()

def create_service(project_root: str, mode: str) -> ContextServiceInterface:
    if mode == "local":
        return CrossFileContextService(
            project_root=project_root,
            store=InMemoryStore()
        )
    elif mode == "remote":  # v0.2.0
        return CrossFileContextClient(project_root)
    else:
        raise ValueError(f"Unknown mode: {mode}")
```

**v0.2.0 change:**

```python
def main():
    project_root = sys.argv[1]

    # ONE LINE CHANGE
    # OLD: service = create_service(project_root, mode="local")
    # NEW:
    service = create_service(project_root, mode="remote")

    mcp_server = CrossFileContextMCPServer(service)
    mcp_server.run()
```

---

### Testing Strategy That Validates Refactorability

**v0.1.0 tests (business logic in isolation):**

```python
def test_read_with_context():
    service = CrossFileContextService(
        project_root="/test/project",
        store=InMemoryStore()
    )

    result = service.read_with_context("bot.py")
    assert "retry_with_backoff" in result["context"]

def test_mcp_tool_delegation():
    mock_service = Mock(spec=ContextServiceInterface)
    mcp_server = CrossFileContextMCPServer(mock_service)

    mcp_server.call_tool("read_with_context", {"filepath": "bot.py"})
    mock_service.read_with_context.assert_called_once_with("bot.py")
```

**Key insight**: If tests pass with mocks, then swapping implementations is safe!

**v0.2.0 tests (reuse v0.1.0 tests!):**

```python
def test_read_with_context_with_persistence():
    service = CrossFileContextService(
        project_root="/test/project",
        store=SQLiteStore(":memory:")  # In-memory SQLite for testing
    )

    result = service.read_with_context("bot.py")
    assert "retry_with_backoff" in result["context"]
    # Exact same test as v0.1.0!

def test_client_delegates_to_backend():
    with mock_backend_server() as backend:
        client = CrossFileContextClient("/test/project")
        result = client.read_with_context("bot.py")
        assert backend.received_call("read_with_context", {"filepath": "bot.py"})
```

**Test reuse**: ~90% of v0.1.0 tests validate v0.2.0 business logic. Only need to test IPC layer.

---

### Answers to Q1 Specifics

**Q1a: Implementation type**
- **Decision**: Standalone MCP server (`xfile-context`)
- Not built-in to Claude Code (allows independent updates)
- Not SDK library (too heavyweight for single-purpose tool)

**Q1b: Protocol details**
- **Protocol version**: Latest stable MCP spec
- **Communication**: stdio (standard for MCP servers, simple, reliable)
- **Tools exposed** (v0.1.0):
  - `read_with_context`: Enhanced Read with injected signatures (DD-5)
  - `query_relationships`: Query relationship graph for file
  - `export_graph`: Export graph to JSON for inspection (DD-4)

**Configuration** (`.claude_code/mcp_servers.json`):
```json
{
  "xfile-context": {
    "command": "python",
    "args": ["-m", "xfile_context.mcp_server"],
    "cwd": "${workspaceFolder}"
  }
}
```

---

### Summary: Design Choices That Minimize Refactor

| Design Choice | v0.1.0 Benefit | v0.2.0 Refactor Impact |
|---------------|----------------|------------------------|
| **Layer separation** | Testable in isolation | MCP layer unchanged |
| **Storage abstraction** (DD-4) | Swap implementations | Change 1 line (InMemory → SQLite) |
| **Dependency injection** | Mock for testing | Inject different implementations |
| **Interface-based design** | Clear contracts | Swap local ↔ remote transparently |
| **Modular components** (DD-1, DD-2) | Plugin architecture | Move as unit to backend |
| **Factory pattern** | Easy mode switching | Change 1 line in factory |

**Total v0.2.0 refactor effort:**
- Lines changed: 2-3
- New code: ~150 lines (client + IPC)
- Business logic changes: 0
- Test reuse: ~90%

---

### TDD Documentation Requirements

The TDD should document:

1. **Layer Architecture**:
   - MCP Protocol Layer: Handles MCP tool calls (thin adapter)
   - Business Logic Layer: Core functionality (no MCP dependencies)
   - Storage Layer: Already abstracted (DD-4)

2. **Service Interface Contract**:
   ```python
   class ContextServiceInterface(ABC):
       @abstractmethod
       def read_with_context(self, filepath: str) -> dict: pass
       @abstractmethod
       def query_relationships(self, filepath: str) -> dict: pass
       @abstractmethod
       def export_graph(self, format: str) -> dict: pass
   ```

3. **Factory Pattern**:
   ```python
   def create_service(mode: str) -> ContextServiceInterface:
       if mode == "local": return CrossFileContextService(...)
       elif mode == "remote": return CrossFileContextClient(...)
   ```

4. **Dependency Injection Points**:
   - Service accepts `store: RelationshipStore` (DD-4)
   - Service accepts `analyzer: LanguageAnalyzer` (DD-2)
   - MCP server accepts `service: ContextServiceInterface`

5. **v0.2.0 Evolution Path**:
   - Document how to add CrossFileContextClient
   - Document IPC mechanism (Unix socket, HTTP, etc.)
   - Document backend service launcher
   - Document migration from InMemoryStore to SQLiteStore

6. **Testing Requirements**:
   - Business logic must be testable without MCP dependencies
   - Interface mocking must validate delegation
   - v0.1.0 tests should work with v0.2.0 SQLiteStore (in-memory mode)

### Impact on Requirements

**For v0.1.0**, we will implement:
- Standalone MCP server with stdio communication
- Layered architecture (MCP protocol + business logic + storage)
- Interface-based design for service contract
- Factory pattern for instantiation
- Dependency injection for storage and analyzers
- All components modular and testable in isolation

**For v0.2.0** (future), we will add:
- CrossFileContextClient (IPC adapter)
- Backend service process (runs CrossFileContextService)
- IPC mechanism (Unix socket or HTTP)
- Backend auto-start logic (if not running)
- Migration: 2-3 lines changed in existing code

This approach:
- Minimizes v0.1.0 complexity (no backend service, no IPC)
- Provides clear and low-risk path to v0.2.0 (layered design enables extraction)
- Leverages abstractions from DD-1, DD-2, DD-4 (already decided)
- Validates v0.1.0 value before adding multi-session complexity

**Key principle**: Design v0.1.0 architecture to support v0.2.0 evolution, but don't implement v0.2.0 features prematurely. The abstractions enable future refactoring without dictating it.

---
