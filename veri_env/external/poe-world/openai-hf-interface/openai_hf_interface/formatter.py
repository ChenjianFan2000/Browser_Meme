from abc import ABC, abstractmethod
import base64
import tiktoken
import os


def encode_image(image_path, high_quality=False):
    if high_quality:
        image_path_1024 = image_path.replace(".jpg", "_1024.jpg")
        os.system(f"gm convert {image_path} -resize 1024x1024! {image_path_1024}")
        with open(image_path_1024, "rb") as image_file:
            data = image_file.read()
    else:
        with open(image_path, "rb") as image_file:
            data = image_file.read()
    data = base64.b64encode(data).decode('utf-8')
    return data


class PromptFormatter(ABC):
    @abstractmethod
    def format_prompt(self):
        pass

    @abstractmethod
    def format_output(self):
        pass

    @abstractmethod
    def prompt_to_string(self):
        pass


class DoNothingFormatter(PromptFormatter):
    def format_prompt(self, prompt):
        return prompt
    
    def format_output(self, output):
        return output
    
    def prompt_to_string(self, prompt):
        return prompt
    

class LLaMaChatFormatter(PromptFormatter):
    def __init__(self, instruction=None): 
        self.instruction = instruction

    def format_prompt(self, prompt):
        B_INST, E_INST = "[INST]", "[/INST]"
        B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"
        BOS, EOS = "<s>", "</s>"
        DEFAULT_SYSTEM_PROMPT = f"""You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe. Please ensure that your responses are socially unbiased and positive in nature. If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. If you don't know the answer to a question, please don't share false information."""

        if isinstance(prompt, str): 
            prompt = [prompt]

        if self.instruction is None:
            prompt = [DEFAULT_SYSTEM_PROMPT] + prompt
        prompt = [B_SYS + prompt[0] + E_SYS + prompt[1]] + prompt[2:]

        formatted = [
            f"{BOS}{B_INST} {(question).strip()} {E_INST} {(answer).strip()} {EOS}"
            for question, answer in zip(prompt[::2], prompt[1::2])
        ]
        formatted.append(f"{BOS}{B_INST} {(prompt[-1]).strip()} {E_INST}")

        return "".join(formatted)
    
    def format_output(self, output):
        return output
    
    def prompt_to_string(self, prompt):
        return prompt
    
    def tiklen_formatted_prompts(self, prompts):
        return sum([len(self.enc.encode(prompt)) for prompt in prompts])
    
    def tiklen_outputs(self, outputs):
        return sum([len(self.enc.encode(output)) for output in outputs])


class OpenAIChatFormatter(PromptFormatter):
    def __init__(self, instruction=None, high_quality_image=False): 
        self.instruction = instruction
        self.enc = tiktoken.get_encoding("cl100k_base")
        self.image_detail = {"detail": "high"} if high_quality_image else {}
        self.image_encoder = (lambda x: encode_image(x, True)) if high_quality_image else encode_image

    def format_prompt(self, prompt):
        if isinstance(prompt, str): 
            messages = [
                {"role": "user", "content": prompt},
            ]
        else:
            messages = []
            
            if isinstance(prompt, tuple):
                prompt = [prompt]

            for user_msg, assistant_msg in zip(prompt[::2], prompt[1::2]):
                if isinstance(user_msg, tuple):
                    content = []
                    content.append({"type": "text", "text": user_msg[0]})
                    for user_sub_msg in user_msg[1:]:
                        # Handle various format of image
                        if isinstance(user_sub_msg, dict):
                            content.append(user_sub_msg)
                        elif os.path.isfile(user_sub_msg):
                            data = self.image_encoder(user_sub_msg)
                            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}", **self.image_detail}})
                        elif isinstance(user_sub_msg, str):
                            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{user_sub_msg}", **self.image_detail}})
                        else:
                            raise NotImplementedError
                else:
                    content = user_msg
                messages.append({"role": "user", "content": content})
                messages.append({"role": "assistant", "content": assistant_msg})
                
            user_msg = prompt[-1]
            if isinstance(user_msg, tuple):
                content = []
                content.append({"type": "text", "text": user_msg[0]})
                for user_sub_msg in user_msg[1:]:
                    # Handle various format of image
                    if isinstance(user_sub_msg, dict):
                        content.append(user_sub_msg)
                    elif os.path.isfile(user_sub_msg):
                        data = self.image_encoder(user_sub_msg)
                        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}", **self.image_detail}})
                    elif isinstance(user_sub_msg, str):
                        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{user_sub_msg}", **self.image_detail}})
                    else:
                        raise NotImplementedError
            else:
                content = user_msg
            messages.append({"role": "user", "content": content})

        if self.instruction is not None:
            messages = [{"role": "system", "content": self.instruction}] + messages
        return messages

    def format_output(self, output):
        return output
    
    def prompt_to_string(self, messages):
        if not isinstance(messages, str):
            txt = ""
            if self.instruction is not None:
                txt += f"System: {messages[0]['content']}"
                messages = messages[1:]
            for idx, msg in enumerate(messages):
                if idx % 2:
                    txt += f"Assistant: {msg['content']}"
                else:
                    txt += f"User: {msg['content']}"
        return txt
    
    def tiklen_formatted_prompts(self, prompts):
        sm = 0
        for prompt in prompts:
            for msg in prompt:
                if isinstance(msg["content"], str):
                    sm += len(self.enc.encode(msg['content']))
                else:
                    for content in msg["content"]:
                        for k,v in content.items():
                            if k == "text":
                                sm += len(self.enc.encode(v))
                            elif k == "type":
                                continue 
                            elif k == "image_url":
                                if "detail" not in v or v["detail"] != "high":
                                    sm += 85
                                else:
                                    sm += 765
                            else:
                                assert False, f"unknown key {k}"
        return sm
    
    def tiklen_outputs(self, outputs):
        return sum([len(self.enc.encode(output)) if isinstance(output, str) else sum([len(self.enc.encode(sub_output)) for sub_output in output]) for output in outputs])