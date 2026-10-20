from __future__ import annotations
from typing import Dict
from loguru import logger
from src.agents import BaseAgent, ChatAgent
from src.models import ModelFactory
from src.types import ModelPlatformType, ModelType
from src.toolkits import (
    FunctionTool,
    WebSearchWithSummaryToolkit,
    SandboxToolkit,
    PlayerEnvToolkit
)

from src.types import (
    CodeReport,
    PlayReport,
    PytestReport,
)

from .utils import extract_payload_from_response,WorldModelPromptBase,extract_all_finals
from .utils.best_code_candidate import select_best_code_candidate, create_code_candidate, should_terminate_early

def initialize_agent(
    benchmark_type: str,
    results_base_dir: str,
    simulator=None,
    # Ablation study control parameters
    model_platform: ModelPlatformType = ModelPlatformType.OPENROUTER,
    model_name: str = "deepseek/deepseek-chat",
    enable_research: bool = True,
    enable_player: bool = True,
    enable_pytest: bool = True,
    max_tokens: int = 30000,
) -> Dict[str, BaseAgent]:
    ## Create model
    research_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENROUTER,
        model_type=ModelType.OPENROUTER_GPT_4_1_MINI,
        model_config_dict={"temperature": 0},
    )
    code_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENROUTER,
        model_type=ModelType.OPENROUTER_GPT_4_1_MINI,
        model_config_dict={"temperature": 0},
    )
    pytest_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENROUTER,
        model_type=ModelType.OPENROUTER_GPT_4_1_MINI,
        model_config_dict={"temperature": 0},
    )
    play_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENROUTER,
        model_type=ModelType.OPENROUTER_GPT_4_1_MINI,
        model_config_dict={"temperature": 0},
    )
    
    ## Create toolkit
    web_search_toolkit = WebSearchWithSummaryToolkit(preferred_provider="serper")
    sandbox_toolkit = SandboxToolkit(
        default_file_map={
            "utils/*": "utils",
        },
        default_requirements=["requests", "retry", "pytest", "numpy", "tarski", "openai", "pddlgym"],
        timeout_minutes=120
    )
    
    sandbox_toolkit.run_code("import tarski\nimport re",["tarski"])
    
    player_env_toolkit = PlayerEnvToolkit(
        benchmark_type,
        sandbox_toolkit,
        simulator
    )

    agents = {
        "sandbox": sandbox_toolkit,
    }
    
    # Create agents based on ablation settings
    if enable_research:
        agents["research"] = ChatAgent(
            system_message="You are a helpful assistant", 
            model=research_model,
            tools=[
                FunctionTool(web_search_toolkit.browser_search),
                FunctionTool(web_search_toolkit.browser_open),
            ],
            auto_save=True,
            max_turn=3,
            results_base_dir=results_base_dir + "/research/"
        )
    
    # Code agent is always needed as it's a core component
    code_tools = []
    if benchmark_type == "text2world":
        code_tools = [
            FunctionTool(sandbox_toolkit.file_tool),
            FunctionTool(sandbox_toolkit.run_bash),
        ]

    agents["code"] = ChatAgent(
        system_message="You are a helpful assistant", 
        model=code_model,
        tools=code_tools,
        auto_save=True,
        max_turn=3,
        results_base_dir=results_base_dir + "/code/"
    )

    if enable_player:
        agents["play"] = ChatAgent(
            system_message="You are a helpful assistant", 
            model=play_model,
            tools=[
                FunctionTool(sandbox_toolkit.file_tool),
                FunctionTool(player_env_toolkit.play_env),
            ],
            auto_save=True,
            results_base_dir=results_base_dir + "/play/"
        )
        
    if enable_pytest:
        agents["pytest"] = ChatAgent(
            system_message="You are a helpful assistant", 
            model=pytest_model,
            tools=[
                FunctionTool(sandbox_toolkit.file_tool),
                FunctionTool(sandbox_toolkit.run_bash),
            ],
            auto_save=True,
            results_base_dir=results_base_dir + "/pytest/"
        )
    
    return agents

