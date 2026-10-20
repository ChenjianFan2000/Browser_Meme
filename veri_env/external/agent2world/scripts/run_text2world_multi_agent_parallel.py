import os
import sys
import json
import argparse
import time
import traceback
from typing import Dict, Any, List, Tuple
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from functools import partial
import threading
from pathlib import Path

# 设置项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from agentic_world_model import generate_text2world_code


def load_text2world_dataset(dataset_path: str) -> List[Dict]:
    """
    Load text2world dataset from JSON file
    
    Args:
        dataset_path: Path to the dataset JSON file
        
    Returns:
        List of task dictionaries
    """
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            # If data is a dictionary, extract tasks
            if 'tasks' in data:
                return data['tasks']
            else:
                # Assume the dictionary values are tasks
                return list(data.values())
        elif isinstance(data, list):
            return data
        else:
            raise ValueError(f"Unsupported dataset format: {type(data)}")
            
    except Exception as e:
        print(f"Error loading dataset from {dataset_path}: {e}")
        raise


def validate_pddl_domain(pddl_domain: str) -> Tuple[bool, str]:
    """
    Validate PDDL domain syntax
    
    Args:
        pddl_domain: PDDL domain string
        
    Returns:
        Tuple of (is_valid, validation_message)
    """
    if not pddl_domain or not pddl_domain.strip():
        return False, "Empty domain"
    
    # Basic PDDL structure validation
    domain_pattern = r'\(define\s+\(domain\s+[\w-]+\)'
    if not re.search(domain_pattern, pddl_domain, re.IGNORECASE):
        return False, "Missing domain definition"
    
    # Check for balanced parentheses
    open_count = pddl_domain.count('(')
    close_count = pddl_domain.count(')')
    if open_count != close_count:
        return False, f"Unbalanced parentheses: {open_count} open, {close_count} close"
    
    return True, "Valid PDDL domain"


def extract_domain_name_from_pddl(pddl_domain: str) -> str:
    """
    Extract domain name from PDDL domain string
    
    Args:
        pddl_domain: PDDL domain string
        
    Returns:
        Domain name or 'unknown-domain' if not found
    """
    if not pddl_domain:
        return "unknown-domain"
    
    # Extract domain name using regex
    domain_pattern = r'\(define\s+\(domain\s+([\w-]+)\)'
    match = re.search(domain_pattern, pddl_domain, re.IGNORECASE)
    
    if match:
        return match.group(1)
    else:
        return "unknown-domain"


def load_existing_results(output_path: str) -> Dict[str, Any]:
    """
    Load existing results from output file
    
    Args:
        output_path: Path to the results JSON file
        
    Returns:
        Dictionary of existing results
    """
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing results from {output_path}: {e}")
            return {}
    return {}


def should_skip_task(task_key: str, existing_results: Dict[str, Any], force_rerun: bool = False) -> bool:
    """
    Check if a task should be skipped based on existing results
    
    Args:
        task_key: Task identifier
        existing_results: Dictionary of existing results
        force_rerun: Whether to force rerun all tasks
        
    Returns:
        True if task should be skipped, False otherwise
    """
    if force_rerun:
        return False
    
    if task_key not in existing_results:
        return False
    
    result = existing_results[task_key]
    
    # Skip if no error and has valid prediction
    if (not result.get('error') and 
        result.get('pred_domain') and 
        result.get('pred_domain').strip()):
        return True
    
    return False


def save_task_result_thread_safe(output_path: str, task_key: str, task_result: Dict[str, Any], lock: threading.Lock):
    """
    Thread-safe version of save_task_result
    
    Args:
        output_path: Path to save results
        task_key: Task identifier
        task_result: Result dictionary to save
        lock: Threading lock for file operations
    """
    with lock:
        # Load current results
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    results = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load existing results: {e}")
                results = {}
        else:
            results = {}
        
        # Update with new result
        results[task_key] = task_result
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save back to file
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving results to {output_path}: {e}")
            raise


