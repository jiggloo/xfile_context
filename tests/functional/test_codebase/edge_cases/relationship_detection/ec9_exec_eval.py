# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-9: exec() and eval() Usage (Unhandled in v0.1.0)

This module demonstrates exec/eval patterns.
These cannot be statically analyzed as code is generated at runtime.

Expected behavior:
- Analyzer should emit warning about dynamic code execution
- Analyzer should mark file as containing dynamic execution
- Analyzer should NOT attempt to analyze the string-based code
"""

from typing import Any

# Static import for comparison
from tests.functional.test_codebase.core.utils.helpers import sanitize_input


def create_class_dynamically(class_name: str, attributes: dict[str, Any]) -> type:
    """Create a class dynamically using exec.

    This is a pattern sometimes used in ORMs or code generators.
    The analyzer cannot analyze the code being executed.
    """
    # Build class definition as string
    attr_defs = "\n    ".join(f"{name} = {repr(value)}" for name, value in attributes.items())
    class_code = f"""
class {class_name}:
    {attr_defs if attr_defs else "pass"}
"""
    # Execute the string as code
    namespace: dict[str, Any] = {}
    exec(class_code, namespace)
    return namespace[class_name]


def evaluate_expression(expression: str, variables: dict[str, Any]) -> Any:
    """Evaluate a mathematical expression using eval.

    WARNING: eval() can execute arbitrary code.
    This is for demonstration only.
    """
    # Restrict to basic operations
    allowed_names = {
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "len": len,
    }
    # Merge with provided variables
    safe_dict = {**allowed_names, **variables}

    # Evaluate expression - cannot be statically analyzed
    return eval(expression, {"__builtins__": {}}, safe_dict)


def execute_template(template: str, context: dict[str, Any]) -> str:
    """Execute a template string with embedded Python code.

    This pattern is sometimes used in simple templating engines.
    """
    result_var = "_result_"
    code = f"{result_var} = f'''{template}'''"

    namespace = dict(context)
    exec(code, namespace)
    return namespace[result_var]


class DynamicMethodGenerator:
    """Generates methods dynamically using exec."""

    def __init__(self) -> None:
        self.methods: dict[str, Any] = {}

    def add_method(self, name: str, params: list[str], body: str) -> None:
        """Add a method by generating code dynamically."""
        param_str = ", ".join(params)
        method_code = f"""
def {name}(self, {param_str}):
    {body}
"""
        namespace: dict[str, Any] = {}
        exec(method_code, namespace)
        self.methods[name] = namespace[name]

    def call_method(self, name: str, *args) -> Any:
        """Call a dynamically generated method."""
        if name not in self.methods:
            raise AttributeError(f"Method {name} not found")
        return self.methods[name](self, *args)


# Static function for comparison
def safe_process(text: str) -> str:
    """Process text safely using static import."""
    return sanitize_input(text)


# Compile for slightly better performance (still dynamic)
def compiled_evaluate(expression: str) -> Any:
    """Evaluate using compiled code object."""
    code_obj = compile(expression, "<string>", "eval")
    return eval(code_obj)
