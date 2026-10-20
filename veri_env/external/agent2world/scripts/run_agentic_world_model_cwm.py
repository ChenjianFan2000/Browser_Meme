import os
import sys
import json
import time
import fire
import numpy as np
import shutil
import multiprocessing as mp
from functools import partial

# Determine the project root by going up three directory levels from this file
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add project root to import path
sys.path.append(PROJECT_ROOT)

from src.cwm_benchmark.generate_env_agentic_world_model import generate_solutions,only_test

env_ids_and_planners = {
    'Blackjack-v1': 'mcts',  # 0
    'CliffWalking-v0': 'mcts',  # 1
    'Taxi-v3': 'mcts',  # 2
    'CartPole-v1': 'mcts',  # 3
    'MountainCar-v0': 'mcts',  # 4
    'Acrobot-v1': 'mcts',  # 5
    'Pendulum-v1': 'cem',  # 6
    'Reacher-v4': 'cem',  # 7
    'Pusher-v4': 'cem',  # 8
    'InvertedPendulum-v4': 'cem',  # 9
    'InvertedDoublePendulum-v4': 'cem',  # 10
    'HalfCheetah-v4': 'cem',  # 11
    'Hopper-v4': 'cem',  # 12
    'Swimmer-v4': 'cem',  # 13
    'Walker2d-v4': 'cem',  # 14
    'Ant-v4': 'cem',  # 15
    'Humanoid-v4': 'cem',  # 16
    'HumanoidStandup-v4': 'cem'  # 17
}


def is_environment_processed(environment, save_dir):
    """
    Check if the environment has already been processed.

    If either 'CliffWalking-v0' or 'CliffWalking-v1' exists with a non-empty 
    'best_code_rollout.py' file, return True. 
    If 'CliffWalking-v0' exists and 'CliffWalking-v1' does not, 
    rename the directory from v0 to v1.

    Args:
        environment (str): Environment name.
        save_dir (str): Directory to search for processed environments.

    Returns:
        bool: True if either v0 or v1 has already been processed; otherwise False.
    """
    # List of environment names to check (handles both v0 and v1 for CliffWalking)
    env_names = [environment]
    if environment == 'CliffWalking-v0':
        env_names.append('CliffWalking-v1')

    for env_name in env_names:
        env_dir = os.path.join(save_dir, env_name)
        result_file = os.path.join(env_dir, "best_code_rollout.py")
        # Check if result file exists and is not empty
        if os.path.exists(result_file) and os.path.getsize(result_file) > 0:
            # If v0 exists but v1 does not, rename directory to v1
            if env_name == 'CliffWalking-v0':
                v1_dir = os.path.join(save_dir, 'CliffWalking-v1')
                if not os.path.exists(v1_dir):
                    shutil.move(env_dir, v1_dir)
            return True
    return False


def process_single_environment(args):
    """
    Process a single environment. This function is designed to be called by multiprocessing.
    
    Args:
        args (tuple): Contains (i, environment, model, hf_cache, budget, save_dir, log_params, kwargs)
    
    Returns:
        tuple: (environment_index, environment_name, success_status)
    """
    i, environment, model, hf_cache, budget, save_dir, log_params, enable_research, enable_player, enable_pytest, kwargs = args
    
    try:
        print(f"\n=== [Process {os.getpid()}] Running environment [{i}]: {environment} ===")
        
        generate_solutions(
            model,
            environment,
            hf_cache,
            budget,
            save_dir,
            log_params,
            enable_research=enable_research,
            enable_player=enable_player,
            enable_pytest=enable_pytest,
            **kwargs
        )
        
        print(f"✅ [Process {os.getpid()}] Completed environment [{i}]: {environment}")
        return (i, environment, True)
        
    except Exception as e:
        print(f"❌ [Process {os.getpid()}] Failed environment [{i}]: {environment} - Error: {str(e)}")
        return (i, environment, False)


