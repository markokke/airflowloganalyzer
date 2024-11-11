# models/mongodb_operations.py
from typing import Dict
import logging
from pymongo.collection import Collection
from datetime import datetime
from bson.objectid import ObjectId

class MongoDBOperations:
    def __init__(self, db):
        """Initialize MongoDB operations."""
        self.db = db
        self.analysis_collection = self.db.AirflowLogAnalysis
        self.logger = logging.getLogger('airflow_log_analyzer')
        self._setup_collection()
    
    def _setup_collection(self):
        """Set up the AirflowLogAnalysis collection with appropriate indexes."""
        # Create indexes for efficient querying
        indexes = [
            ("dag_id", 1),
            ("dag_run_id", 1),
            ("task_id", 1),
            ("try_number", 1),
            ("timestamp", -1)
        ]
        
        for field, direction in indexes:
            self.analysis_collection.create_index(
                [(field, direction)],
                background=True
            )
        
        self.logger.info("Set up AirflowLogAnalysis collection and indexes")

    def store_analysis(self, analysis_data: Dict) -> ObjectId:
        """
        Store analysis results in MongoDB.
        
        Args:
            analysis_data: Dictionary containing analysis results and metadata
            
        Returns:
            ObjectId of the inserted document
        """
        try:
            # Extract required fields from the raw log content
            log_info = analysis_data.get('log_info', '')
            
            # Extract Airflow context using the configured regex pattern
            airflow_context = {}
            if 'AIRFLOW_CTX_' in log_info:
                context_fields = {
                    'dag_id': "AIRFLOW_CTX_DAG_ID='([^']+)'",
                    'dag_run_id': "AIRFLOW_CTX_DAG_RUN_ID='([^']+)'",
                    'task_id': "AIRFLOW_CTX_TASK_ID='([^']+)'",
                    'try_number': "AIRFLOW_CTX_TRY_NUMBER='([^']+)'"
                }
                
                import re
                for field, pattern in context_fields.items():
                    match = re.search(pattern, log_info)
                    if match:
                        airflow_context[field] = match.group(1)
                    else:
                        airflow_context[field] = "unknown"
                        self.logger.warning(f"Could not extract {field} from log content")

            # Prepare document for insertion
            document = {
                "dag_id": airflow_context.get('dag_id', 'unknown'),
                "dag_run_id": airflow_context.get('dag_run_id', 'unknown'),
                "task_id": airflow_context.get('task_id', 'unknown'),
                "try_number": airflow_context.get('try_number', 'unknown'),
                "full_analysis": analysis_data.get('analysis', {}),
                "pattern_matches": analysis_data.get('patterns', {}),
                "recommendations": analysis_data.get('recommendations', []),
                "summary": analysis_data.get('summary', {}),
                "timestamp": datetime.now(),
                "source_log_id": analysis_data.get('log_id')
            }

            # Insert the document
            result = self.analysis_collection.insert_one(document)
            self.logger.info(f"Stored analysis results with ID: {result.inserted_id}")
            
            return result.inserted_id
            
        except Exception as e:
            self.logger.error(f"Error storing analysis results: {str(e)}")
            raise