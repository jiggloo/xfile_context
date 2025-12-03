# Functional Test Codebase

This directory contains a representative Python codebase with 50-100 files designed for functional testing of the cross-file context analyzer.

## Purpose

This test codebase serves as the **ground truth** for validating that the analyzer correctly:
- Detects all relationship types (imports, function calls, inheritance)
- Handles edge cases (EC-1 through EC-20)
- Injects context correctly
- Manages cache and memory appropriately

## Structure

```
test_codebase/
├── __init__.py
├── ground_truth.json          # Machine-parseable expected relationships
├── README.md                  # This file
├── core/                      # Core application modules
│   ├── models/                # Data models
│   │   ├── base.py           # Base model class
│   │   ├── user.py           # User model
│   │   ├── product.py        # Product model
│   │   └── order.py          # Order model
│   ├── services/              # Business logic
│   │   ├── base_service.py   # Base service class
│   │   ├── user_service.py   # User service
│   │   ├── product_service.py # Product service
│   │   ├── order_service.py  # Order service
│   │   └── notification_service.py # Notification service
│   └── utils/                 # Utility functions
│       ├── formatting.py     # Formatting utilities
│       ├── validation.py     # Validation utilities
│       └── helpers.py        # General helpers
├── api/                       # API layer
│   ├── endpoints.py          # API endpoints
│   └── middleware.py         # Request middleware
├── data/                      # Data access layer
│   ├── repository.py         # Repository interface
│   └── in_memory_store.py    # In-memory implementation
├── config/                    # Configuration
│   ├── settings.py           # Settings management
│   └── constants.py          # Application constants
└── edge_cases/                # Edge case examples
    ├── relationship_detection/  # EC-1 through EC-10
    ├── context_injection/       # EC-11 through EC-14
    ├── memory_management/       # EC-15 through EC-17
    └── failure_modes/           # EC-18 through EC-20
```

## Edge Cases Covered

### Relationship Detection (EC-1 through EC-10)

| ID | Description | File(s) |
|----|-------------|---------|
| EC-1 | Circular Dependencies | `ec1_circular_a.py`, `ec1_circular_b.py` |
| EC-2 | Dynamic Imports | `ec2_dynamic_imports.py` |
| EC-3 | Aliased Imports | `ec3_aliased_imports.py` |
| EC-4 | Wildcard Imports | `ec4_wildcard_imports.py` |
| EC-5 | Conditional Imports (TYPE_CHECKING) | `ec5_conditional_imports.py` |
| EC-6 | Dynamic Dispatch | `ec6_dynamic_dispatch.py` |
| EC-7 | Monkey Patching | `ec7_monkey_patching.py` |
| EC-8 | Decorators | `ec8_decorators.py` |
| EC-9 | exec/eval Usage | `ec9_exec_eval.py` |
| EC-10 | Metaclasses | `ec10_metaclasses.py` |

### Context Injection (EC-11 through EC-14)

| ID | Description | File(s) |
|----|-------------|---------|
| EC-11 | Stale Cache After External Edit | `ec11_stale_cache.py` |
| EC-12 | Large Functions | `ec12_large_functions.py` |
| EC-13 | Multiple Definitions | `ec13_multiple_definitions.py`, `ec13_multiple_definitions_alt.py` |
| EC-14 | Deleted Files | `ec14_deleted_files.py` |

### Memory Management (EC-15 through EC-17)

| ID | Description | File(s) |
|----|-------------|---------|
| EC-15 | Memory Pressure | `ec15_memory_pressure.py` |
| EC-16 | Long-Running Sessions | `ec16_long_sessions.py` |
| EC-17 | Massive Files | `ec17_massive_files.py` |

### Failure Modes (EC-18 through EC-20)

| ID | Description | File(s) |
|----|-------------|---------|
| EC-18 | Parsing Failure | `ec18_parsing_failure.py` |
| EC-19 | Graph Corruption | `ec19_graph_corruption.py` |
| EC-20 | Concurrent Modifications | `ec20_concurrent_modifications.py` |

## Ground Truth Manifest

The `ground_truth.json` file contains:
- **relationships**: Expected import relationships between all files
- **edge_cases**: Expected behavior for each edge case
- **statistics**: Summary counts and metrics

### Using the Ground Truth

```python
import json

with open("ground_truth.json") as f:
    ground_truth = json.load(f)

# Get expected imports for a file
user_imports = ground_truth["relationships"]["core/models/user.py"]["imports"]

# Get expected behavior for an edge case
ec1_behavior = ground_truth["edge_cases"]["EC-1"]["expected_behavior"]
```

## Test Categories

This codebase supports validation of:

- **T-1**: Relationship Detection (T-1.1 through T-1.8)
- **T-2**: Context Injection (T-2.1 through T-2.5)
- **T-3**: Working Memory Cache (T-3.1 through T-3.5)
- **T-4**: Cross-File Awareness (T-4.1 through T-4.8)
- **T-5**: Context Injection Logging (T-5.1 through T-5.7)
- **T-6**: Dynamic Python Handling (T-6.1 through T-6.10)
- **T-10**: Session Metrics (T-10.1 through T-10.7)

## File Count

- **Total Python files**: 53
- **Core module files**: ~20
- **Edge case files**: ~21
- **Init files**: 12

This meets the 50-100 file requirement for representative testing.