def main(
    idx=[],           # None, single int, list of ints, or 'all'
    model=None,
    env=None,
    hf_cache=None,
    budget=1,
    log_file=False,
    log_level="INFO",
    save_dir="results/cwm/default_exp",
    skip_processed=True,
    enable_research=True,
    enable_player=True,
    enable_pytest=True,
    num_processes=None,  # 新增参数：进程数量
    **kwargs
):
    """
    Entry point for running experiments:
    - If idx is empty, runs all environments in env_ids_and_planners.
    - Otherwise, runs only the specified indices.
    - If skip_processed is True, skips environments that have already been processed.
    - Uses multiprocessing to run environments in parallel.

    Additional parameters are forwarded to generate_solutions().
    
    Args:
        enable_research (bool): Enable research component (default: True)
        enable_player (bool): Enable player component (default: True) 
        enable_pytest (bool): Enable pytest component (default: True)
        num_processes (int): Number of parallel processes (default: CPU count)
    """
    # Set default number of processes to CPU count
    if num_processes is None:
        num_processes = mp.cpu_count()
    
    print(f"🚀 Starting experiments with {num_processes} parallel processes")
    
    # Set up logging configuration dictionary
    log_params = {
        'log_file': log_file,
        'log_level': log_level,
    }

    # Get the list of environment IDs (in order)
    list_of_env_ids = list(env_ids_and_planners.keys())

    if isinstance(idx, int):
        idx = [idx]
    
    if len(idx) == 0:
        idx = [i for i in range(len(list_of_env_ids))]
    
    # Filter environments to process
    environments_to_process = []
    for i in idx:
        if i < 0 or i >= len(list_of_env_ids):
            print(f"⚠️  Skipping invalid index {i} (out of range)")
            continue

        environment = list_of_env_ids[i]
        
        # check if environment has already been processed
        if skip_processed and is_environment_processed(environment, save_dir):
            print(f"⏭️  Skipping environment [{i}]: {environment} (already processed)")
            continue
            
        environments_to_process.append((i, environment))
    
    if not environments_to_process:
        print("📝 No environments to process.")
        return
    
    print(f"📋 Processing {len(environments_to_process)} environments: {[env[1] for env in environments_to_process]}")
    
    # Prepare arguments for multiprocessing
    process_args = []
    for i, environment in environments_to_process:
        args = (i, environment, model, hf_cache, budget, save_dir, log_params, 
                enable_research, enable_player, enable_pytest, kwargs)
        process_args.append(args)
    
    # Run environments in parallel using multiprocessing
    start_time = time.time()
    
    if num_processes == 1:
        # Sequential processing for debugging
        print("🔄 Running in sequential mode (num_processes=1)")
        results = [process_single_environment(args) for args in process_args]
    else:
        # Parallel processing
        print(f"🔄 Running in parallel mode with {num_processes} processes")
        with mp.Pool(processes=num_processes) as pool:
            results = pool.map(process_single_environment, process_args)
    
    end_time = time.time()
    
    # Print summary
    successful = [r for r in results if r[2]]
    failed = [r for r in results if not r[2]]
    
    print(f"\n{'='*60}")
    print(f"📊 EXPERIMENT SUMMARY")
    print(f"{'='*60}")
    print(f"⏱️  Total time: {end_time - start_time:.2f} seconds")
    print(f"✅ Successful: {len(successful)}/{len(results)}")
    print(f"❌ Failed: {len(failed)}/{len(results)}")
    
    if successful:
        print(f"\n✅ Successful environments:")
        for i, env, _ in successful:
            print(f"   [{i}] {env}")
    
    if failed:
        print(f"\n❌ Failed environments:")
        for i, env, _ in failed:
            print(f"   [{i}] {env}")
    
    print(f"{'='*60}")


if __name__ == "__main__":
    # Set multiprocessing start method for compatibility
    mp.set_start_method('spawn', force=True)
    fire.Fire(main)