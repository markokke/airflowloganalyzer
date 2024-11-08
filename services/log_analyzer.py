import yaml
import json
import logging.config
from collections import defaultdict
import re
from typing import Dict, List
import pymongo
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from pathlib import Path
from prompts import AIRFLOW_LOG_ANALYSIS_PROMPT
from models.mongo_encoder import MongoJSONEncoder 
from clients.ollama_client import OllamaClient

class LogAnalyzer:
    def __init__(self, config: Dict):
        """Initialize the LogAnalyzer with configuration."""
        self.config = config
        logging.config.dictConfig(self.config['logging'])
        self.logger = logging.getLogger('airflow_log_analyzer')
        self.init_mongodb()
        
        # Add error checking for patterns
        if 'analysis' not in self.config:
            raise ValueError("Analysis configuration is missing from config")
        if 'patterns' not in self.config['analysis']:
            raise ValueError("Patterns configuration is missing from analysis config")
            
        # Initialize patterns with logging
        try:
            self.patterns = {}
            for name, pattern in self.config['analysis']['patterns'].items():
                if not isinstance(pattern, dict):
                    self.logger.warning(f"Pattern '{name}' is not properly configured")
                    continue
                if 'regex' not in pattern:
                    self.logger.warning(f"Pattern '{name}' is missing regex configuration")
                    continue
                self.patterns[name] = pattern['regex']
                self.logger.debug(f"Initialized pattern '{name}' with regex: {pattern['regex']}")
        except Exception as e:
            self.logger.error(f"Error initializing patterns: {str(e)}")
            raise
            
        self.analysis_results = {}

    def _load_config(self, config_path: str) -> Dict:
        with open(config_path) as f:
            return yaml.safe_load(f)
            
    def init_mongodb(self):
        """Initialize MongoDB connection with better error handling."""
        mongo_config = self.config.get('mongodb')
        if not mongo_config:
            raise ValueError("MongoDB configuration is missing from config")
            
        try:
            self.logger.debug(f"Attempting to connect to MongoDB at {mongo_config['uri']}")
            
            self.client = pymongo.MongoClient(
                mongo_config['uri'],
                serverSelectionTimeoutMS=mongo_config['timeout_ms'],
                maxPoolSize=mongo_config['max_pool_size']
            )
            
            # Test the connection
            self.client.server_info()
            self.logger.info("Successfully connected to MongoDB")
            
            # Get database and collection
            self.db = self.client[mongo_config['db_name']]
            self.collection = self.db[mongo_config['collection_name']]
            
            # Verify collection exists and has documents
            doc_count = self.collection.count_documents({})
            self.logger.info(f"Found {doc_count} documents in collection {mongo_config['collection_name']}")
            
            if doc_count == 0:
                self.logger.warning(f"Collection {mongo_config['collection_name']} is empty")
                
        except pymongo.errors.ServerSelectionTimeoutError as e:
            self.logger.error(f"Could not connect to MongoDB server: {str(e)}")
            raise
        except pymongo.errors.OperationFailure as e:
            self.logger.error(f"MongoDB authentication failed: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize MongoDB: {str(e)}")
            raise
        
    def analyze_logs(self) -> Dict:
        """Primary analysis method returning pattern results."""
        # Add error checking for config
        if 'analysis' not in self.config:
            self.logger.error("Missing 'analysis' section in configuration")
            raise KeyError("Missing 'analysis' section in configuration")
        if 'days_back' not in self.config['analysis']:
            self.logger.error("Missing 'days_back' in analysis configuration")
            raise KeyError("Missing 'days_back' in analysis configuration")

        days_back = self.config['analysis']['days_back']
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cutoff_object_id = ObjectId.from_datetime(cutoff_date)
        
        self.logger.info(f"Analyzing logs from the last {days_back} days")
        
        # Count total logs
        total_logs = self.collection.count_documents({"_id": {"$gte": cutoff_object_id}})
        self.logger.info(f"Found {total_logs} log entries to analyze")
        
        # Query logs
        logs = self.collection.find(
            {"_id": {"$gte": cutoff_object_id}},
            batch_size=self.config['mongodb']['batch_size']
        )
        
        # Add this debug statement
        #first_doc = self.collection.find_one({"_id": {"$gte": cutoff_object_id}})
        #if first_doc:
        #    self.logger.debug("Document structure (without LogInfo):")
        #    doc_without_loginfo = {k: v for k, v in first_doc.items() if k != 'LogInfo'}
        #    self.logger.debug(json.dumps(doc_without_loginfo, default=str, indent=2))
        #    self.logger.debug("First 100 characters of LogInfo:")
        #    loginfo = first_doc.get('LogInfo', 'No LogInfo found')
        #    self.logger.debug(loginfo[:100] + "..." if len(loginfo) > 100 else loginfo)
        
        
        # Process patterns
        results = {
            pattern: defaultdict(list) 
            for pattern in self.patterns.keys()
        }
        
        # Initialize pattern results dictionary for specific analyses
        pattern_results = defaultdict(list)
        
        processed_logs = 0
        for log in logs:
            processed_logs += 1
            log_info = log['LogInfo']
            for pattern_name, pattern_config in self.config['analysis']['patterns'].items():
                # Extract pattern and get the matches
                matches = self._extract_pattern(
                    pattern_name,
                    pattern_config,
                    log_info,
                    results[pattern_name]
                )
                
                # Group by pattern type using only the matched content
                if matches and pattern_config.get('severity') in ['critical', 'high']:
                    pattern_type = self._get_pattern_type(pattern_name)
                    for match_content in matches:
                        pattern_results[pattern_type].append({
                            'content': match_content,  # Only the matched content
                            'pattern': pattern_name,
                            'severity': pattern_config.get('severity')
                        })
        
        # Store actual counts
        self.total_logs = total_logs
        self.processed_logs = processed_logs
        
        # Process regular results
        self.analysis_results = self._process_results(results)
        
        # Initialize Ollama client
        ollama_client = OllamaClient(model_name=self.config['model']['name'], config=self.config)
        
        # Perform specific pattern analyses
        analysis_results = {}
        
        # Error patterns
        if pattern_results.get('error'):
            lootatme = pattern_results['error']
            error_analysis = ollama_client.ask_model(pattern_results['error'], prompt_type='error')
            analysis_results['error_analysis'] = error_analysis
            
        # Test failure patterns
        if pattern_results.get('test_result'):
            test_analysis = ollama_client.ask_model(pattern_results['test_result'], prompt_type='test')
            analysis_results['test_analysis'] = test_analysis

        # Performance patterns
        if pattern_results.get('performance'):
            perf_analysis = ollama_client.ask_model(pattern_results['performance'], prompt_type='performance')
            analysis_results['performance_analysis'] = perf_analysis
            
        # Pod status patterns
        if pattern_results.get('pod_status'):
            pod_analysis = ollama_client.ask_model(pattern_results['pod_status'], prompt_type='pod')
            analysis_results['pod_analysis'] = pod_analysis
            
        # DBT patterns
        dbt_patterns = [p for p in pattern_results.keys() if 'dbt' in p.lower()]
        if dbt_patterns:
            # Combine all DBT-related pattern matches
            all_dbt_matches = []
            for pattern in dbt_patterns:
                all_dbt_matches.extend(pattern_results[pattern])
            dbt_analysis = ollama_client.ask_model(all_dbt_matches, prompt_type='dbt')
            analysis_results['dbt_analysis'] = dbt_analysis

        # Add debug log for pattern results before analysis
        self.logger.debug("Pattern matches found:")
        for pattern_type, matches in pattern_results.items():
            self.logger.debug(f"{pattern_type}: {len(matches)} matches")
        
        # Store all results
        self.pattern_analysis = analysis_results
        
        # Before the return statement
        final_results = {
            'pattern_matches': self.analysis_results,
            'prompt_analysis': analysis_results,
            'counts': {
                'total_logs': total_logs,
                'processed_logs': processed_logs,
                'pattern_matches': sum(
                    len(severity_data)
                    for pattern_data in self.analysis_results.values()
                    if isinstance(pattern_data, dict)
                    for severity_data in pattern_data.values()
                    if isinstance(severity_data, list)
                )
            }
        }
        
        self.logger.debug("Final results summary:")
        self.logger.debug(f"- Pattern matches: {len(self.analysis_results)}")
        self.logger.debug(f"- Prompt analyses: {len(analysis_results)}")
        self.logger.debug(f"- Total logs processed: {processed_logs}")
        
        return final_results
        
    def _get_pattern_type(self, pattern_name: str) -> str:
        """
        Map pattern names to their types for prompt selection.
        
        Args:
            pattern_name: Name of the pattern to categorize
            
        Returns:
            String indicating the pattern type (error, test_result, etc.)
        """
        pattern_mappings = {
            'error': ['error', 'exception', 'failure', 'failed'],
            'test_result': ['test', 'assertion', 'validate'],
            'performance': ['performance', 'duration', 'latency', 'timeout'],
            'pod_status': ['pod', 'container', 'kubernetes'],
            'dbt': ['dbt', 'data_build', 'model'],
            'scheduler': ['scheduler', 'scheduling'],
            'database': ['database', 'postgres', 'mysql', 'sqlite'],
            'airflow_task': ['task', 'operator'],
            'dag_run': ['dag', 'run', 'trigger']
        }
        
        pattern_name_lower = pattern_name.lower()
        
        # Check each pattern type for matching keywords
        for pattern_type, keywords in pattern_mappings.items():
            if any(keyword in pattern_name_lower for keyword in keywords):
                return pattern_type
                
        # If no specific match is found, return 'main' as default
        return 'main'        
    
    def get_log_counts(self) -> Dict[str, int]:
        """Get counts of logs analyzed and patterns found."""
        return {
            'total_logs': getattr(self, 'total_logs', 0),
            'processed_logs': getattr(self, 'processed_logs', 0),
            'pattern_matches': sum(
                len(severity_data)
                for pattern_data in self.analysis_results.values()
                if isinstance(pattern_data, dict)
                for severity_data in pattern_data.values()
                if isinstance(severity_data, list)
            )
        }    
    
    def _extract_pattern(self, pattern_name: str, pattern_config: Dict, log_info: str, results: Dict):
        """Extract patterns from log info based on configuration"""
        lines = log_info.split('\n')
        matched_contents = []
        match_count = 0
        
        # Regex for timestamp pattern
        timestamp_pattern = r'^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{4})\]'
        
        for line in lines:
            # Skip lines without timestamp
            timestamp_match = re.match(timestamp_pattern, line)
            if not timestamp_match:
                continue
                
            current_timestamp = datetime.strptime(timestamp_match.group(1), '%Y-%m-%dT%H:%M:%S.%f%z')
            
            # Skip INFO lines EXCEPT for test failures
            if " INFO - " in line and pattern_name != "test_failure":
                continue
                
            matches = re.finditer(pattern_config['regex'], line)
            
            for match in matches:
                match_count += 1
                # Get context if configured
                if pattern_config.get('include_context'):
                    content = self._get_context(
                        line,
                        match,
                        self.config['analysis']['context_lines']
                    )
                else:
                    content = match.group(0)
                    
                # Store result with metadata using the log line's timestamp
                results[pattern_config['severity']].append({
                    'content': content,
                    'pattern': pattern_name,
                    'timestamp': current_timestamp
                })
                matched_contents.append(content)
        
        if match_count > 0:
            self.logger.debug(f"Found {match_count} matches for '{pattern_name}'")
            
        return matched_contents
        
    def _get_context(self, log_info: str, match, context_lines: int) -> str:
        """Get surrounding context lines for a match"""
        lines = log_info.split('\n')
        line_num = len(log_info[:match.start()].split('\n'))
        
        start = max(0, line_num - context_lines)
        end = min(len(lines), line_num + context_lines + 1)
        
        return '\n'.join(lines[start:end])
        
    def _process_results(self, results: Dict) -> Dict:
        """Process and filter analysis results"""
        min_occurrences = self.config['analysis']['min_pattern_occurrences']
        
        processed = {}
        for pattern, pattern_results in results.items():
            processed[pattern] = {
                severity: results
                for severity, results in pattern_results.items()
                if len(results) >= min_occurrences
            }
            if processed[pattern]:
                # Instead of debug logging, write to JSON file
                pattern_file = f"pattern_{pattern}_matches.json"
                with open(pattern_file, 'w') as f:
                    json.dump(processed[pattern], f, indent=2, cls=MongoJSONEncoder)
                
        return processed

    def _get_recommendation_for_pattern(self, pattern_type: str, severity: str) -> str:
        """Get specific recommendation based on pattern type and severity"""
        recommendations = {
            'error': {
                'critical': 'CRITICAL: Immediate investigation required. Review logs and system resources.',
                'high': 'HIGH: Urgent review needed. Check error patterns and implement fixes.'
            },
            'warning': {
                'critical': 'Review warning patterns for potential system issues.',
                'high': 'Analyze warning trends and implement preventive measures.',
                'medium': 'Monitor these warnings for potential escalation.'
            },
            'test_result': {
                'critical': 'CRITICAL: Multiple test failures detected. Immediate investigation needed.',
                'high': 'HIGH: Test failures require attention. Review test cases and data quality.',
                'medium': 'Review test results and update test criteria as needed.'
            },
            'pod_status': {
                'critical': 'CRITICAL: Kubernetes pod issues detected. Check cluster health.',
                'high': 'HIGH: Review pod configurations and resource allocations.',
                'medium': 'Monitor pod lifecycle and resource usage patterns.'
            },
            'performance': {
                'critical': 'CRITICAL: Severe performance degradation. Check system resources.',
                'high': 'HIGH: Performance issues detected. Review resource allocation.',
                'medium': 'Monitor system performance metrics and trends.'
            },
            'airflow_task': {
                'critical': 'CRITICAL: Task execution issues detected. Check DAG configuration.',
                'high': 'HIGH: Review task dependencies and resource requirements.',
                'medium': 'Monitor task execution patterns and optimize as needed.'
            },
            'dag_run': {
                'critical': 'CRITICAL: DAG execution failures detected. Check scheduler logs.',
                'high': 'HIGH: Review DAG configuration and dependencies.',
                'medium': 'Monitor DAG performance and execution patterns.'
            },
            'scheduler': {
                'critical': 'CRITICAL: Scheduler issues detected. Check Airflow configuration.',
                'high': 'HIGH: Review scheduler logs and settings.',
                'medium': 'Monitor scheduler health and performance.'
            },
            'database': {
                'critical': 'CRITICAL: Database issues detected. Check connection and performance.',
                'high': 'HIGH: Review database logs and connection settings.',
                'medium': 'Monitor database performance and connection patterns.'
            }
        }

        # Get pattern-specific recommendations
        pattern_recommendations = recommendations.get(pattern_type, {})
        
        # Get severity-specific recommendation or use a default
        recommendation = pattern_recommendations.get(severity, 
            f"Review and address {pattern_type.replace('_', ' ')} issues based on {severity} severity level.")
        
        # Add universal recommendations based on severity
        if severity == 'critical':
            recommendation += "\nRecommended Actions:\n" + \
                "- Immediate investigation required\n" + \
                "- Notify relevant team members\n" + \
                "- Consider system health impact\n" + \
                "- Document findings and actions taken"
        elif severity == 'high':
            recommendation += "\nRecommended Actions:\n" + \
                "- Schedule urgent review\n" + \
                "- Monitor for recurrence\n" + \
                "- Plan remediation steps"
        elif severity == 'medium':
            recommendation += "\nRecommended Actions:\n" + \
                "- Review during next maintenance\n" + \
                "- Monitor for escalation\n" + \
                "- Document patterns"
        else:
            recommendation += "\nRecommended Actions:\n" + \
                "- Monitor for changes\n" + \
                "- Include in regular review"

        return recommendation
    
    def generate_system_prompt(self, analysis: Dict) -> str:
        """Generate system prompt based on analysis results"""
        # We can just return the AIRFLOW_LOG_ANALYSIS_PROMPT template
        return AIRFLOW_LOG_ANALYSIS_PROMPT.template
        
    def _format_section(self, 
                       name: str, 
                       description: str, 
                       data: Dict,
                       config: Dict) -> str:
        """Format a section of the system prompt"""
        lines = [f"{name}:", description]
        
        # Add examples if configured
        if config.get('include_examples'):
            max_examples = config.get('max_examples', 2)
            for severity, items in data.items():
                examples = items[:max_examples]
                for example in examples:
                    lines.append(f"- {severity.upper()}: {example['content']}")
                    
        return '\n'.join(lines)
        
    def create_ollama_model(self, system_prompt: str) -> Dict:
        """Create Ollama model request using config settings"""
        model_config = self.config['model']        
     
        # Get just the template part without the variables
        system_prompt = AIRFLOW_LOG_ANALYSIS_PROMPT.template.format(
            context="",  # Empty context since this is just the system prompt
            question=""  # Empty question since this is just the system prompt
        )
        
        # Log the formatted prompt
        self.logger.debug("Formatted system prompt:")
        self.logger.debug(system_prompt)
        
        # Properly escape the prompt for the modelfile
        escaped_prompt = system_prompt.replace('"', '\\"').replace('\n', '\\n')
        
        # Create modelfile with config parameters
        modelfile = (
            f"FROM {model_config['base_model']}\n"
            f"PARAMETER temperature {model_config['parameters']['temperature']}\n"
            f"PARAMETER top_p {model_config['parameters']['top_p']}\n"
            f"PARAMETER num_ctx {model_config['parameters']['num_ctx']}\n"
            f'SYSTEM "{escaped_prompt}"\n'
            'TEMPLATE """{{.System}}\n\n'
            'User: {{.Prompt}}\n\n'
            'Assistant: {{.Response}}"""\n'
        )
        
        request_data = {
            "name": model_config['name'],
            "modelfile": modelfile
        }
        
        # Log the final request for debugging
        #self.logger.debug("Model request:")
        #self.logger.debug(json.dumps(request_data, indent=2))
        
        return request_data
        
    def format_ollama_analysis(self, analysis_response: Dict, analysis_data: Dict = None) -> str:
        """Format Ollama's analysis response into a readable text format"""
        formatted = []
        formatted.append("=" * 80)
        formatted.append("AIRFLOW LOG ANALYSIS REPORT")
        formatted.append("=" * 80)
        formatted.append("")

        # Format timestamp
        formatted.append(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        formatted.append("")

        # Add summary from analysis data if available
        if analysis_data and 'summary' in analysis_data:
            formatted.append("-" * 40)
            formatted.append("ANALYSIS SUMMARY")
            formatted.append("-" * 40)
            summary = analysis_data['summary']
            formatted.append(f"Total Logs Analyzed: {summary.get('total_logs_analyzed', 'N/A')}")
            formatted.append(f"Time Period: {summary.get('time_period', 'N/A')}")
            formatted.append(f"Total Issues Found: {summary.get('total_issues_found', 'N/A')}")
            formatted.append("")

        # Add pattern analysis if available
        if analysis_data and 'patterns' in analysis_data:
            formatted.append("-" * 40)
            formatted.append("DETECTED PATTERNS")
            formatted.append("-" * 40)
            
            patterns = analysis_data['patterns']
            for pattern_type, severities in patterns.items():
                formatted.append(f"\n{pattern_type.replace('_', ' ').title()}:")
                for severity, issues in severities.items():
                    formatted.append(f"\n  {severity.upper()} Severity Issues:")
                    for issue in issues:
                        formatted.append(f"    - {issue['content']}")
                        if 'frequency' in issue:
                            formatted.append(f"      Frequency: {issue['frequency']} occurrences")
                        if 'context' in issue and issue['context']:
                            formatted.append(f"      Context: {issue['context']}")
            formatted.append("")

        # Format the response content
        if 'response' in analysis_response:
            formatted.append("-" * 40)
            formatted.append("AI ANALYSIS")
            formatted.append("-" * 40)
            
            response_text = analysis_response['response']
            sections = response_text.split('\n')
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

        # Add recommendations if available
        if analysis_data and 'recommendations' in analysis_data:
            formatted.append("")
            formatted.append("-" * 40)
            formatted.append("RECOMMENDATIONS")
            formatted.append("-" * 40)
            for rec in analysis_data['recommendations']:
                formatted.append(f"Issue: {rec['issue']} (Severity: {rec['severity']})")
                formatted.append(f"Suggestion: {rec['suggestion']}")
                formatted.append("")

        # Add model metadata if available
        if 'eval_count' in analysis_response or 'eval_duration' in analysis_response:
            formatted.append("-" * 40)
            formatted.append("Analysis Metadata")
            formatted.append("-" * 40)
            if 'eval_count' in analysis_response:
                formatted.append(f"Eval Count: {analysis_response['eval_count']}")
            if 'eval_duration' in analysis_response:
                formatted.append(f"Duration: {analysis_response['eval_duration']} ms")

        return "\n".join(formatted)

    def save_analysis_report(self, ollama_response: Dict, output_file: str = None):
        """Save formatted analysis report to a text file"""
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"airflow_analysis_report_{timestamp}.txt"

        # Get the latest analysis results
        analysis_data = None
        if hasattr(self, 'analysis_results') and self.analysis_results:
            # Calculate total issues found
            total_issues = 0
            for pattern_type, severities in self.analysis_results.items():
                if isinstance(severities, dict):
                    for severity_level, issues in severities.items():
                        if isinstance(issues, list):
                            total_issues += len(issues)

            analysis_data = {
                'summary': {
                    'total_logs_analyzed': sum(
                        len(severity_data)
                        for pattern_data in self.analysis_results.values()
                        if isinstance(pattern_data, dict)
                        for severity_data in pattern_data.values()
                        if isinstance(severity_data, list)
                    ),
                    'time_period': f"{self.config['analysis']['days_back']} days",
                    'total_issues_found': total_issues
                },
                'patterns': self.analysis_results,
                'recommendations': self._generate_recommendations(self.analysis_results)
            }

        formatted_analysis = self.format_ollama_analysis(ollama_response, analysis_data)
        
        output_path = self._get_output_path(output_file, datetime.now().strftime('%Y%m%d_%H%M%S'))
        self._save_text(formatted_analysis, output_path)
        self.logger.info(f"Saved analysis report to {output_path}")
        
        return output_path

    def _generate_recommendations(self, analysis_results: Dict) -> List[Dict]:
        """Generate recommendations based on analysis results"""
        recommendations = []
        
        for pattern_type, severities in analysis_results.items():
            if isinstance(severities, dict):
                for severity, issues in severities.items():
                    if severity in ['critical', 'high'] and issues and isinstance(issues, list):
                        recommendation = self._get_recommendation_for_pattern(pattern_type, severity)
                        issue_count = len(issues)
                        
                        recommendations.append({
                            'issue': pattern_type.replace('_', ' ').title(),
                            'severity': severity,
                            'count': issue_count,
                            'suggestion': recommendation,
                            'sample': issues[0]['content'][:200] if issues else None
                        })
        
        # Sort recommendations by severity (critical first, then high)
        recommendations.sort(key=lambda x: 0 if x['severity'] == 'critical' else 1)
        
        return recommendations

    def _get_output_path(self, filename: str, timestamp: str) -> Path:
        """Get output path with optional timestamp"""
        path = Path(filename)
        if self.config['output']['include_timestamp']:
            return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")
        return path
        
    def _save_json(self, data: Dict, path: Path, indent: int):
        """Save data as JSON with custom encoder for MongoDB types"""
        with open(path, 'w') as f:
            json.dump(data, f, indent=indent, cls=MongoJSONEncoder)
        self.logger.info(f"Saved JSON to {path}")
        
    def _save_text(self, text: str, path: Path):
        """Save text to file"""
        with open(path, 'w') as f:
            f.write(text)
        self.logger.info(f"Saved text to {path}")

    def save_outputs(self, analysis: Dict, system_prompt: str, model_request: Dict):
        """Save outputs based on configuration"""
        output_config = self.config['output']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if output_config['save_analysis']:
            path = self._get_output_path(output_config['analysis_file'], timestamp)
            self._save_json(analysis, path, output_config['json_indent'])
            
        if output_config['save_prompt']:
            path = self._get_output_path(output_config['prompt_file'], timestamp)
            self._save_text(system_prompt, path)
            
        if output_config['save_model_request']:
            path = self._get_output_path(output_config['model_request_file'], timestamp)
            self._save_json(model_request, path, output_config['json_indent'])        