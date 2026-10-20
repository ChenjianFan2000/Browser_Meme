import json
import os
import concurrent.futures
import requests
import time
import random
from typing import List, Dict, Any, Tuple, Union, Optional
from loguru import logger
from copy import deepcopy
from threading import Lock
import re
from openai import OpenAI
from codetiming import Timer
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from threading import Lock

SEARCH_MODEL_IP_LIST = [
    "29.81.228.116"
]

_SEARCH_CLIENT = OpenAI(
    base_url=f"http://{SEARCH_MODEL_IP_LIST[0]}:8000/v1",
    api_key="EMPTY",
)

SEARCH_MODEL_NAME = _SEARCH_CLIENT.models.list().data[0].id

file_lock = Lock()


def extract_data_from_tags(text: str, tag: str) -> str:
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start_index = text.find(start_tag)
    end_index = text.find(end_tag, start_index)
    if start_index != -1 and end_index != -1:
        return text[start_index + len(start_tag):end_index].strip()
    return ""


def process_prompt(question: str) -> List[Dict[str, str]]:

    tool_list = [{
        "name": "search_web",
        "description": "Search the web for information using duckduckgo",
        "parameters": {
            "type": "dict",
            "properties": {
                "query": {
                    "description": "The query to search the web for",
                    "type": "string"
                }
            },
            "required": ["query"]
        }
    }]

    prompt = f"""
    Solve the following problem step by step. 
    You now have the ability to selectively use tools to enhance your reasoning process. 
    The tool's output (wrapped in `<function_result>output_str</function_result>`) can be returned to aid your reasoning and help you arrive at the final answer. 
    Each function call should be wrapped with `<function_call>[TOOL CALL HERE]</function_call>`.
    The tool call should be in JSON format, including `name` and `arguments` keys.
    You should use tools when you are thinking. Do not use tools when you are thinking.
    Here are the tools you can use:
    {json.dumps(tool_list)}

    Now please solve the following problem: 
    
    {question}
    
    Remember to place the final answer in the last part using the format: \n<answer>\n[YOUR ANSWER HERE]\n</answer>
    """
    chat_messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that invoke tools to solve problems step by step."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    return chat_messages


def ask_search_llm(prompt, temperature):
    # random select a search model ip
    search_model_ip = random.choice(SEARCH_MODEL_IP_LIST)

    search_client = OpenAI(
        base_url=f"http://{search_model_ip}:8000/v1",
        api_key="EMPTY",
    )

    while(1):
        try:
            # 准备内容列表
            content = [{"type": "text", "text": prompt}]

            chat_response = search_client.chat.completions.create(
                model=SEARCH_MODEL_NAME,
                max_tokens=1024,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": ""},
                    {
                        "role": "user",
                        "content": content
                    },
                ],
            )

            return chat_response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in asking search llm: {e}")
            time.sleep(3)
            continue


def _search_simulate_sft(temperature, query, problem, ground_truth):
    gt_threshold = 0.5
    prob = random.random()
    if prob > gt_threshold:
        prompt = f'''You are the Google search engine.
Given a query, you need to generate five useful documents for the query.

The user is trying to answer the question: "{problem}" whose answer is {ground_truth}.
Each document should contain about 30 words, and these documents should contain useful information.

Query: {query}
Useful Output:
'''
    else:
        prompt = f'''You are the Google search engine.
Given a query, you need to generate five noisy documents for the query.

The user is trying to answer the question: "{problem}" whose answer is {ground_truth}.
Each document should contain about 30 words, and these documents should contain noisy information.

Query: {query}
Noisy Output:
'''
    # logger.debug(f"query: {query}")
    results = ask_search_llm(prompt, temperature)
    # logger.debug(f"resuts: {resuts}")
    return '\n'.join(results.replace('\n\n', '\n').split('\n')[:5])


def parse_and_execute_function_call(problem, ground_truth, function_call: Union[str, Dict]): 
    try:
        if isinstance(function_call, str):
            function_call = eval(function_call)

        function_name = function_call['name']
        function_args = function_call['arguments']
        if function_name == 'search_web':
            query = function_args['query']
            return _search_simulate_sft(1, query, problem, ground_truth)
        else:
            print(f"Unknown function name: {function_name}")
            return f"Error: Unknown function name: {function_name}"
    
    except Exception as e:
        print(f"Error parsing and executing function call: {e}")
        return f"Error: {str(e)}"


