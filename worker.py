import time
import logging
import os
from app.services.dispatcher import TaskDispatcher

# Setup Logging for the worker
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, "worker.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BeatManagerWorker")

def main():
    logger.info("BeatManager Worker starting up...")
    
    # Initialize the dispatcher
    dispatcher = TaskDispatcher(PROJECT_ROOT)
    
    logger.info("Worker entering main loop. Monitoring state.json for pending tasks.")
    
    while True:
        try:
            # Get pending tasks
            pending_tasks = dispatcher.state.get_pending_tasks()
            
            if not pending_tasks:
                # Sleep if nothing to do
                time.sleep(5)
                continue
            
            for task in pending_tasks:
                task_id = task.doc_id
                logger.info(f"Processing Task #{task_id} ({task.get('type')})")
                
                # Execute the task via dispatcher
                result = dispatcher.process_task(task_id)
                
                if result.success:
                    logger.info(f"Task #{task_id} completed successfully.")
                else:
                    logger.error(f"Task #{task_id} failed: {result.error_message}")
            
        except KeyboardInterrupt:
            logger.info("Worker shutting down...")
            break
        except Exception as e:
            logger.error(f"Worker encountered an unexpected error: {str(e)}")
            time.sleep(10) # Pause before retry on error

if __name__ == "__main__":
    main()