def agent2world_gen_code(
    agent2world_agents: Dict[str, BaseAgent], 
    prompt_generator: WorldModelPromptBase,
    # Ablation control parameters
    enable_research: bool = True,
    enable_player: bool = True,
    enable_pytest: bool = True
) -> str:
    logger.info("Generate the world model report")
    
    if enable_research and "research" in agent2world_agents:
        research_prompt = prompt_generator.build_research_prompt()
        research_report = agent2world_agents["research"].step(research_prompt)
        research_report = extract_all_finals(research_report)
    else:
        research_report = "No research phase enabled for this ablation study."
        logger.info("Skipping research phase (ablation study)")
    prompt_generator.research_report = research_report
    once_research_report = research_report 
    feedback = {}  
    max_turn = 3
    current_turn = 0  
    
    while True:
        logger.info("Generate the code" if once_research_report else "Fix the code")
        gen_code_prompt = prompt_generator.build_gen_code_prompt(once_research_report, feedback)
        once_research_report = None
        raw_code_report = agent2world_agents["code"].step(gen_code_prompt, CodeReport)
        code_report: CodeReport = extract_payload_from_response(raw_code_report, CodeReport)
        
        if not hasattr(code_report, "code_file_path") or not hasattr(code_report, "entrypoint_code"):
            return ""
        agent2world_agents["sandbox"].file_tool("save", code_report.code_file_path, code_report.entrypoint_code)
        
        current_turn += 1
        if current_turn == max_turn:
            return str(code_report.entrypoint_code)
        
        feedback = {}
        feedback["source_code"] = code_report.entrypoint_code

        # Execute play phase based on ablation settings
        if enable_player and "play" in agent2world_agents:
            logger.info("Play the code")
            player_prompt = prompt_generator.build_play_env_prompt(code_report.entrypoint_code, code_report.code_file_path)
            try:
                raw_play_report = agent2world_agents["play"].step(player_prompt, PlayReport)
                play_report: PlayReport = extract_payload_from_response(raw_play_report, PlayReport)
                feedback["play"] = play_report.model_dump()
                play_success = play_report.success
            except Exception as e:
                play_report = PlayReport(success=False, pass_rate=0.0, analysis=str(e), suggest_fix="")
                feedback["play"] = play_report.model_dump()
                play_success = False
        else:
            logger.info("Skipping play phase (ablation study)")
            play_success = True
        
        # Execute pytest phase based on ablation settings
        if enable_pytest and "pytest" in agent2world_agents:
            logger.info("Pytest the code")
            pytest_prompt = prompt_generator.build_pytest_env_prompt(code_report.entrypoint_code, code_report.code_file_path)
            try:
                raw_pytest_report = agent2world_agents["pytest"].step(pytest_prompt, PytestReport)
                pytest_report: PytestReport = extract_payload_from_response(raw_pytest_report, PytestReport)
                feedback["pytest"] = pytest_report.model_dump()
                pytest_success = pytest_report.success
            except Exception as e:
                pytest_report = PytestReport(success=False, analysis=str(e), suggest_fix="")
                feedback["pytest"] = pytest_report.model_dump()
                pytest_success = False
        else:
            logger.info("Skipping pytest phase (ablation study)")
            pytest_success = True
        
        logger.debug(f"play_success: {play_success} pytest_success: {pytest_success}")
        
        # Return code if both phases succeed (or are skipped)
        if play_success and pytest_success:
            return str(code_report.entrypoint_code)
        else:
            if current_turn < max_turn:
                agent2world_agents["code"].reset()
                # Reset only existing agents
                if enable_player and "play" in agent2world_agents:
                    agent2world_agents["play"].reset()
                if enable_pytest and "pytest" in agent2world_agents:
                    agent2world_agents["pytest"].reset()

