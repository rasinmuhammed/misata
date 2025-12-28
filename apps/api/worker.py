import os
import time
from celery import Celery
from misata import DataSimulator, SchemaConfig
import pandas as pd

# Initialize Celery
BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("misata_worker", broker=BROKER_URL, backend=BROKER_URL)

@celery_app.task(bind=True)
def generate_dataset_task(self, schema_config_dict: dict, job_id: str):
    """
    Celery task to generate dataset from schema configuration.
    Currently saves to local storage (apps/api/storage).
    """
    self.update_state(state='PROGRESS', meta={'progress': 0, 'status': 'Initializing...'})
    
    try:
        # 1. Deserialize schema
        config = SchemaConfig(**schema_config_dict)
        
        # Enable smart mode for context-aware value generation
        # Uses LLM to generate realistic domain-specific values
        simulator = DataSimulator(config, smart_mode=True, use_llm=True)
        
        # 2. Setup Output location
        output_dir = os.path.abspath(f"storage/{job_id}")
        os.makedirs(output_dir, exist_ok=True)
        
        # Calculate total rows for progress monitoring
        # Avoid division by zero
        total_rows = sum([t.row_count for t in config.tables if not t.is_reference]) or 1
        generated_rows = 0
        
        results = {}
        
        self.update_state(state='PROGRESS', meta={'progress': 5, 'status': 'Starting generation...'})
        
        # 3. Generate Data
        # Using generate_all() which yields (table_name, dataframe)
        for table_name, df in simulator.generate_all():
            file_name = f"{table_name}.csv"
            file_path = os.path.join(output_dir, file_name)
            
            # Save to CSV
            df.to_csv(file_path, index=False)
            results[table_name] = file_path
            
            # Update Progress
            generated_rows += len(df)
            # Cap progress at 95% until finalized
            progress = 5 + int((generated_rows / total_rows) * 90)
            progress = min(progress, 95)
            
            self.update_state(state='PROGRESS', meta={
                'progress': progress, 
                'status': f'Generated {table_name} ({len(df)} rows)'
            })
            
        # 4. Finalize
        self.update_state(state='SUCCESS', meta={
            'progress': 100, 
            'status': 'Complete', 
            'files': results
        })
        
        return {"status": "complete", "job_id": job_id, "files": results}
        
    except Exception as e:
        # Celery handles exceptions automatically, setting state to FAILURE
        # and result to the exception object.
        raise e
