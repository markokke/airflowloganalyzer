import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from models.mongo_encoder import MongoJSONEncoder


class ReportGenerator:
    def __init__(self, config: Dict):
        self.config = config
        self.output_config = config.get("output", {})
        self.logger = logging.getLogger("airflow_log_analyzer")
        self._ensure_output_directories()

    def _ensure_output_directories(self):
        """Create output directories if they don't exist."""
        base_dir = Path(self.output_config["output_dir"])
        subdirs = self.output_config.get("subdirectories", {})

        # Create base directory
        base_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        for subdir in subdirs.values():
            (base_dir / subdir).mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Initialized output directories in {base_dir}")

    def _get_output_path(self, filename: Union[str, Path], subdir: str = None) -> Path:
        """Get the output path with optional timestamp and subdirectory."""
        # Get base directory
        base_dir = Path(self.output_config["output_dir"])

        # Add subdirectory if specified
        if subdir:
            base_dir = base_dir / self.output_config["subdirectories"].get(
                subdir, subdir
            )

        # Process filename
        path = Path(filename)
        if self.output_config.get("include_timestamp", False):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_filename = f"{path.stem}_{timestamp}{path.suffix}"
        else:
            new_filename = path.name

        return base_dir / new_filename

    def _save_json(self, data: Dict, path: Path):
        """Save dictionary as JSON with proper encoding and formatting."""
        self.logger.debug(f"Saving JSON to {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                data,
                f,
                indent=self.config["output"].get("json_indent", 2),
                cls=MongoJSONEncoder,
            )
        self.logger.info(f"Saved JSON to {path}")

    def _save_text(self, text: str, path: Path):
        """Save text content to file."""
        self.logger.debug(f"Saving text to {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        self.logger.info(f"Saved text to {path}")

    def save_outputs(self, analysis: Dict, model_request: Dict):
        """Save all analysis outputs to their respective directories."""
        self.logger.debug("Saving analysis outputs")

        # Save analysis results
        if self.output_config.get("save_analysis"):
            json_path = self._get_output_path(
                self.output_config["analysis_file"], subdir="json"
            )
            self.logger.debug(f"Saving analysis to {json_path}")
            self._save_json(analysis, json_path)

        # Save model request
        if self.output_config.get("save_model_request"):
            request_path = self._get_output_path(
                self.output_config["model_request_file"], subdir="json"
            )
            self.logger.debug(f"Saving model request to {request_path}")
            self._save_json(model_request, request_path)

    def save_report(
        self, formatted_analysis: str, filename: Optional[str] = None
    ) -> Path:
        """Save the formatted analysis report to a file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"airflow_analysis_report_{timestamp}.txt"

        # Use reports subdirectory
        output_path = self._get_output_path(filename, subdir="reports")
        self._save_text(formatted_analysis, output_path)
        return output_path

    def generate_individual_reports(self, analysis_results: List[Dict]) -> List[Path]:
        """Generate separate reports for each analyzed log in the reports directory."""
        self.logger.info("Generating individual reports")
        report_paths = []

        # Create reports directory if it doesn't exist
        base_dir = Path(self.output_config["output_dir"])
        reports_dir = base_dir / self.output_config["subdirectories"]["reports"]
        reports_dir.mkdir(parents=True, exist_ok=True)

        for result in analysis_results:
            log_id = result["log_id"]
            timestamp = result["timestamp"]

            # Format the analysis data for this log
            analysis_data = {
                "summary": {
                    "log_id": log_id,
                    "timestamp": timestamp,
                    "total_issues_found": sum(
                        len(matches) for matches in result["pattern_matches"].values()
                    ),
                },
                "patterns": result["pattern_matches"],
                "recommendations": self._generate_recommendations(
                    result["pattern_matches"]
                ),
            }

            # Format the report
            formatted_report = self.format_analysis(result["analysis"], analysis_data)

            # Generate unique filename for this log
            timestamp_str = datetime.fromisoformat(
                str(timestamp).replace("Z", "+00:00")
            ).strftime("%Y%m%d_%H%M%S")
            filename = f"airflow_analysis_log_{timestamp_str}_{log_id[:8]}.txt"

            # Create full path in reports directory
            report_path = reports_dir / filename

            # Save the report
            self.logger.info(f"Saving report to: {report_path}")
            with open(report_path, "w") as f:
                f.write(formatted_report)

            report_paths.append(report_path)
            self.logger.info(f"Saved report for log {log_id}")

        self.logger.info(f"Generated {len(report_paths)} reports in {reports_dir}")
        return report_paths

    def _generate_recommendations(self, pattern_matches: Dict) -> List[Dict]:
        """Generate recommendations based on pattern matches."""
        recommendations = []

        for pattern_type, matches in pattern_matches.items():
            if matches:  # If there are matches for this pattern
                # Count occurrences by severity
                severity_counts = {}
                for match in matches:
                    severity = match["severity"]
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1

                # Generate recommendation for each severity level
                for severity, count in severity_counts.items():
                    recommendations.append(
                        {
                            "issue": pattern_type.replace("_", " ").title(),
                            "severity": severity,
                            "count": count,
                            "suggestion": self._get_recommendation_for_pattern(
                                pattern_type, severity
                            ),
                        }
                    )

        return recommendations

    def _get_recommendation_for_pattern(self, pattern_type: str, severity: str) -> str:
        """Get a recommendation based on pattern type and severity."""
        # Add your recommendation logic here based on pattern type and severity
        recommendations = {
            "test_failure": {
                "high": "Review and fix failing tests immediately. Check data quality and test conditions.",
                "medium": "Investigate test failures during next maintenance window.",
            },
            "error": {
                "high": "Immediate investigation required. Check system logs and error messages.",
                "medium": "Monitor these errors and investigate during next maintenance window.",
            },
            "pod_status": {
                "high": "Review pod configurations and resource allocations immediately.",
                "medium": "Monitor pod lifecycle events and investigate resource usage patterns.",
            },
        }

        # Get recommendation or use default
        pattern_recs = recommendations.get(pattern_type, {})
        return pattern_recs.get(
            severity, f"Review {pattern_type} issues with {severity} severity"
        )

    def format_analysis(self, model_response: Dict, analysis_data: Dict) -> str:
        """Format the analysis results into a readable report."""
        formatted = []

        # Extract DAG ID from patterns with debug logging
        dag_id = "Unknown"
        self.logger.debug("Trying to extract DAG ID from analysis data")

        # First try to find DAG ID in the raw log content
        if "log_info" in analysis_data:
            log_content = analysis_data["log_info"]
            self.logger.debug("Checking raw log content for DAG ID")

            # Try to find AIRFLOW_CTX_DAG_ID in the raw log
            if "AIRFLOW_CTX_DAG_ID=" in log_content:
                try:
                    # Extract between AIRFLOW_CTX_DAG_ID=' and next '
                    dag_id = log_content.split("AIRFLOW_CTX_DAG_ID='")[1].split("'")[0]
                    self.logger.debug(f"Found DAG ID in raw log: {dag_id}")
                except (IndexError, AttributeError):
                    self.logger.debug("Failed to extract DAG ID from raw log")

            if "AIRFLOW_CTX_DAG_RUN_ID=" in log_content:
                try:
                    dag_run_id = log_content.split("AIRFLOW_CTX_DAG_RUN_ID='")[1].split(
                        "'"
                    )[0]
                    self.logger.debug(
                        f"Found DAG RUN ID in pattern match: {dag_run_id}"
                    )
                except (IndexError, AttributeError):
                    self.logger.debug("Failed to extract DAG RUN ID from raw log")

            if "AIRFLOW_CTX_TASK_ID=" in log_content:
                try:
                    task_id = log_content.split("AIRFLOW_CTX_TASK_ID='")[1].split("'")[
                        0
                    ]
                    self.logger.debug(f"Found TASK ID in pattern match: {task_id}")

                except (IndexError, AttributeError):
                    self.logger.debug("Failed to extract TASK ID from raw log")

            if "AIRFLOW_CTX_TRY_NUMBER=" in log_content:
                try:
                    try_number = log_content.split("AIRFLOW_CTX_TRY_NUMBER='")[1].split(
                        "'"
                    )[0]
                    self.logger.debug(
                        f"Found TRY NUMBER in pattern match: {try_number}"
                    )
                except (IndexError, AttributeError):
                    self.logger.debug("Failed to extract TRY NUMBER from raw log")

        # If not found in raw log, try pattern matches as backup
        if dag_id == "Unknown" and "patterns" in analysis_data:
            for pattern_type, matches in analysis_data["patterns"].items():
                for match in matches:
                    content = match.get("content", "")
                    if "AIRFLOW_CTX_DAG_ID=" in content:
                        try:
                            dag_id = content.split("AIRFLOW_CTX_DAG_ID='")[1].split(
                                "'"
                            )[0]
                            self.logger.debug(
                                f"Found DAG ID in pattern match: {dag_id}"
                            )
                            break
                        except (IndexError, AttributeError):
                            continue

        # Report Header
        formatted.extend(
            [
                "=" * 80,
                "AIRFLOW LOG ANALYSIS REPORT",
                "=" * 80,
                "",
                f"    DAG ID: {dag_id}",
                f"DAG RUN ID: {dag_run_id}",
                f"   TASK ID: {task_id}",
                f"TRY NUMBER: {try_number}",
                f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Log ID: {analysis_data['summary']['log_id']}",
                f"Log Timestamp: {analysis_data['summary']['timestamp']}",
                "",
            ]
        )

        # Add debug info about DAG ID extraction if it's unknown
        if dag_id == "Unknown":
            self.logger.warning(
                f"Could not extract DAG ID for log {analysis_data['summary']['log_id']}"
            )
            self.logger.debug(
                "Available patterns: " + ", ".join(analysis_data["patterns"].keys())
            )

        # Add Pattern Matches Section
        if analysis_data["patterns"]:
            formatted.extend(["-" * 40, "DETECTED PATTERN SNIPPETS", "-" * 40, ""])

            for pattern_type, matches in analysis_data["patterns"].items():
                formatted.append(f"{pattern_type}:")
                for match in matches:
                    formatted.extend(
                        [
                            f"  {match['content']}",  # Show full content without truncation
                            "",
                        ]
                    )

        # Add Analysis Results Section
        if model_response:
            formatted.extend(["-" * 40, "AI ANALYSIS", "-" * 40, ""])

            for analysis_type, analysis in model_response.items():
                if analysis and isinstance(analysis, dict) and "response" in analysis:
                    formatted.extend(
                        [
                            f"{analysis_type.upper().replace('_', ' ')}:",
                            "-" * len(analysis_type),
                            analysis.get("response", "No analysis available"),
                            "",
                        ]
                    )
                else:
                    self.logger.warning(
                        f"Unexpected analysis format for {analysis_type}: {analysis}"
                    )
                    formatted.extend(
                        [
                            f"{analysis_type.upper().replace('_', ' ')}:",
                            "-" * len(analysis_type),
                            "Analysis data not in expected format",
                            "",
                        ]
                    )

        # Add Recommendations Section
        if analysis_data.get("recommendations"):
            formatted.extend(["-" * 40, "RECOMMENDATIONS", "-" * 40, ""])

            for rec in analysis_data["recommendations"]:
                formatted.extend(
                    [
                        f"Issue: {rec.get('issue', 'Unknown')} (Severity: {rec.get('severity', 'Unknown')})",
                        f"Count: {rec.get('count', 'N/A')}",
                        f"Suggestion: {rec.get('suggestion', 'No suggestion available')}",
                        "",
                    ]
                )

        # Add Summary Section
        formatted.extend(
            [
                "-" * 40,
                "SUMMARY",
                "-" * 40,
                f"Total Issues Found: {analysis_data['summary']['total_issues_found']}",
            ]
        )

        # Add pattern type counts to summary
        pattern_counts = {}
        for pattern_type, matches in analysis_data["patterns"].items():
            pattern_counts[pattern_type] = len(matches)

        if pattern_counts:
            formatted.extend(["", "Pattern Counts:"])
            for pattern_type, count in pattern_counts.items():
                if count > 0:  # Only show patterns that had matches
                    formatted.append(f"- {pattern_type}: {count} matches")

        # Add severity summary if available
        severity_counts = defaultdict(int)
        for pattern_type, matches in analysis_data["patterns"].items():
            for match in matches:
                severity_counts[match.get("severity", "unknown")] += 1

        if severity_counts:
            formatted.extend(["", "Severity Distribution:"])
            for severity, count in severity_counts.items():
                formatted.append(f"- {severity.upper()}: {count} issues")

        formatted.append("")  # Add final newline

        return "\n".join(formatted)
