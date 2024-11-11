import json
from datetime import datetime
import time
import requests
import logging
from pathlib import Path
from typing import Dict, Union
from prompts import (
    AIRFLOW_LOG_ANALYSIS_PROMPT,
    ERROR_ANALYSIS_PROMPT,
    TEST_FAILURE_ANALYSIS_PROMPT,
    PERFORMANCE_ANALYSIS_PROMPT,
    POD_LIFECYCLE_ANALYSIS_PROMPT,
    SUMMARY_TEMPLATE,
    DBT_ANALYSIS_PROMPT
)

class OllamaClient:
    """Client for interacting with Ollama API for model management and inference."""
    
    def __init__(self, model_name: str, config: Dict):
        self.config = config['ollama']
        self.output_config = config['output']  # Add this line
        protocol = self.config.get('protocol', 'http')
        host = self.config['host']
        port = self.config['port']
        self.base_url = f"{protocol}://{host}:{port}"
        self.model_name = model_name
        self.timeout = self.config.get('timeout', 30)
        self.retries = self.config.get('retries', 3)
        self.prompts = self._load_prompts()
        self.logger = logging.getLogger('airflow_log_analyzer')
        
    def _load_prompts(self) -> Dict:
        """Load all prompt templates."""
        return {
            'main': AIRFLOW_LOG_ANALYSIS_PROMPT,
            'error': ERROR_ANALYSIS_PROMPT,
            'test': TEST_FAILURE_ANALYSIS_PROMPT,
            'performance': PERFORMANCE_ANALYSIS_PROMPT,
            'pod': POD_LIFECYCLE_ANALYSIS_PROMPT,
            'summary': SUMMARY_TEMPLATE,
            'dbt': DBT_ANALYSIS_PROMPT
        }
        
    def _make_request(self, method: str, endpoint: str, data: Dict = None, stream: bool = False) -> Union[Dict, requests.Response]:
        """
        Make HTTP request with retries.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without leading slash)
            data: Request data (for POST requests)
            stream: Whether to stream the response
            
        Returns:
            JSON response or streaming response object
            
        Raises:
            requests.RequestException: If request fails after all retries
        """
        url = f"{self.base_url}/{endpoint}"
        for attempt in range(self.retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    json=data,
                    stream=stream,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response if stream else response.json()
            except requests.RequestException as e:
                if attempt == self.retries - 1:  # Last attempt
                    print(f"Failed to connect to Ollama after {self.retries} attempts: {str(e)}")
                    raise
                print(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(1)  # Wait before retry
                
    def model_exists(self, model_name: str) -> bool:
            """
            Check if a model exists in Ollama.
            
            Args:
                model_name: Name of the model to check
                
            Returns:
                True if model exists, False otherwise
            """
            try:
                # Use api/tags to list all models
                response = self._make_request('GET', 'api/tags')
                models = response.get('models', [])
                return any(model['name'] == model_name for model in models)
            except Exception as e:
                print(f"Error checking model existence: {str(e)}")
                return False

    def create_model(self, model_request: Dict, force_recreate: bool = False) -> Dict:
        """
        Create a new model in Ollama or recreate an existing one.
        
        Args:
            model_request: Model creation request dictionary
            force_recreate: Whether to force recreation if model exists
            
        Returns:
            Response from the Ollama API
        """
        model_name = model_request["name"]
        if self.model_exists(model_name) and not force_recreate:
            return {"status": "exists"}
            
        try:
            # Use api/create endpoint for model creation
            response = self._make_request('POST', 'api/create', model_request, stream=True)
            status_updates = []
            
            for line in response.iter_lines():
                if line:
                    status = json.loads(line.decode('utf-8'))
                    status_updates.append(status)
                    if 'status' in status:
                        print(f"Status: {status['status']}")
                    if 'error' in status:
                        print(f"Error: {status['error']}")
                    
            return status_updates[-1] if status_updates else {"status": "unknown"}
            
        except Exception as e:
            print(f"Error creating model: {str(e)}")
            raise

    def generate_completion(self, model: str, prompt: str, stream: bool = False) -> Dict:
        """
        Generate a completion using the model.
        
        Args:
            model: Name of the model to use
            prompt: Input prompt
            stream: Whether to stream the response
            
        Returns:
            Model response dictionary
        """
        request_data = {
            "model": model,
            "prompt": prompt,
            "stream": stream
        }
        
        try:
            # Use api/generate endpoint for completions
            if stream:
                response = self._make_request('POST', 'api/generate', request_data, stream=True)
                responses = []
                for line in response.iter_lines():
                    if line:
                        response_obj = json.loads(line.decode('utf-8'))
                        responses.append(response_obj)
                return responses[-1] if responses else {}
            else:
                return self._make_request('POST', 'api/generate', request_data)
                
        except Exception as e:
            print(f"Error generating completion: {str(e)}")
            raise
        
    def ask_model(self, log_content: str, prompt_type: str = 'main', log_id: str = None) -> Dict:
        """Ask the model to analyze log content using a specific prompt type."""
        if prompt_type not in self.prompts:
            raise ValueError(f"Invalid prompt type: {prompt_type}")
            
        prompt_template = self.prompts[prompt_type]
        formatted_prompt = self._format_prompt(prompt_template, log_content, prompt_type)
        
        self.logger.debug(f"ask_model prompt: {formatted_prompt}")
        
        # Create prompt directory if it doesn't exist
        base_dir = Path(self.output_config['output_dir'])
        prompts_dir = base_dir / self.output_config['subdirectories']['prompts']
        prompts_dir.mkdir(parents=True, exist_ok=True)
        
        # Write formatted prompt to JSON file in the prompts directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Include log_id in filename if provided
        log_id_part = f"_{log_id[:8]}" if log_id else ""
        prompt_file = prompts_dir / f"prompt_{prompt_type}{log_id_part}_{timestamp}.json"
        
        with open(prompt_file, 'w') as f:
            json.dump({
                "prompt_type": prompt_type,
                "log_id": log_id,  # Include log_id in the JSON content too
                "formatted_prompt": formatted_prompt
            }, f, indent=2)
        
        self.logger.debug(f"Prompt saved to file: {prompt_file}")
        
        response = self.generate_completion(self.model_name, formatted_prompt)
        
        self.logger.debug(f"Received response from Ollama: {response}")
        return response

    def _format_prompt(self, template, log_content: str, prompt_type: str) -> str:
        """
        Format a prompt template with the given content.
        
        Args:
            template: Prompt template
            log_content: Log content to analyze
            prompt_type: Type of prompt being formatted
            
        Returns:
            Formatted prompt string
        """
        template_vars = {
            'main': {
                'context': log_content,
                'question': "What issues and patterns can you identify in these logs?"
            },
            'error': {'error_context': log_content},
            'test': {'test_context': log_content},
            'performance': {'performance_data': log_content},
            'pod': {'pod_data': log_content},
            'summary': {'analysis_results': log_content},
            'dbt': {'dbt_context': log_content}
        }
        
        return template.format(**template_vars[prompt_type])                        