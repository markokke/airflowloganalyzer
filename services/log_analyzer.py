import json
import logging.config
import re
from collections import defaultdict
import pymongo
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from pathlib import Path
from models.mongo_encoder import MongoJSONEncoder 
from models.mongodb_operations import MongoDBOperations
from clients.ollama_client import OllamaClient
from services.report_generator import ReportGenerator
from typing import Dict, List, Optional

class LogAnalyzer:
    def __init__(self, config: Dict, report_generator: Optional[ReportGenerator] = None):
        """Initialize the LogAnalyzer with configuration."""
        self.config = config
        logging.config.dictConfig(self.config['logging'])
        self.logger = logging.getLogger('airflow_log_analyzer')
        self.report_generator = report_generator or ReportGenerator(config)
        
        # Initialize MongoDB connections
        self._init_mongodb()
        self.mongo_ops = MongoDBOperations(self.db)
        
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

    def _init_mongodb(self):
        """Initialize MongoDB connections with comprehensive error handling and index management."""
        mongo_config = self.config.get('mongodb')
        if not mongo_config:
            raise ValueError("MongoDB configuration is missing from config")
            
        try:
            self.logger.debug(f"Attempting to connect to MongoDB at {mongo_config['uri']}")
            
            # Initialize main MongoDB client
            self.client = pymongo.MongoClient(
                mongo_config['uri'],
                serverSelectionTimeoutMS=mongo_config['timeout_ms'],
                maxPoolSize=mongo_config['max_pool_size']
            )
            
            # Test the connection
            self.client.server_info()
            self.logger.info("Successfully connected to MongoDB")
            
            # Get database
            self.db = self.client[mongo_config['db_name']]
            
            # Initialize collections - with fallback to old configuration style
            if 'collections' in mongo_config:
                # New style configuration
                collections_config = mongo_config['collections']
                self.log_collection = self.db[collections_config['logs']]
                self.analysis_collection = self.db[collections_config['analysis']]
            else:
                # Old style configuration
                self.log_collection = self.db[mongo_config['collection_name']]
                self.analysis_collection = self.db['AirflowLogAnalysis']

            # Handle text indexes if configured
            if 'indexes' in mongo_config and 'text_indexes' in mongo_config['indexes']:
                self._ensure_text_indexes(mongo_config['indexes']['text_indexes'])

            # Handle analysis indexes
            if 'analysis_indexes' in mongo_config:
                self._ensure_analysis_indexes(mongo_config['analysis_indexes'])
            else:
                # Default index configuration if not specified
                default_indexes = [
                    {'field': 'dag_id', 'direction': 1},
                    {'field': 'dag_run_id', 'direction': 1},
                    {'field': 'task_id', 'direction': 1},
                    {'field': 'try_number', 'direction': 1},
                    {'field': 'timestamp', 'direction': -1}
                ]
                self._ensure_analysis_indexes(default_indexes)
                
            # Verify collections exist and have documents
            self._verify_collections()
                
        except pymongo.errors.ServerSelectionTimeoutError as e:
            self.logger.error(f"Could not connect to MongoDB server: {str(e)}")
            raise
        except pymongo.errors.OperationFailure as e:
            self.logger.error(f"MongoDB authentication failed: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize MongoDB: {str(e)}")
            raise

    def _ensure_text_indexes(self, text_index_configs):
        """Ensure text indexes are properly configured."""
        try:
            # Get existing indexes
            existing_indexes = list(self.log_collection.list_indexes())
            existing_text_indexes = [
                idx for idx in existing_indexes 
                if idx.get('key', {}).get('_fts') == 'text'
            ]

            for idx_config in text_index_configs:
                if not idx_config.get('enabled', False):
                    continue

                field = idx_config['field']
                weights = idx_config.get('weights', {field: 1})
                
                # Check if we need to drop and recreate the text index
                needs_recreation = False
                if existing_text_indexes:
                    current_idx = existing_text_indexes[0]  # MongoDB allows only one text index
                    current_weights = current_idx.get('weights', {})
                    if current_weights != weights:
                        self.logger.info("Text index weights have changed, recreating index")
                        needs_recreation = True
                        # Drop existing text index
                        self.log_collection.drop_index(current_idx['name'])
                else:
                    needs_recreation = True

                if needs_recreation:
                    self.logger.info(f"Creating text index on {field}")
                    self.log_collection.create_index(
                        [(field, 'text')],
                        weights=weights,
                        default_language=idx_config.get('default_language', 'english'),
                        language_override=idx_config.get('language_override', 'language'),
                        sparse=idx_config.get('sparse', True),
                        background=idx_config.get('background', True)
                    )
                    self.logger.info(f"Successfully created text index on {field}")

        except Exception as e:
            self.logger.error(f"Error ensuring text indexes: {str(e)}")
            raise

    def _ensure_analysis_indexes(self, index_config):
        """Ensure required indexes exist on the analysis collection."""
        try:
            existing_indexes = self.analysis_collection.list_indexes()
            existing_index_names = {idx['name'] for idx in existing_indexes}
            
            for index in index_config:
                field = index['field']
                direction = index['direction']
                index_name = f"{field}_1" if direction == 1 else f"{field}_-1"
                
                if index_name not in existing_index_names:
                    self.logger.info(f"Creating index on {field}")
                    self.analysis_collection.create_index(
                        [(field, direction)],
                        background=True
                    )
                    self.logger.debug(f"Created index {index_name}")
            
            self.logger.info("Finished ensuring analysis collection indexes")
            
        except Exception as e:
            self.logger.error(f"Error ensuring analysis indexes: {str(e)}")
            raise

    def _verify_collections(self):
        """Verify collections exist and have documents."""
        try:
            # Check log collection
            log_count = self.log_collection.count_documents({})
            self.logger.info(f"Found {log_count} documents in logs collection")
            
            if log_count == 0:
                self.logger.warning("Logs collection is empty")

            # Check analysis collection
            analysis_count = self.analysis_collection.count_documents({})
            self.logger.debug(f"Found {analysis_count} documents in analysis collection")
            
            # Get and log the names of all collections in the database
            all_collections = self.db.list_collection_names()
            self.logger.debug(f"Available collections in database: {all_collections}")
            
        except Exception as e:
            self.logger.error(f"Error verifying collections: {str(e)}")
            raise
        
    def analyze_individual_logs(self) -> List[Dict]:
        """Analyze each log entry individually and return list of analysis results."""
        try:
            self.logger.info("Starting analyze_individual_logs method")
            
            if 'analysis' not in self.config:
                self.logger.error("Missing 'analysis' section in configuration")
                raise KeyError("Missing 'analysis' section in configuration")
                
            days_back = self.config['analysis']['days_back']
            cutoff_date = datetime.now() - timedelta(days=days_back)
            cutoff_object_id = ObjectId.from_datetime(cutoff_date)
            
            self.logger.debug(f"Checking for text index existence")
            # Check if text index exists
            indexes = list(self.log_collection.list_indexes())
            has_text_index = any(
                idx.get('key', {}).get('_fts') == 'text' and 
                'LogInfo' in idx.get('weights', {})
                for idx in indexes
            )
            
            self.logger.debug(f"Text index exists: {has_text_index}")

            # Build query with debug logging
            if has_text_index:
                query = {
                    "_id": {"$gte": cutoff_object_id},
                    "$and": [
                        {"$text": {"$search": "Task exit code 1"}},
                        {"LogInfo": {"$regex": ".*Task exited with return code 1.*"}}
                    ]
                }
            else:
                query = {
                    "_id": {"$gte": cutoff_object_id},
                    "LogInfo": {"$regex": ".*Task exited with return code 1.*"}
                }            

            self.logger.debug(f"Using query: {query}")
            
            # Execute query with debug logging
            self.logger.debug("Executing MongoDB query...")
            try:
                logs = self.log_collection.find(
                    query,
                    batch_size=self.config['mongodb']['batch_size']
                )
                self.logger.debug("Query executed successfully")
                
                # Get total count with debug logging
                self.logger.debug("Counting matching documents...")
                total_logs = self.log_collection.count_documents(query)
                self.logger.info(f"Found {total_logs} logs to analyze")
                
                if total_logs == 0:
                    self.logger.warning("No logs found matching the query criteria")
                    return []

                # Initialize services
                self.logger.debug("Initializing Ollama client...")
                ollama_client = OllamaClient(model_name=self.config['model']['name'], config=self.config)
                
                analysis_results = []
                log_count = 0

                for log in logs:
                    try:
                        log_count += 1
                        log_id = str(log['_id'])
                        self.logger.info(f"{'='*40}")
                        self.logger.info(f"Starting analysis of log {log_count} of {total_logs} (ID: {log_id})")
                        
                        # Log pattern information for this log entry
                        self.logger.debug(f"Starting pattern analysis for log {log_id}")
                        
                        # Initialize pattern results for this log
                        pattern_results = defaultdict(list)
                        
                        # Process patterns for this single log
                        log_info = log['LogInfo']
                        for pattern_name, pattern_config in self.config['analysis']['patterns'].items():
                            matches = self._extract_pattern(
                                pattern_name,
                                pattern_config,
                                log_info,
                                defaultdict(list)
                            )
                            
                            if matches:
                                pattern_type = pattern_name
                                for match_content in matches:
                                    pattern_results[pattern_type].append({
                                        'content': match_content,
                                        'pattern': pattern_name,
                                        'severity': pattern_config.get('severity')
                                    })

                        # Perform analysis for this log
                        log_analysis = {}
                        
                        try:
                            # Various analysis types...
                            if pattern_results.get('test_failure'):
                                test_analysis = ollama_client.ask_model(
                                    pattern_results['test_failure'], 
                                    prompt_type='test',
                                    log_id=log_id
                                )
                                log_analysis['test_analysis'] = test_analysis
                                
                            # Error patterns
                            if pattern_results.get('error'):
                                error_analysis = ollama_client.ask_model(
                                    pattern_results['error'], 
                                    prompt_type='error',
                                    log_id=log_id
                                )
                                log_analysis['error_analysis'] = error_analysis
                                
                            # Performance patterns
                            if pattern_results.get('performance'):
                                perf_analysis = ollama_client.ask_model(
                                    pattern_results['performance'], 
                                    prompt_type='performance',
                                    log_id=log_id
                                )
                                log_analysis['performance_analysis'] = perf_analysis
                                
                            # Pod status patterns
                            if pattern_results.get('pod_status'):
                                pod_analysis = ollama_client.ask_model(
                                    pattern_results['pod_status'], 
                                    prompt_type='pod',
                                    log_id=log_id
                                )
                                log_analysis['pod_analysis'] = pod_analysis

                        except Exception as e:
                            self.logger.error(f"Error during Ollama analysis for log {log_id}: {str(e)}")

                        # Format the analysis data
                        analysis_data = {
                            'log_id': log_id,
                            'log_info': log_info,
                            'analysis': log_analysis,
                            'patterns': dict(pattern_results),
                            'recommendations': self._generate_recommendations(dict(pattern_results)),
                            'summary': {
                                'log_id': log_id,
                                'timestamp': str(log['_id'].generation_time),
                                'total_issues_found': sum(len(matches) for matches in pattern_results.values())
                            }
                        }

                        # Store in MongoDB Analysis Collection
                        try:
                            analysis_id = self.mongo_ops.store_analysis(analysis_data)
                            self.logger.info(f"Stored analysis in MongoDB with ID: {analysis_id}")
                        except Exception as e:
                            self.logger.error(f"Error storing analysis in MongoDB: {str(e)}")
                            self.logger.exception("MongoDB storage error details:")
                        
                        # Generate and save report
                        try:
                            formatted_report = self.report_generator.format_analysis(
                                log_analysis,
                                analysis_data
                            )
                            filename = f"airflow_analysis_log_{log_id}.txt"
                            report_path = self.report_generator.save_report(formatted_report, filename)
                            self.logger.info(f"Generated report for log {log_id}: {report_path}")
                        except Exception as e:
                            self.logger.error(f"Error generating report for log {log_id}: {str(e)}")
                            self.logger.exception("Report generation error details:")

                        analysis_results.append({
                            'log_id': log_id,
                            'timestamp': str(log['_id'].generation_time),
                            'pattern_matches': dict(pattern_results),
                            'analysis': log_analysis
                        })

                    except Exception as e:
                        self.logger.error(f"Error processing log {log_count} (ID: {log_id}): {str(e)}")
                        self.logger.exception("Full traceback:")
                        continue

                self.logger.info(f"{'='*60}")
                self.logger.info("Final Summary:")
                self.logger.info(f"Total logs found: {total_logs}")
                self.logger.info(f"Total logs processed: {log_count}")
                self.logger.info(f"{'='*60}")
                
                return analysis_results
                
            except Exception as e:
                self.logger.error(f"Error executing MongoDB query: {str(e)}")
                self.logger.exception("Full traceback:")
                raise

        except Exception as e:
            self.logger.error(f"Critical error in analyze_individual_logs: {str(e)}")
            self.logger.exception("Full traceback:")
            raise
        
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
        
    def _get_context(self, log_info: str, match: re.Match, context_lines: int) -> str:
        """Get surrounding context lines for a match"""
        lines = log_info.split('\n')
        line_num = len(log_info[:match.start()].split('\n'))
        
        start = max(0, line_num - context_lines)
        end = min(len(lines), line_num + context_lines + 1)
        
        return '\n'.join(lines[start:end])

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

    def _extract_airflow_context(self, log_info: str) -> Dict[str, str]:
        """
        Extract Airflow context information from log content.
        
        Args:
            log_info: Raw log content string
            
        Returns:
            Dictionary containing extracted context fields
        """
        context_fields = {
            'dag_id': "AIRFLOW_CTX_DAG_ID='([^']+)'",
            'dag_run_id': "AIRFLOW_CTX_DAG_RUN_ID='([^']+)'",
            'task_id': "AIRFLOW_CTX_TASK_ID='([^']+)'",
            'try_number': "AIRFLOW_CTX_TRY_NUMBER='([^']+)'",
            'execution_date': "AIRFLOW_CTX_EXECUTION_DATE='([^']+)'"
        }
        
        extracted_context = {}
        
        for field, pattern in context_fields.items():
            match = re.search(pattern, log_info)
            if match:
                extracted_context[field] = match.group(1)
                self.logger.debug(f"Extracted {field}: {extracted_context[field]}")
            else:
                extracted_context[field] = "unknown"
                self.logger.warning(f"Could not extract {field} from log content")
                
        return extracted_context

    def _analyze_test_failures(self, log_content: str) -> List[Dict]:
        """
        Analyze test failures in log content.
        
        Args:
            log_content: Log content string to analyze
            
        Returns:
            List of dictionaries containing test failure details
        """
        failures = []
        failure_pattern = r"Failure in test([^:]+): (.+?)(?=\n|$)"
        
        for match in re.finditer(failure_pattern, log_content):
            test_name = match.group(1).strip()
            failure_message = match.group(2).strip()
            
            failures.append({
                'test_name': test_name,
                'failure_message': failure_message
            })
            self.logger.debug(f"Found test failure: {test_name}")
            
        return failures

    def _analyze_pod_events(self, log_content: str) -> List[Dict]:
        """
        Analyze Kubernetes pod events in log content.
        
        Args:
            log_content: Log content string to analyze
            
        Returns:
            List of dictionaries containing pod event details
        """
        events = []
        pod_pattern = r"Pod ([^\s]+) (has phase|returned) ([A-Za-z]+)"
        
        for match in re.finditer(pod_pattern, log_content):
            pod_name = match.group(1)
            event_type = match.group(2)
            status = match.group(3)
            
            events.append({
                'pod_name': pod_name,
                'event_type': event_type,
                'status': status
            })
            self.logger.debug(f"Found pod event: {pod_name} {event_type} {status}")
            
        return events 
    
    def _generate_recommendations(self, pattern_results: Dict) -> List[Dict]:
        """
        Generate recommendations based on pattern results.
        
        Args:
            pattern_results: Dictionary containing pattern matches
            
        Returns:
            List of recommendation dictionaries
        """
        recommendations = []
        
        for pattern_type, severities in pattern_results.items():
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

    def _get_recommendation_for_pattern(self, pattern_type: str, severity: str) -> str:
        """
        Get specific recommendation based on pattern type and severity.
        
        Args:
            pattern_type: Type of pattern detected
            severity: Severity level of the issue
            
        Returns:
            String containing the recommendation
        """
        recommendations = {
            'error': {
                'critical': 'CRITICAL: Immediate investigation required. Review logs and system resources.',
                'high': 'HIGH: Urgent review needed. Check error patterns and implement fixes.',
                'medium': 'Review error patterns and plan fixes during next maintenance window.'
            },
            'test_failure': {
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
            }
        }

        # Get pattern-specific recommendations
        pattern_recommendations = recommendations.get(pattern_type, {})
        
        # Get severity-specific recommendation or use default
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
                
        return recommendation

    def get_log_counts(self) -> Dict[str, int]:
        """
        Get counts of logs analyzed and patterns found.
        
        Returns:
            Dictionary containing log and pattern count statistics
        """
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

    def _format_output_path(self, filename: str, timestamp: str = None) -> Path:
        """
        Format output path with optional timestamp.
        
        Args:
            filename: Base filename
            timestamp: Optional timestamp string
            
        Returns:
            Path object for the formatted output path
        """
        path = Path(filename)
        if timestamp and self.config['output']['include_timestamp']:
            return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")
        return path
        
    def _save_json(self, data: Dict, path: Path):
        """
        Save dictionary as JSON with proper encoding.
        
        Args:
            data: Dictionary to save
            path: Path where to save the JSON file
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(
                data, 
                f, 
                indent=self.config['output'].get('json_indent', 2),
                cls=MongoJSONEncoder
            )
        self.logger.info(f"Saved JSON to {path}")
        
    def _save_text(self, text: str, path: Path):
        """
        Save text content to file.
        
        Args:
            text: Text content to save
            path: Path where to save the text file
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)
        self.logger.info(f"Saved text to {path}")

    def cleanup(self):
        """Cleanup resources and connections."""
        try:
            if hasattr(self, 'client'):
                self.client.close()
                self.logger.info("Closed MongoDB connection")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")                   