def save_task_result(output_path: str, task_key: str, task_result: Dict[str, Any], existing_results: Dict[str, Any]):
    """
    Save task result to output file (single-threaded version)
    
    Args:
        output_path: Path to save results
        task_key: Task identifier
        task_result: Result dictionary to save
        existing_results: Dictionary of existing results (will be modified)
    """
    # Update existing results
    existing_results[task_key] = task_result
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Save to file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(existing_results, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving results to {output_path}: {e}")
        raise


def generate_pddl_for_task(task_data: Dict, benchmark_type: str, task_key: str,
                          enable_research: bool, enable_player: bool, enable_pytest: bool) -> Dict[str, Any]:
    """
    Generate PDDL domain for a single task using multi-agent framework

    Args:
        task_data: Single task data
        benchmark_type: Benchmark type identifier
        task_key: Task key for results directory
        enable_research: Whether to enable research agent
        enable_player: Whether to enable player agent
        enable_pytest: Whether to enable pytest agent

    Returns:
        Dictionary containing generation results
    """
    task_id = task_data['id']
    description = task_data['corrected_description']

    print(f"Processing task {task_id}...")

    start_time = time.time()
    error = None
    pred_domain = ""
    max_retries = 8
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Call multi-agent framework to generate PDDL domain
            pred_domain = generate_text2world_code(
                benchmark_type,
                description,
                results_base_dir=f"./logs/{benchmark_type}/{task_key}",
                enable_research=enable_research,
                enable_player=enable_player,
                enable_pytest=enable_pytest
            )

            if pred_domain:
                error = None
                break

        except Exception as e:
            retry_count += 1
            error = f"Multi-agent generation failed (attempt {retry_count}/{max_retries}): {str(e)}"
            print(f"Task {task_id} generation attempt {retry_count} failed: {error}")
            traceback.print_exc()

            if retry_count < max_retries:
                print(f"Retrying... ({retry_count + 1}/{max_retries})")
                time.sleep(2)
            else:
                print(f"Task {task_id} reached maximum retry limit, generation failed")

    end_time = time.time()
    generation_time = end_time - start_time

    # PDDL validation
    close_loop_success = False
    validation_msg = ""
    if pred_domain and not error:
        is_valid, validation_msg = validate_pddl_domain(pred_domain)
        close_loop_success = is_valid
        if not is_valid:
            print(f"Task {task_id} PDDL validation failed: {validation_msg}")
    elif error:
        validation_msg = error

    # Extract domain name
    domain_name = extract_domain_name_from_pddl(pred_domain) if pred_domain else "unknown-domain"

    # Create simple correction_process with only the final pred_domain
    if error:
        correction_process = {"0": {"domain_name": "error", "domain": "", "exec_info": ""}}
    else:
        correction_process = {"0": {"domain_name": domain_name, "domain": pred_domain, "exec_info": validation_msg}}

    # Build result
    result = {
        "error": error,
        "id": task_id,
        "gt_domain_raw": task_data['pddl_domain'],
        "gt_domain_without_comment": task_data['pddl_domain_processed'],
        "pred_domain": pred_domain,
        "domain_description": description,
        "close_loop_world_generation_success": close_loop_success,
        "validation_msg": validation_msg,
        "close_loop_world_generation_data": {
            "pred_domain": pred_domain,
            "correct_trace": [],  # Keep empty array as required
            "time": generation_time,
            "correction_process": correction_process  # Simple correction_process with only final result
        }
    }

    return result


def process_single_task(task_info: Tuple, args_dict: Dict) -> Tuple:
    """
    Process a single task in a worker process
    
    Args:
        task_info: Tuple of (task_data, global_task_index, task_key)
        args_dict: Dictionary containing all necessary arguments
    
    Returns:
        Tuple of (task_key, result, global_task_index, success)
    """
    task_data, global_task_index, task_key = task_info
    
    try:
        print(f"Worker {os.getpid()}: Processing task {global_task_index}...")
        
        result = generate_pddl_for_task(
            task_data,
            args_dict['benchmark_type'],
            task_key,
            enable_research=args_dict['enable_research'],
            enable_player=args_dict['enable_player'],
            enable_pytest=args_dict['enable_pytest']
        )
        
        success = result.get('close_loop_world_generation_success', False)
        print(f"Worker {os.getpid()}: Task {global_task_index} completed (success: {success})")
        
        return (task_key, result, global_task_index, success)
        
    except Exception as e:
        print(f"Worker {os.getpid()}: Error processing task {global_task_index}: {e}")
        traceback.print_exc()
        
        # Create error result
        error_result = {
            "error": f"Processing failed: {str(e)}",
            "id": task_data.get('id', global_task_index),
            "gt_domain_raw": task_data.get('pddl_domain', ''),
            "gt_domain_without_comment": task_data.get('pddl_domain_processed', ''),
            "pred_domain": "",
            "domain_description": task_data.get('corrected_description', ''),
            "close_loop_world_generation_success": False,
            "validation_msg": "",
            "close_loop_world_generation_data": {
                "pred_domain": "",
                "correct_trace": [],
                "time": 0.0,
                "correction_process": {
                    "0": {
                        "domain_name": "error",
                        "domain": "",
                        "exec_info": ""
                    }
                }
            }
        }
        
        return (task_key, error_result, global_task_index, False)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run text2world multi-agent framework with parallel processing')
    
    # Basic arguments
    parser.add_argument('--dataset', type=str, required=True,
                       help='Path to the dataset file')
    parser.add_argument('--output', type=str, required=True,
                       help='Output directory for results')
    parser.add_argument('--benchmark_type', type=str, default='text2world',
                       help='Benchmark type identifier')
    
    # Batch processing arguments
    parser.add_argument('--batch_index', type=int, default=0,
                       help='Batch index for parallel processing')
    parser.add_argument('--batch_total', type=int, default=1,
                       help='Total number of batches')
    parser.add_argument('--max_tasks', type=int, default=None,
                       help='Maximum number of tasks to process (for testing)')
    parser.add_argument('--force_rerun', action='store_true',
                       help='Force rerun all tasks, ignoring existing results')
    
    # Ablation study arguments
    parser.add_argument('--disable_research', action='store_true',
                       help='Disable research agent')
    parser.add_argument('--disable_player', action='store_true',
                       help='Disable player agent')
    parser.add_argument('--disable_pytest', action='store_true',
                       help='Disable pytest agent')
    
    # Multi-worker arguments
    parser.add_argument('--num_workers', type=int, default=1,
                       help='Number of worker processes (default: 1, 0 for auto-detect)')
    parser.add_argument('--chunk_size', type=int, default=1,
                       help='Number of tasks per worker chunk (default: 1)')
    
    # Progress monitoring
    parser.add_argument('--progress_interval', type=int, default=10,
                       help='Progress reporting interval in seconds (default: 10)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose output')
    
    return parser.parse_args()


def print_progress_stats(completed: int, total: int, successful: int, start_time: float):
    """Print progress statistics"""
    elapsed = time.time() - start_time
    if completed > 0:
        avg_time = elapsed / completed
        eta = avg_time * (total - completed)
        success_rate = successful / completed * 100
        
        print(f"\n=== Progress Update ===")
        print(f"Completed: {completed}/{total} ({completed/total*100:.1f}%)")
        print(f"Successful: {successful} ({success_rate:.1f}%)")
        print(f"Elapsed: {elapsed:.1f}s, ETA: {eta:.1f}s")
        print(f"Average time per task: {avg_time:.1f}s")
        print("=" * 25)


def main():
    """Main function"""
    args = parse_args()

    # Auto-detect number of workers if set to 0
    if args.num_workers == 0:
        args.num_workers = multiprocessing.cpu_count()
        print(f"Auto-detected {args.num_workers} CPU cores, using {args.num_workers} workers")
    elif args.num_workers > 1:
        print(f"Using {args.num_workers} worker processes")

    # Ensure output directory exists
    if not os.path.exists(args.output):
        os.makedirs(args.output)

    # Create output filename based on ablation settings
    ablation_suffix = ""
    if args.disable_research:
        ablation_suffix += "_no_research"
    if args.disable_player:
        ablation_suffix += "_no_player"
    if args.disable_pytest:
        ablation_suffix += "_no_pytest"

    output_path = os.path.join(PROJECT_ROOT, args.output,
                              f'{args.benchmark_type}_multi_agent{ablation_suffix}_batch_{args.batch_index}_of_{args.batch_total}_results.json')

    # Load existing results
    results = load_existing_results(output_path)

    # Load dataset
    dataset_path = os.path.join(PROJECT_ROOT, args.dataset)
    dataset = load_text2world_dataset(dataset_path)

    # Limit number of tasks (for testing)
    if args.max_tasks:
        dataset = dataset[:args.max_tasks]
        print(f"Limiting tasks to process: {args.max_tasks}")

    # Validate batch parameters
    if args.batch_index < 0 or args.batch_index >= args.batch_total:
        raise ValueError(f"batch_index ({args.batch_index}) must be between 0 and {args.batch_total-1}")

    # Apply batch processing
    total_tasks_original = len(dataset)
    batch_size = (total_tasks_original + args.batch_total - 1) // args.batch_total  # 向上取整
    start_idx = args.batch_index * batch_size
    end_idx = min(start_idx + batch_size, total_tasks_original)

    # Split dataset for current batch
    dataset = dataset[start_idx:end_idx]
    print(f"Batch processing: {args.batch_index}/{args.batch_total-1}, processing tasks {start_idx}-{end_idx-1} ({len(dataset)} tasks)")

    # Initialize statistics variables
    total_tasks = len(dataset)
    skipped_tasks = 0
    processed_tasks = 0
    successful_tasks = 0
    new_successful_tasks = 0

    # Prepare tasks to process (filter out skipped tasks)
    tasks_to_process = []
    for i, task_data in enumerate(dataset):
        global_task_index = start_idx + i
        task_key = f"task_{global_task_index}"

        # Check if should skip this task
        if should_skip_task(task_key, results, args.force_rerun):
            print(f"Skipping task {global_task_index} (already has valid result)")
            skipped_tasks += 1
            # Update successful task count
            if results[task_key].get('close_loop_world_generation_success'):
                successful_tasks += 1
            continue

        tasks_to_process.append((task_data, global_task_index, task_key))

    print(f"Found {len(tasks_to_process)} tasks to process with {args.num_workers} workers")

    if len(tasks_to_process) == 0:
        print("No tasks to process!")
    elif args.num_workers == 1:
        # Single-threaded processing (original behavior)
        print("Using single-threaded processing")
        start_time = time.time()
        
        for idx, (task_data, global_task_index, task_key) in enumerate(tasks_to_process):
            print(f"Starting to process task {global_task_index} ({idx+1}/{len(tasks_to_process)})...")
            try:
                result = generate_pddl_for_task(
                    task_data,
                    args.benchmark_type,
                    task_key,
                    enable_research=not args.disable_research,
                    enable_player=not args.disable_player,
                    enable_pytest=not args.disable_pytest
                )

                # Save result immediately
                save_task_result(output_path, task_key, result, results)

                processed_tasks += 1
                if result.get('close_loop_world_generation_success'):
                    successful_tasks += 1
                    new_successful_tasks += 1

                print(f"Task {global_task_index} processed and saved")
                
                # Print progress periodically
                if (idx + 1) % 5 == 0 or idx + 1 == len(tasks_to_process):
                    print_progress_stats(idx + 1, len(tasks_to_process), new_successful_tasks, start_time)

            except Exception as e:
                print(f"Error occurred while processing task {global_task_index}: {e}")
                traceback.print_exc()
                processed_tasks += 1
    else:
        # Multi-threaded processing
        print(f"Using multi-threaded processing with {args.num_workers} workers")
        
        # Prepare arguments for worker processes
        args_dict = {
            'benchmark_type': args.benchmark_type,
            'enable_research': not args.disable_research,
            'enable_player': not args.disable_player,
            'enable_pytest': not args.disable_pytest
        }
        
        # Create thread lock for file operations
        file_lock = threading.Lock()
        
        # Process tasks with multiple workers
        start_time = time.time()
        last_progress_time = start_time
        
        with ProcessPoolExecutor(max_workers=args.num_workers) as executor:
            # Submit all tasks
            future_to_task = {}
            for task_info in tasks_to_process:
                future = executor.submit(process_single_task, task_info, args_dict)
                future_to_task[future] = task_info
            
            # Process completed tasks
            completed_count = 0
            for future in as_completed(future_to_task):
                try:
                    task_key, result, global_task_index, success = future.result()
                    
                    # Save result in thread-safe manner
                    save_task_result_thread_safe(output_path, task_key, result, file_lock)
                    
                    processed_tasks += 1
                    completed_count += 1
                    
                    if success:
                        successful_tasks += 1
                        new_successful_tasks += 1
                    
                    if args.verbose:
                        print(f"Task {global_task_index} processed and saved (success: {success})")
                    
                    # Print progress periodically
                    current_time = time.time()
                    if (current_time - last_progress_time >= args.progress_interval or 
                        completed_count == len(tasks_to_process)):
                        print_progress_stats(completed_count, len(tasks_to_process), new_successful_tasks, start_time)
                        last_progress_time = current_time
                    
                except Exception as e:
                    task_info = future_to_task[future]
                    _, global_task_index, _ = task_info
                    print(f"Task {global_task_index} generated an exception: {e}")
                    traceback.print_exc()
                    processed_tasks += 1

    # Final statistics
    total_time = time.time() - (start_time if 'start_time' in locals() else time.time())
    
    print(f"\n=== Processing Complete ===")
    print(f"Batch info: {args.batch_index}/{args.batch_total-1} (tasks {start_idx}-{end_idx-1})")
    print(f"Total tasks in this batch: {total_tasks}")
    print(f"Skipped tasks: {skipped_tasks}")
    print(f"Newly processed tasks: {processed_tasks}")
    print(f"Successful tasks: {successful_tasks}")
    print(f"Batch success rate: {successful_tasks/total_tasks*100:.1f}%")
    if processed_tasks > 0:
        print(f"New processing success rate: {new_successful_tasks/processed_tasks*100:.1f}%")
        print(f"Average processing time: {total_time/processed_tasks:.1f}s per task")
    print(f"Total processing time: {total_time:.1f}s")
    print(f"Results saved to: {output_path}")

    # Print processing settings summary
    print(f"\n=== Processing Settings ===")
    print(f"Number of workers: {args.num_workers}")
    print(f"Research enabled: {not args.disable_research}")
    print(f"Player enabled: {not args.disable_player}")
    print(f"Pytest enabled: {not args.disable_pytest}")


if __name__ == "__main__":
    main()