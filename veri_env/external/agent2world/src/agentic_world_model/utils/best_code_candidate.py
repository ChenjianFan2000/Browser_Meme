
from __future__ import annotations
from typing import List, Dict, Optional
from loguru import logger
from src.types import CodeReport, PlayReport, PytestReport

def select_best_code_candidate(code_candidates: List[Dict], current_best_code: Optional[Dict] = None) -> Dict:
    """
    从代码候选者列表中选择最佳代码
    
    Args:
        code_candidates: 代码候选者列表，每个候选者包含code, turn, play_success, pytest_success, pass_rate, feedback
        current_best_code: 当前最佳代码（可选）
    
    Returns:
        最佳代码候选者字典
    """
    # 确保返回值永远不是 None
    default_candidate = {
        'code': "",
        'turn': 0,
        'play_success': False,
        'pytest_success': False,
        'pass_rate': 0.0,
        'feedback': {}
    }
    
    if not code_candidates:
        return current_best_code if current_best_code is not None else default_candidate
    
    # 过滤掉无效的候选者
    valid_candidates = []
    for candidate in code_candidates:
        if isinstance(candidate, dict) and 'code' in candidate:
            # 确保所有必需的字段都存在
            candidate.setdefault('pass_rate', 0.0)
            candidate.setdefault('pytest_success', False)
            candidate.setdefault('play_success', False)
            candidate.setdefault('turn', 0)
            candidate.setdefault('feedback', {})
            valid_candidates.append(candidate)
    
    if not valid_candidates:
        return current_best_code if current_best_code is not None else default_candidate
    
    # 选择当前候选者中的最佳代码
    try:
        current_best = max(valid_candidates, key=lambda x: (
            float(x.get('pass_rate', 0.0)),  # 确保是数字类型
            bool(x.get('pytest_success', False)),
            bool(x.get('play_success', False)),
            int(x.get('turn', 0))
        ))
    except (ValueError, TypeError) as e:
        logger.error(f"Error selecting best candidate: {e}")
        return current_best_code if current_best_code is not None else default_candidate
    
    # 如果没有历史最佳代码，直接返回当前最佳
    if current_best_code is None:
        logger.info(f"Selected initial best code from turn {current_best['turn']} with pass_rate: {current_best['pass_rate']}")
        return current_best
    
    # 比较当前最佳和历史最佳
    try:
        current_pass_rate = float(current_best.get('pass_rate', 0.0))
        best_pass_rate = float(current_best_code.get('pass_rate', 0.0))
        current_pytest_success = bool(current_best.get('pytest_success', False))
        best_pytest_success = bool(current_best_code.get('pytest_success', False))
        
        # 更新最佳代码的条件：首先比较pass_rate，如果相同则比较pytest_success
        if (current_pass_rate > best_pass_rate) or (
            current_pass_rate == best_pass_rate and 
            current_pytest_success > best_pytest_success
        ) or (
            current_pass_rate == best_pass_rate and 
            current_pytest_success == best_pytest_success and
            bool(current_best.get('play_success', False)) > bool(current_best_code.get('play_success', False))
        ) or (
            current_pass_rate == best_pass_rate and 
            current_pytest_success == best_pytest_success and
            bool(current_best.get('play_success', False)) == bool(current_best_code.get('play_success', False)) and
            int(current_best.get('turn', 0)) > int(current_best_code.get('turn', 0))
        ):
            logger.info(f"Updated best code from turn {current_best['turn']} (pass_rate: {current_best['pass_rate']}, pytest: {current_best['pytest_success']}) replacing turn {current_best_code['turn']} (pass_rate: {current_best_code['pass_rate']}, pytest: {current_best_code['pytest_success']})")
            return current_best
        
        logger.debug(f"Keeping current best code from turn {current_best_code['turn']} with pass_rate: {current_best_code['pass_rate']}")
        return current_best_code
        
    except (ValueError, TypeError) as e:
        logger.error(f"Error comparing candidates: {e}")
        return current_best_code if current_best_code is not None else default_candidate

def create_code_candidate(code_report: CodeReport, currency_turn: int, 
                         play_resport: PlayReport, pytest_report, feedback: Dict) -> Dict:
    """
    创建代码候选者字典
    
    Args:
        code_report: 代码报告
        currency_turn: 当前轮数
        play_resport: 游戏测试报告
        pytest_report: 单元测试报告
        feedback: 反馈信息
    
    Returns:
        代码候选者字典
    """
    try:
        # 安全地提取代码
        code = ""
        if code_report and hasattr(code_report, 'entrypoint_code'):
            code = str(code_report.entrypoint_code)
        
        # 安全地提取 play 结果
        play_success = False
        pass_rate = 0.0
        if play_resport:
            play_success = getattr(play_resport, 'success', False)
            pass_rate = getattr(play_resport, 'pass_rate', 0.0)
            # 确保 pass_rate 是有效的数字
            if pass_rate is None or not isinstance(pass_rate, (int, float)):
                pass_rate = 0.0
            else:
                pass_rate = float(pass_rate)
        
        # 安全地提取 pytest 结果
        pytest_success = False
        if pytest_report:
            pytest_success = getattr(pytest_report, 'success', False)
        
        # 确保 feedback 是字典
        if not isinstance(feedback, dict):
            feedback = {}
        
        candidate = {
            'code': code,
            'turn': int(currency_turn),
            'play_success': bool(play_success),
            'pytest_success': bool(pytest_success),
            'pass_rate': pass_rate,
            'feedback': feedback
        }
        
        logger.debug(f"Created candidate for turn {currency_turn}: play_success={candidate['play_success']}, pytest_success={candidate['pytest_success']}, pass_rate={candidate['pass_rate']}")
        return candidate
        
    except Exception as e:
        logger.error(f"Error creating code candidate: {e}")
        # 返回默认候选者
        return {
            'code': "",
            'turn': int(currency_turn) if isinstance(currency_turn, (int, float)) else 0,
            'play_success': False,
            'pytest_success': False,
            'pass_rate': 0.0,
            'feedback': {}
        }


def should_terminate_early(best_code: Optional[Dict], currency_turn: int, max_turn: int) -> bool:
    """
    判断是否应该提前终止迭代
    
    Args:
        best_code: 当前最佳代码
        currency_turn: 当前轮数
        max_turn: 最大轮数
    
    Returns:
        是否应该提前终止
    """
    try:
        # 达到最大轮数
        if currency_turn >= max_turn:
            return True
        
        # 如果没有最佳代码，不提前终止
        if not best_code or not isinstance(best_code, dict):
            return False
        
        # 如果通过率达到100%，可以提前终止
        pass_rate = best_code.get('pass_rate', 0)
        if pass_rate is not None and float(pass_rate) >= 1.0:
            logger.info(f"Early termination: achieved perfect pass_rate (1.0) at turn {best_code.get('turn', 'unknown')}")
            return True
        
        return False
        
    except (ValueError, TypeError) as e:
        logger.error(f"Error in should_terminate_early: {e}")
        # 如果出错，按最大轮数判断
        return currency_turn >= max_turn