def agent2world_gen_cwmb_code(
    agent2world_agents: Dict[str, BaseAgent], 
    prompt_generator: WorldModelPromptBase,
    # Ablation control parameters
    enable_research: bool = True,
    enable_player: bool = True,
    enable_pytest: bool = True
) -> str:
    logger.info("Generate the world model report")
    
    try:
        if enable_research and "research" in agent2world_agents:
            research_prompt = prompt_generator.build_research_prompt()
            research_report = agent2world_agents["research"].step(research_prompt)
            research_report = extract_all_finals(research_report)
        else:
            research_report = "No research phase enabled for this ablation study."
            logger.info("Skipping research phase (ablation study)")
    except Exception as e:
        logger.error(f"Error in research phase: {e}")
        research_report = "Error in research phase."
    prompt_generator.research_report = research_report
    
    feedback = ""
    max_turn = 3
    currency_turn = 0
    
    # Dictionary to store all code versions and their metrics
    code_candidates = []
    best_code = None
    debug = False
    
    while True:
        if debug:
            message = f"Turn {currency_turn}/{max_turn} Fix the code"
        elif feedback:
            message = f"Turn {currency_turn}/{max_turn} Improve the code" 
        else:
            message = f"Turn {currency_turn}/{max_turn} Generate the code"
        logger.info(message)
        
        gen_code_prompt = prompt_generator.build_gen_code_prompt(feedback,debug)
        debug = False
        raw_code_report = agent2world_agents["code"].step(gen_code_prompt, CodeReport)
        code_report: CodeReport = extract_payload_from_response(raw_code_report, CodeReport)
        
        if not hasattr(code_report, "code_file_path") or not hasattr(code_report, "entrypoint_code"):
            return ""
        agent2world_agents["sandbox"].file_tool("save", code_report.code_file_path, code_report.entrypoint_code)
        
        currency_turn += 1
        
        feedback = {}
        feedback["source_code"] = code_report.entrypoint_code
        
        # Execute play phase based on ablation settings
        if enable_player and "play" in agent2world_agents:
            logger.info("Play the code")
            player_prompt = prompt_generator.build_play_env_prompt(code_report.entrypoint_code, code_report.code_file_path)
            try:
                raw_play_resport = agent2world_agents["play"].step(player_prompt, PlayReport)
                play_resport: PlayReport = extract_payload_from_response(raw_play_resport, PlayReport)
                feedback["play"] = play_resport.model_dump()
            except Exception:
                play_resport = type('PlayReport', (), {'success': False, 'pass_rate': 0.0})()
        else:
            logger.info("Skipping play phase (ablation study)")
            # Create a default successful play report
            play_resport = type('PlayReport', (), {'success': True, 'pass_rate': 0.5})()
        
        # Execute pytest phase based on ablation settings
        if enable_pytest and "pytest" in agent2world_agents:
            logger.info("Pytest the code")
            pytest_prompt = prompt_generator.build_pytest_env_prompt(code_report.entrypoint_code, code_report.code_file_path)
            try:
                raw_pytest_report = agent2world_agents["pytest"].step(pytest_prompt, PytestReport)
                pytest_report: PytestReport = extract_payload_from_response(raw_pytest_report, PytestReport)
                feedback["pytest"] = pytest_report.model_dump()
            except Exception:
                pytest_report = type('PytestReport', (), {'success': False})()
        else:
            logger.info("Skipping pytest phase (ablation study)")
            # Create a default successful pytest report
            pytest_report = type('PytestReport', (), {'success': True})()
        
        logger.debug(f"play_success: {play_resport.success} pytest_success: {pytest_report.success}")
        
        # Create current code candidate
        candidate = create_code_candidate(
            code_report, currency_turn, play_resport, pytest_report, feedback
        )
        code_candidates.append(candidate)
        
        # Select best code
        best_code = select_best_code_candidate(code_candidates, best_code)
        
        # Check if should terminate early
        if should_terminate_early(best_code, currency_turn, max_turn):
            logger.info(f"Final best code from turn {best_code['turn']} with pass_rate: {best_code['pass_rate']}")
            return best_code['code']
        
        # Prepare feedback for next round based on current best code's feedback
        if best_code and best_code['feedback']:
            feedback = best_code['feedback']
            debug = not best_code['pytest_success']
            logger.info(f"Using feedback from best code (turn {best_code['turn']}) for next iteration")
        
        if currency_turn + 1 != max_turn:
            agent2world_agents["code"].reset()
            if enable_player and "play" in agent2world_agents:
                agent2world_agents["play"].reset()
            if enable_pytest and "pytest" in agent2world_agents:
                agent2world_agents["pytest"].reset()

