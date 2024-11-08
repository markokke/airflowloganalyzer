from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import json
from models.mongo_encoder import MongoJSONEncoder

class ReportGenerator:
    """
    Handles the generation, formatting, and saving of analysis reports.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.output_config = config.get('output', {})
    
    def format_analysis(self, analysis_response: Dict, analysis_data: Dict = None) -> str:
        """
        Format the complete analysis into a readable report.
        
        Args:
            analysis_response: Response from the Ollama model
            analysis_data: Additional analysis data including patterns and recommendations
            
        Returns:
            Formatted report as a string
        """
        formatted = []
        
        # Report Header
        formatted.extend([
            "=" * 80,
            "AIRFLOW LOG ANALYSIS REPORT",
            "=" * 80,
            "",
            f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ])

        # Add Airflow Context Section
        if analysis_data and 'patterns' in analysis_data:
            context_matches = analysis_data['patterns'].get('airflow_context', {})
            if context_matches:
                formatted.extend([
                    "-" * 40,
                    "AIRFLOW CONTEXT",
                    "-" * 40
                ])
                
                # Get the first match as it contains the context
                first_match = next(iter(next(iter(context_matches.values()), [])), None)
                if first_match:
                    context = first_match.get('content', '')
                    # Format each context variable on its own line
                    formatted.extend([
                        line.strip()
                        for line in context.split(' ')
                        if line.startswith('AIRFLOW_CTX_')
                    ])
                formatted.append("")
                
            formatted.extend([
                "-" * 40,
                "ANALYSIS SUMMARY",
                "-" * 40,
                f"Total Logs Analyzed: {analysis_data['summary'].get('total_logs_analyzed', 'N/A')}",
                f"Time Period: {analysis_data['summary'].get('time_period', 'N/A')}",
                f"Total Issues Found: {analysis_data['summary'].get('total_issues_found', 'N/A')}",
                ""
            ])

        # Detected Patterns Section
        if analysis_data and 'patterns' in analysis_data:
            formatted.extend([
                "-" * 40,
                "DETECTED PATTERNS",
                "-" * 40
            ])
            
            for pattern_type, severities in analysis_data['patterns'].items():
                if isinstance(severities, dict):  # Ensure it's a dictionary
                    formatted.append(f"\n{pattern_type.replace('_', ' ').title()}:")
                    
                    for severity, issues in severities.items():
                        if isinstance(issues, list) and issues:  # Ensure it's a non-empty list
                            formatted.append(f"\n  {severity.upper()} Severity Issues:")
                            
                            for issue in issues:
                                # Add the main issue content
                                formatted.append(f"    - {issue.get('content', 'No content available')}")
                                
                                # Add frequency if available
                                if 'frequency' in issue:
                                    formatted.append(f"      Frequency: {issue['frequency']} occurrences")
                                    
                                # Add context if available
                                if 'context' in issue and issue['context']:
                                    formatted.append(f"      Context: {issue['context']}")
                                    
                                # Add timestamp if available
                                if 'timestamp' in issue:
                                    formatted.append(f"      Time: {issue['timestamp']}")
            
            formatted.append("")

        # AI Analysis Section
        if analysis_response and 'response' in analysis_response:
            formatted.extend([
                "-" * 40,
                "AI ANALYSIS",
                "-" * 40
            ])
            
            # Process AI analysis response
            sections = analysis_response['response'].split('\n')
            current_section = []
            
            for line in sections:
                if line.strip():  # Skip empty lines
                    if line.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                        # If we have content in current section, add it
                        if current_section:
                            formatted.extend(current_section)
                            formatted.append("")
                            current_section = []
                        # Start new section
                        formatted.append(line.strip())
                    else:
                        # Add to current section with proper indentation
                        current_section.append("  " + line.strip())
            
            # Add any remaining content
            if current_section:
                formatted.extend(current_section)
            
            formatted.append("")

        # Recommendations Section
        if analysis_data and 'recommendations' in analysis_data:
            formatted.extend([
                "-" * 40,
                "RECOMMENDATIONS",
                "-" * 40
            ])
            
            for rec in analysis_data['recommendations']:
                formatted.extend([
                    f"Issue: {rec.get('issue', 'Unknown Issue')} (Severity: {rec.get('severity', 'Unknown')})",
                    f"Count: {rec.get('count', 'N/A')}"
                ])
                
                if rec.get('suggestion'):
                    formatted.extend([
                        "Suggestion:",
                        "  " + rec['suggestion'].replace("\n", "\n  ")
                    ])
                    
                if rec.get('sample'):
                    formatted.extend([
                        "Sample:",
                        "  " + rec['sample'][:200] + ("..." if len(rec['sample']) > 200 else "")
                    ])
                    
                formatted.append("")

        # Analysis Metadata Section
        if any(key in analysis_response for key in ['eval_count', 'eval_duration', 'prompt_eval_count']):
            formatted.extend([
                "-" * 40,
                "ANALYSIS METADATA",
                "-" * 40
            ])
            
            if 'eval_count' in analysis_response:
                formatted.append(f"Eval Count: {analysis_response['eval_count']}")
            if 'eval_duration' in analysis_response:
                formatted.append(f"Duration: {analysis_response['eval_duration']} ms")
            if 'prompt_eval_count' in analysis_response:
                formatted.append(f"Prompt Eval Count: {analysis_response['prompt_eval_count']}")
            
            formatted.append("")

        # Join all sections with newlines and return
        return "\n".join(formatted)

    def _create_section_header(self, title: str) -> str:
        """Create a formatted section header."""
        return f"{'-' * 40}\n{title}\n{'-' * 40}"

    def _format_summary(self, summary: Dict) -> str:
        """Format the analysis summary section."""
        lines = [
            f"Total Logs Analyzed: {summary.get('total_logs_analyzed', 'N/A')}",
            f"Time Period: {summary.get('time_period', 'N/A')}",
            f"Total Issues Found: {summary.get('total_issues_found', 'N/A')}"
        ]
        
        # Add any additional summary metrics
        for key, value in summary.items():
            if key not in ['total_logs_analyzed', 'time_period', 'total_issues_found']:
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
                
        return "\n".join(lines)

    def _format_patterns(self, patterns: Dict) -> str:
        """Format the detected patterns section."""
        formatted = []
        
        for pattern_type, severities in patterns.items():
            pattern_lines = [f"\n{pattern_type.replace('_', ' ').title()}:"]
            
            for severity, issues in severities.items():
                pattern_lines.append(f"\n  {severity.upper()} Severity Issues:")
                
                for issue in issues:
                    pattern_lines.append(f"    - {issue['content']}")
                    if 'frequency' in issue:
                        pattern_lines.append(f"      Frequency: {issue['frequency']} occurrences")
                    if 'context' in issue and issue['context']:
                        pattern_lines.append(f"      Context: {issue['context']}")
                        
            formatted.extend(pattern_lines)
            
        return "\n".join(formatted)

    def _format_ai_analysis(self, response_text: str) -> str:
        """Format the AI analysis section with proper indentation and structure."""
        sections = response_text.split('\n')
        formatted = []
        current_section = []
        
        for line in sections:
            if line.strip():  # Skip empty lines
                if line.startswith(('1.', '2.', '3.', '4.', '5.')):
                    # If we have content in current section, add it
                    if current_section:
                        formatted.extend(current_section)
                        formatted.append("")
                        current_section = []
                    # Start new section
                    formatted.append(line.strip())
                else:
                    # Add to current section with proper indentation
                    current_section.append("  " + line.strip())
        
        # Add any remaining content
        if current_section:
            formatted.extend(current_section)
            
        return "\n".join(formatted)

    def _format_recommendations(self, recommendations: List[Dict]) -> str:
        """Format the recommendations section."""
        formatted = []
        
        for rec in recommendations:
            formatted.extend([
                f"Issue: {rec['issue']} (Severity: {rec['severity']})",
                f"Count: {rec.get('count', 'N/A')}",
                f"Suggestion: {rec['suggestion']}",
                ""
            ])
            
            if rec.get('sample'):
                formatted.append(f"Sample: {rec['sample']}")
                formatted.append("")
                
        return "\n".join(formatted)

    def _has_metadata(self, response: Dict) -> bool:
        """Check if response contains metadata."""
        metadata_fields = ['eval_count', 'eval_duration', 'load_time', 'prompt_eval_count']
        return any(field in response for field in metadata_fields)

    def _format_metadata(self, response: Dict) -> str:
        """Format the metadata section."""
        metadata_lines = []
        
        if 'eval_count' in response:
            metadata_lines.append(f"Eval Count: {response['eval_count']}")
        if 'eval_duration' in response:
            metadata_lines.append(f"Duration: {response['eval_duration']} ms")
        if 'load_time' in response:
            metadata_lines.append(f"Load Time: {response['load_time']} ms")
        if 'prompt_eval_count' in response:
            metadata_lines.append(f"Prompt Eval Count: {response['prompt_eval_count']}")
            
        return "\n".join(metadata_lines)

    def save_report(self, formatted_analysis: str, output_file: Optional[str] = None) -> Path:
        """
        Save the formatted analysis report to a file.
        
        Args:
            formatted_analysis: The formatted report string
            output_file: Optional custom filename
            
        Returns:
            Path to the saved report file
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"airflow_analysis_report_{timestamp}.txt"

        output_path = self._get_output_path(output_file)
        self._save_text(formatted_analysis, output_path)
        return output_path

    def save_outputs(self, analysis: Dict, model_request: Dict):
        """Save all analysis outputs."""
        #timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save analysis results
        if self.output_config.get('save_analysis'):
            path = self._get_output_path(self.output_config['analysis_file'])
            self._save_json(analysis, path)  # Remove the indent parameter
            
        # Save system prompt
        #if self.output_config.get('save_prompt'):
        #    path = self._get_output_path(self.output_config['prompt_file'])
        #    self._save_text(system_prompt, path)
            
        # Save model request
        if self.output_config.get('save_model_request'):
            path = self._get_output_path(self.output_config['model_request_file'])
            self._save_json(model_request, path)  # Remove the indent parameter

    def _get_output_path(self, filename: Union[str, Path]) -> Path:
        """
        Get the output path with optional timestamp.
        
        Args:
            filename: Base filename or path
            
        Returns:
            Complete output path
        """
        path = Path(filename)
        if self.output_config.get('include_timestamp', False):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")
        return path

    def _save_json(self, data: Dict, path: Path, indent: int = None):
        """
        Save dictionary as JSON with proper encoding and formatting.
        
        Args:
            data: Dictionary to save
            path: Path to save to
            indent: Number of spaces for indentation (optional)
        """
        if indent is None:
            indent = self.config['output'].get('json_indent', 2)
            
        with open(path, 'w') as f:
            json.dump(
                data, 
                f, 
                indent=indent,
                cls=MongoJSONEncoder
            )

    def _save_text(self, text: str, path: Path):
        """Save text content to file."""
        with open(path, 'w') as f:
            f.write(text)