def load_json_data(data_path: str) -> list:
    with open(data_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def get_processed_data_ids(save_path: str) -> set:
    processed_ids = set()
    if not os.path.exists(save_path):
        return processed_ids
    
    try:
        with open(save_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if isinstance(data, list):
                        data = data[1]
                    processed_ids.add(get_data_id(data))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning(f"Error: {e}")
    
    return processed_ids


def get_data_id(data: Dict[str, Any]) -> str:
    # 确保返回的值是可哈希的
    return data['id']


def call_model(chat_messages: List[Dict[str, str]]) -> Tuple[str, str, str]:

    model_name = "DeepSeek-R1-0528-offline-crawl-gz-v1"
    # model_name = "DeepSeekV3-0324-SGL-nj"
    query_id = str(int(time.time() * 1000)) + str(random.randint(0, 9999))
    
    interface = 'http://stream-server-offline-10274.turbotke.production.polaris:81/openapi/chat/completions'
    headers = {"Content-Type": "application/json", "Authorization": "Bearer 7auGXNATFSKl7dF", "Wsid": "10103"}

    params = {
        #"user_session_id": user_session_id,
        "query_id": query_id,
        "model": model_name,
        "messages": chat_messages,
        "model_type":"hunyuan",
        # "temperature":0.3,"top_p":1,"top_k":40,"output_seq_len":4096,"max_input_seq_len":8192,"repetition_penalty":1,
        "temperature":0.3,
        "top_p":1,
        "top_k":40,
        "output_seq_len":16384,
        "max_input_seq_len":16384,
        "repetition_penalty":1,
        "debug_level":0,
        "stream":False,
        "random_seed":5610,
        "debug_flag":0,
        "compatible_with_openai": True,
        "stop": ["</answer>", "</function_call>"]
        # "stop": ["wait", "DeepSeek", "Wait", "First"]
    }
    # Max tries: 5, if extracted content is empty, retry

    tries = 6

    while tries > 0:

        try:
            raw_resp = requests.post(url=interface, json=params, headers=headers, stream=False)
            # Time
            print(f"{time.strftime(r'%m%d-%H:%M:%S')}: Response status code: {raw_resp.status_code}")
            resp_content_dict = json.loads(raw_resp.text)
            one_answer = resp_content_dict['choices'][0]['message']['content']
            reasoning_content = resp_content_dict['choices'][0]['message']['reasoning_content']
            logger.debug(f"Reasoning content: {reasoning_content}\n\n")
            logger.debug(f"One answer: {one_answer}\n\n")
            stop_reason = ""

            if len(one_answer) == 0:
                stop_reason = judge_stop_reason(reasoning_content)
            else:
                stop_reason = judge_stop_reason(one_answer)

            return one_answer, reasoning_content, stop_reason


        except Exception as e:
            logger.warning(f"Error in calling model: {e}")
            continue
    
    logger.warning(f"Failed to call model after 5 tries.")
    return "", "", ""


def judge_stop_reason(text: str) -> str:
    if "</a" in text:
        return "answer"
    elif "</f" in text:
        return "function_call"
    else:
        return ""


def judge_answer(question: str, answer: str, ground_truth: str) -> bool:
    prompt = f"""
You are a helpful assistant that can judge whether the model's output is semantically consistent with the ground truth.
Please judge whether the model's output is correct.
If it is correct, return only "correct".
If it is incorrect, return only "incorrect".
Please only return "correct" or "incorrect".

The question is {question}.
The ground truth is {ground_truth}.
The model's output is {answer}.
Your judgement:
"""
    chat_messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that can judge whether the model's output is semantically consistent with the ground truth."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    one_answer, reasoning_content, _ = call_model(chat_messages)

    if "incorrect" in one_answer.lower():
        return False
    else:
        return True


def process_single_question(question: str, ground_truth: str) -> List[Dict[str, str]]:

    chat_messages = process_prompt(question)
    
    max_turns = 10
    turns = 0

    while turns < max_turns:

        one_answer, reasoning_content, stop_reason = call_model(chat_messages)

        if stop_reason == "function_call":
            function_call_str = one_answer.split("<function_call>")[-1].split("</fun")[0].strip()
            combined_response = f"<think>\n{reasoning_content}\n</think>\n<function_call>\n{function_call_str}\n</function_call>\n"
            chat_messages.append({
                "role": "assistant",
                "content": combined_response
            })
            function_call_result = parse_and_execute_function_call(question, ground_truth, function_call_str)
            function_call_result_info = f"<function_result>\n{function_call_result}\n</function_result>"
            chat_messages.append({
                "role": "user",
                "content": function_call_result_info
            })


        elif stop_reason == "answer":
            # 已经得到了答案，输出答案
            final_resp = one_answer.split("<answer>")[-1].split("</a")[0].strip()
            combined_response = f"<think>\n{reasoning_content}\n</think>\n<answer>\n{final_resp}\n</answer>\n"
            chat_messages.append({
                "role": "assistant",
                "content": combined_response
            })
            logger.info(f"Model's final answer: {final_resp}")
            logger.info(f"Ground truth: {ground_truth}")
            return chat_messages
        
        else:
            raise ValueError(f"Invalid stop reason. Model's response: {one_answer}, reasoning_content: {reasoning_content}, stop_reason: {stop_reason}")

    raise ValueError(f"Max turns reached. Model's response: {one_answer}, reasoning_content: {reasoning_content}, stop_reason: {stop_reason}")



def print_chat_messages(chat_messages: List[Dict[str, str]]):
    for message in chat_messages:
        print(f"{message['role']}: \n{message['content']}\n")
        print("\n\n")


def process_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:

    correct_save_path = "/apdcephfs/private_ralphzhou/workspace/ZeroSearch/post_training/result/r1_correct.jsonl"
    incorrect_save_path = "/apdcephfs/private_ralphzhou/workspace/ZeroSearch/post_training/result/r1_incorrect.jsonl"

    question = data['question']
    ground_truth = data['golden_answers']
    with Timer(f"Processing question: {question}"):
        chat_messages = process_single_question(question, ground_truth)
        # print_chat_messages(chat_messages)
        final_answer = chat_messages[-1]['content'].split("<answer>")[-1].split("</answer>")[0].strip()
        correctness = judge_answer(question, final_answer, ground_truth)
        logger.info(f"Correctness: {correctness}")
        data['messages'] = chat_messages
        data['correctness'] = correctness

        with file_lock:
            with open(correct_save_path if correctness else incorrect_save_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")


def process_data_concurrently(data_path: str, max_workers: int = 10) -> List[Dict[str, Any]]:

    correct_save_path = "/apdcephfs/private_ralphzhou/workspace/ZeroSearch/post_training/result/r1_correct.jsonl"
    incorrect_save_path = "/apdcephfs/private_ralphzhou/workspace/ZeroSearch/post_training/result/r1_incorrect.jsonl"

    processed_data_id_set = get_processed_data_ids(correct_save_path)
    processed_data_id_set.update(get_processed_data_ids(incorrect_save_path))

    data_list = load_json_data(data_path)

    logger.info(f"Total data: {len(data_list)}")
    logger.info(f"Processed data: {len(processed_data_id_set)}, unprocessed data: {len(data_list) - len(processed_data_id_set)}")

    unprocessed_data_list = [data for data in data_list if get_data_id(data) not in processed_data_id_set]

    with tqdm(total=len(unprocessed_data_list)) as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_data, data) for data in unprocessed_data_list]
            for future in futures:
                pbar.update(1)
                future.result()


if __name__ == "__main__":
    # question = "How many studio albums published by Merceds Sosa from 2000 to 2009 according to latest Wikipedia?"

    # if_success, one_answer = call_model(process_question(question))

    data_path = "/apdcephfs/private_ralphzhou/workspace/ZeroSearch/post_training/result/all_incorrect_data.jsonl"
    # save_path = "/apdcephfs/private_ralphzhou/workspace/ZeroSearch/post_training/result/all_incorrect_data_processed_raw.jsonl"
    process_data_concurrently(data_path, max_workers=50)
