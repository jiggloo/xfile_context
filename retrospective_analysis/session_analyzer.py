#!/usr/bin/env python3
"""
Claude Code Session Analyzer - Information Retrieval Pattern Analysis

Analyzes .jsonl session logs to identify inefficient search/discovery patterns.
"""

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ToolCall:
    """Represents a single tool invocation with its result."""

    tool_id: str
    tool_name: str
    timestamp: datetime
    inputs: Dict
    result: Optional[str] = None
    result_metadata: Optional[Dict] = None
    is_error: bool = False
    is_empty: bool = False

    def elapsed_ms(self, other: "ToolCall") -> float:
        """Calculate milliseconds between this and another tool call."""
        delta = other.timestamp - self.timestamp
        return delta.total_seconds() * 1000


class SessionAnalyzer:
    """Analyzes a single Claude Code session for information retrieval patterns."""

    def __init__(self, session_file: Path):
        self.session_file = session_file
        self.tool_calls: List[ToolCall] = []
        self.session_id: Optional[str] = None

    def parse(self):
        """Parse the session JSONL file."""
        tool_map = {}  # Map tool_id to ToolCall

        with open(self.session_file) as f:
            for line in f:
                data = json.loads(line)

                # Capture session ID
                if not self.session_id and "sessionId" in data:
                    self.session_id = data["sessionId"]

                # Parse tool uses
                if data.get("type") == "assistant" and "message" in data:
                    for content in data["message"].get("content", []):
                        if content.get("type") == "tool_use":
                            tool_call = ToolCall(
                                tool_id=content.get("id"),
                                tool_name=content.get("name"),
                                timestamp=datetime.fromisoformat(
                                    data["timestamp"].replace("Z", "+00:00")
                                ),
                                inputs=content.get("input", {}),
                            )
                            tool_map[tool_call.tool_id] = tool_call
                            self.tool_calls.append(tool_call)

                # Parse tool results
                if data.get("type") == "user" and "message" in data:
                    message_content = data["message"].get("content", [])
                    # Content can be a string (user message) or list (tool results)
                    if isinstance(message_content, list):
                        for content in message_content:
                            if isinstance(content, dict) and content.get("type") == "tool_result":
                                tool_id = content.get("tool_use_id")
                                if tool_id in tool_map:
                                    tool_call = tool_map[tool_id]
                                    result_content = content.get("content", "")

                                    # Normalize result to string
                                    if isinstance(result_content, list):
                                        result_str = json.dumps(result_content)
                                    else:
                                        result_str = str(result_content)

                                    # Store result
                                    tool_call.result = result_str
                                    tool_call.result_metadata = data.get("toolUseResult", {})

                                    # Detect errors
                                    tool_call.is_error = (
                                        "error" in result_str.lower() or "Error" in result_str
                                    )

                                    # Detect empty results (tool-specific)
                                    if tool_call.tool_name in ["Grep", "Glob"]:
                                        num_files = tool_call.result_metadata.get("numFiles", -1)
                                        tool_call.is_empty = num_files == 0
                                    elif tool_call.tool_name == "Read":
                                        # Empty if very short or has error patterns
                                        tool_call.is_empty = len(result_str.strip()) < 10

    def analyze_search_efficiency(self) -> Dict:
        """Analyze search tool usage patterns."""
        search_tools = ["Grep", "Glob"]
        searches = [tc for tc in self.tool_calls if tc.tool_name in search_tools]

        empty_searches = [s for s in searches if s.is_empty]
        error_searches = [s for s in searches if s.is_error]

        # Detect repeated searches (same pattern multiple times)
        pattern_counts = defaultdict(list)
        for search in searches:
            if search.tool_name == "Grep":
                pattern = search.inputs.get("pattern", "")
            else:  # Glob
                pattern = search.inputs.get("pattern", "")
            pattern_counts[pattern].append(search)

        repeated_patterns = {pat: calls for pat, calls in pattern_counts.items() if len(calls) > 1}

        return {
            "total_searches": len(searches),
            "empty_results": len(empty_searches),
            "error_results": len(error_searches),
            "success_rate": (
                (len(searches) - len(empty_searches)) / len(searches) if searches else 0
            ),
            "repeated_patterns_count": len(repeated_patterns),
            "repeated_patterns": repeated_patterns,
            "empty_search_details": [
                {
                    "tool": s.tool_name,
                    "pattern": s.inputs.get("pattern", "N/A"),
                    "timestamp": s.timestamp.isoformat(),
                }
                for s in empty_searches[:10]  # Limit to first 10
            ],
        }

    def analyze_file_access_sequence(self) -> Dict:
        """Analyze Read tool usage patterns."""
        reads = [tc for tc in self.tool_calls if tc.tool_name == "Read"]

        # Detect re-reads (same file read multiple times)
        file_access_counts = defaultdict(list)
        for read in reads:
            file_path = read.inputs.get("file_path", "")
            file_access_counts[file_path].append(read)

        re_reads = {
            path: accesses for path, accesses in file_access_counts.items() if len(accesses) > 1
        }

        # Calculate time between first and second read (potential context loss)
        re_read_intervals = []
        for path, accesses in re_reads.items():
            if len(accesses) >= 2:
                interval_ms = accesses[0].elapsed_ms(accesses[1])
                re_read_intervals.append(
                    {"file": path, "interval_ms": interval_ms, "num_accesses": len(accesses)}
                )

        return {
            "total_reads": len(reads),
            "unique_files": len(file_access_counts),
            "re_read_files": len(re_reads),
            "re_read_intervals": sorted(
                re_read_intervals, key=lambda x: x["interval_ms"], reverse=True
            )[:10],
        }

    def analyze_tool_distribution(self) -> Dict:
        """Analyze overall tool usage distribution."""
        tool_counts = defaultdict(int)
        for tc in self.tool_calls:
            tool_counts[tc.tool_name] += 1

        return dict(sorted(tool_counts.items(), key=lambda x: x[1], reverse=True))

    def calculate_discovery_metrics(self) -> Dict:
        """Calculate time-to-discovery metrics."""
        if not self.tool_calls:
            return {}

        # Time to first file read
        first_read = next((tc for tc in self.tool_calls if tc.tool_name == "Read"), None)
        first_search = next(
            (tc for tc in self.tool_calls if tc.tool_name in ["Grep", "Glob"]), None
        )

        metrics = {
            "session_duration_ms": (
                self.tool_calls[0].elapsed_ms(self.tool_calls[-1])
                if len(self.tool_calls) > 1
                else 0
            ),
            "first_tool": self.tool_calls[0].tool_name if self.tool_calls else None,
        }

        if first_read and first_search:
            metrics["search_to_read_delay_ms"] = first_search.elapsed_ms(first_read)

        return metrics

    def generate_report(self) -> str:
        """Generate a comprehensive analysis report."""
        self.parse()

        search_analysis = self.analyze_search_efficiency()
        file_analysis = self.analyze_file_access_sequence()
        tool_dist = self.analyze_tool_distribution()
        discovery_metrics = self.calculate_discovery_metrics()

        report = []
        report.append("# Information Retrieval Pattern Analysis")
        report.append(f"\n**Session:** {self.session_id}")
        report.append(f"**Log File:** {self.session_file.name}")
        report.append("\n## Overview")
        report.append(f"- Total tool calls: {len(self.tool_calls)}")
        report.append(
            f"- Session duration: {discovery_metrics.get('session_duration_ms', 0):.0f}ms"
        )
        report.append(f"- First tool used: {discovery_metrics.get('first_tool', 'N/A')}")

        report.append("\n## Tool Usage Distribution")
        for tool, count in tool_dist.items():
            report.append(f"- {tool}: {count}")

        report.append("\n## Search Efficiency Analysis")
        report.append(f"- Total searches (Grep/Glob): {search_analysis['total_searches']}")
        empty_pct = (
            search_analysis["empty_results"] / search_analysis["total_searches"] * 100
            if search_analysis["total_searches"]
            else 0
        )
        report.append(f"- Empty results: {search_analysis['empty_results']} ({empty_pct:.1f}%)")
        report.append(f"- Success rate: {search_analysis['success_rate']*100:.1f}%")
        report.append(f"- Repeated patterns: {search_analysis['repeated_patterns_count']}")

        if search_analysis["empty_search_details"]:
            report.append("\n### Empty Search Samples (First 10)")
            for detail in search_analysis["empty_search_details"]:
                report.append(
                    f"- **{detail['tool']}**: `{detail['pattern']}` at {detail['timestamp']}"
                )

        if search_analysis["repeated_patterns"]:
            report.append("\n### Repeated Search Patterns")
            for pattern, calls in list(search_analysis["repeated_patterns"].items())[:5]:
                report.append(f"- Pattern `{pattern}`: {len(calls)} times")

        report.append("\n## File Access Analysis")
        report.append(f"- Total file reads: {file_analysis['total_reads']}")
        report.append(f"- Unique files accessed: {file_analysis['unique_files']}")
        report.append(f"- Files re-read: {file_analysis['re_read_files']}")

        if file_analysis["re_read_intervals"]:
            report.append("\n### Files Re-Read (Potential Context Loss)")
            for interval in file_analysis["re_read_intervals"]:
                file_path = interval["file"]
                num_accesses = interval["num_accesses"]
                interval_ms = interval["interval_ms"]
                report.append(
                    f"- `{file_path}`: {num_accesses} times, "
                    f"{interval_ms:.0f}ms between first and second read"
                )

        report.append("\n## Discovery Metrics")
        if "search_to_read_delay_ms" in discovery_metrics:
            delay_ms = discovery_metrics["search_to_read_delay_ms"]
            report.append(f"- Time from first search to first read: {delay_ms:.0f}ms")

        return "\n".join(report)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python session_analyzer.py <session.jsonl>")
        print("\nExample:")
        example_path = (
            "~/.claude/projects/-Users-henruwang-Code-reaction-requests/"
            "1ea0f7d8-716c-4383-8ecd-4b4cbb0b72a5.jsonl"
        )
        print(f"  python session_analyzer.py {example_path}")
        sys.exit(1)

    session_file = Path(sys.argv[1])
    if not session_file.exists():
        print(f"Error: Session file not found: {session_file}")
        sys.exit(1)

    analyzer = SessionAnalyzer(session_file)
    report = analyzer.generate_report()
    print(report)


if __name__ == "__main__":
    main()
