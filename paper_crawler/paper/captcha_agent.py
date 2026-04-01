from .llm.llm import LLM

system_prompt = """
你是一个得力的验证码识别助手

请根据我给你的验证码图片，提取出验证码

返回JSON格式:
{
    "status": "success or failed",
    "value": "提取到的验证码",
}
"""

class CaptchaAgent:
    def __init__(self):
        self.agent = LLM(system_prompt=system_prompt)

    def run(self, prompt):
        return self.agent.run(prompt)