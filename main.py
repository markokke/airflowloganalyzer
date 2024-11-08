"""
Airflow Log Analyzer Main Script
This script orchestrates the log analysis process using the various components
to analyze Airflow logs, generate insights, and create reports.
"""

import sys
import yaml
from pathlib import Path
from typing import Dict, Tuple
import logging
from datetime import datetime

from services.log_analyzer import LogAnalyzer
from services.report_generator import ReportGenerator
from clients.ollama_client import OllamaClient

def load_config(config_path: str) -> Dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration: {str(e)}")
        sys.exit(1)

def setup_logging(config: Dict) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Configured logger instance
    """
    try:
        logging.config.dictConfig(config['logging'])
        return logging.getLogger('airflow_log_analyzer')
    except Exception as e:
        print(f"Error setting up logging: {str(e)}")
        sys.exit(1)

def initialize_services(config: Dict) -> Tuple[LogAnalyzer, ReportGenerator]:
    """
    Initialize the main services needed for log analysis.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Tuple of (LogAnalyzer, ReportGenerator)
    """
    try:
        analyzer = LogAnalyzer(config)  # Pass config directly instead of path
        report_generator = ReportGenerator(config)
        return analyzer, report_generator
    except Exception as e:
        print(f"Error initializing services: {str(e)}")
        sys.exit(1)

def handle_model_creation(
    ollama_client: OllamaClient,
    model_request: Dict,
    config: Dict
) -> None:
    """
    Handle the creation or recreation of the Ollama model.
    
    Args:
        ollama_client: Initialized OllamaClient
        model_request: Model creation request dictionary
        config: Configuration dictionary
    """
    model_name = model_request["name"]
    force_recreate = config['model']['creation'].get('force_recreate', False)
    prompt_for_recreate = config['model']['creation'].get('prompt_for_recreate', True)
    skip_if_exists = config['model']['creation'].get('skip_if_exists', False)

    if ollama_client.model_exists(model_name):
        if skip_if_exists:
            print(f"Model '{model_name}' exists. Skipping creation.")
            return
        if force_recreate:
            print(f"Model '{model_name}' exists. Forcing recreation...")
        elif prompt_for_recreate:
            user_input = input(f"Model '{model_name}' already exists. Recreate? (y/N): ")
            if user_input.lower() != 'y':
                return

    print(f"{'Recreating' if force_recreate else 'Creating'} Ollama model...")
    try:
        create_response = ollama_client.create_model(model_request, force_recreate=force_recreate)
        if create_response.get('status') in ['success', 'exists']:
            print(f"Model {model_name} {'recreated' if force_recreate else 'created'} successfully!")
        else:
            print(f"Warning: Unexpected status from model creation: {create_response.get('status')}")
    except Exception as e:
        print(f"Error during model creation: {str(e)}")
        sys.exit(1)

def analyze_logs(analyzer: LogAnalyzer, logger: logging.Logger) -> Dict:
    """
    Perform log analysis and handle any errors.
    
    Args:
        analyzer: Initialized LogAnalyzer
        logger: Configured logger
    
    Returns:
        Analysis results dictionary
    """
    try:
        logger.info("Starting log analysis...")
        print("Analyzing logs...")
        return analyzer.analyze_logs()
    except Exception as e:
        logger.error(f"Log analysis failed: {str(e)}")
        print(f"Error during log analysis: {str(e)}")
        sys.exit(1)

def process_analysis(
    analyzer: LogAnalyzer,
    ollama_client: OllamaClient,
    analysis: Dict,
    logger: logging.Logger
) -> Dict:
    try:
        logger.info("Generating system prompt and model request...")
        print("\nProcessing analysis results...")
        
        system_prompt = analyzer.generate_system_prompt(analysis)
        model_request = analyzer.create_ollama_model(system_prompt)
        
        handle_model_creation(ollama_client, model_request, analyzer.config)
        
        logger.info("Performing AI analysis...")
        print("Running AI analysis...")
        
        # Return the full analysis structure
        return {
            'model_response': analyzer.pattern_analysis,
            'pattern_matches': analysis['pattern_matches'],
            'counts': analysis['counts']
        }, system_prompt, model_request
        
    except Exception as e:
        logger.error(f"Analysis processing failed: {str(e)}")
        print(f"Error processing analysis: {str(e)}")
        sys.exit(1)

def generate_report(
    report_generator: ReportGenerator,
    analysis: Dict,
    model_response: Dict,
    system_prompt: str,
    model_request: Dict,
    logger: logging.Logger
) -> None:
    """
    Generate and save the analysis report.
    
    Args:
        report_generator: Initialized ReportGenerator
        analysis: Analysis results
        model_response: Model response
        system_prompt: Generated system prompt
        model_request: Model request dictionary
        logger: Configured logger
    """
    try:
        logger.info("Generating analysis report...")
        print("\nGenerating report...")
        
        formatted_report = report_generator.format_analysis(
            model_response,
            analysis
        )
        
        report_path = report_generator.save_report(formatted_report)
        print(f"Analysis report saved to: {report_path}")
        
        logger.info("Saving additional outputs...")
        report_generator.save_outputs(analysis, model_request)
        print("All outputs saved successfully!")
    except Exception as e:
        logger.error(f"Report generation failed: {str(e)}")
        print(f"Error generating report: {str(e)}")
        sys.exit(1)

def main():
    """Main execution function."""
    try:
        # Load configuration
        config = load_config('config.yaml')
        
        # Setup logging
        logger = setup_logging(config)
        logger.info("Starting Airflow Log Analysis")
        
        # Initialize services
        analyzer, report_generator = initialize_services(config)
        
        # Initialize Ollama client with config
        ollama_client = OllamaClient(
            model_name=config['model']['name'],
            config=config  # Pass the entire config
        )
        
        # Analyze logs
        print("Analyzing logs...")
        analysis = analyzer.analyze_logs()
        
        # Process with Ollama
        analysis_results, system_prompt, model_request = process_analysis(
            analyzer,
            ollama_client,
            analysis,
            logger
        )
    
        
        # Get actual log counts
        log_counts = analyzer.get_log_counts()        

        # Generate report with proper data structure
        analysis_data = {
            'summary': {
                'total_logs_analyzed': log_counts['total_logs'],
                'processed_logs': log_counts['processed_logs'],
                'time_period': f"{config['analysis']['days_back']} days",
                'total_issues_found': log_counts['pattern_matches'],
                'unique_patterns_found': len(analysis_results['pattern_matches']) if analysis_results.get('pattern_matches') else 0
            },
            'patterns': analysis_results['pattern_matches'],
            'recommendations': analyzer._generate_recommendations(analysis_results['pattern_matches'])
        }
        
        formatted_report = report_generator.format_analysis(
            analysis_results['model_response'],  # Use the model response from analysis_results
            analysis_data
        )
        
        # Save everything
        report_path = report_generator.save_report(formatted_report)
        report_generator.save_outputs(analysis_data, model_request)
        
        print(f"\nAnalysis report saved to: {report_path}")
        print("Process completed successfully!")
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\nUnexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()