def agent2world_gen_pddl_code(
    agent2world_agents: Dict[str, BaseAgent], 
    prompt_generator: WorldModelPromptBase,
    task_describe: str,
    # Ablation control parameters
    enable_research: bool = True,
    enable_player: bool = True,
    enable_pytest: bool = True
) -> str:
    logger.info("Generate the world model report")
    
    if enable_research and "research" in agent2world_agents:
        research_prompt = prompt_generator.build_research_prompt()
        research_report = agent2world_agents["research"].step(research_prompt)
        research_report = extract_all_finals(research_report)
    else:
        research_report = "No research phase enabled for this ablation study."
        logger.info("Skipping research phase (ablation study)")
    prompt_generator.research_report = research_report
    once_research_report = research_report 
    feedback = {}  
    max_turn = 3
    current_turn = 0  
    
    while True:
        logger.info("Generate the code" if once_research_report else "Fix the code")
        gen_code_prompt = prompt_generator.build_gen_code_prompt(once_research_report, feedback)
        once_research_report = None
        raw_code_report = agent2world_agents["code"].step(gen_code_prompt, CodeReport)
        code_report: CodeReport = extract_payload_from_response(raw_code_report, CodeReport)
        
        if not hasattr(code_report, "code_file_path") or not hasattr(code_report, "entrypoint_code"):
            return ""
        agent2world_agents["sandbox"].file_tool("save", code_report.code_file_path, code_report.entrypoint_code)
        
        current_turn += 1
        if current_turn == max_turn:
            return str(code_report.entrypoint_code)
        
        feedback = {}
        feedback["source_code"] = code_report.entrypoint_code
        
        # Execute play phase based on ablation settings
        if enable_player and "play" in agent2world_agents:
            logger.info("Play the code")
            player_prompt = prompt_generator.build_play_env_prompt(code_report.entrypoint_code, code_report.code_file_path)
            raw_play_report = agent2world_agents["play"].step(player_prompt, PlayReport)
            play_report: PlayReport = extract_payload_from_response(raw_play_report, PlayReport)
            feedback["play"] = play_report.model_dump()
            play_success = play_report.success
        else:
            logger.info("Skipping play phase (ablation study)")
            play_success = True
        
        # Execute pytest phase based on ablation settings
        if enable_pytest and "pytest" in agent2world_agents:
            logger.info("Pytest the code")
            pytest_prompt = prompt_generator.build_pytest_env_prompt(code_report.entrypoint_code, code_report.code_file_path, task_describe)
            raw_pytest_report = agent2world_agents["pytest"].step(pytest_prompt, PytestReport)
            pytest_report: PytestReport = extract_payload_from_response(raw_pytest_report, PytestReport)
            feedback["pytest"] = pytest_report.model_dump()
            pytest_success = pytest_report.success
        else:
            logger.info("Skipping pytest phase (ablation study)")
            pytest_success = True
        
        logger.debug(f"play_success: {play_success} pytest_success: {pytest_success}")
        
        # Return code if both phases succeed (or are skipped)
        if play_success and pytest_success:
            return str(code_report.entrypoint_code)
        else:
            if current_turn < max_turn:
                agent2world_agents["code"].reset()
                # Reset only existing agents
                if enable_player and "play" in agent2world_agents:
                    agent2world_agents["play"].reset()
                if enable_pytest and "pytest" in agent2world_agents:
                    agent2world_agents["pytest"].reset()
