from .llm.llm import LLM

system_prompt = """
你是一个得力的论文查找助手

请根据我给你的BibTex转换的Json和当前论文列表，在论文列表中找出和Bibtex相符的论文

# 规则
一旦找到相关论文，status键为True
value键为论文PDF链接
如果没有找到论文，或找到的论文没有PDF链接，status键为False
value键为空字符串

返回JSON格式:
{
    "status": True or False，
    "value": "提取到的信息",
}
"""

class FilterAgent:
    def __init__(self):
        self.agent = LLM(system_prompt=system_prompt)

    def run(self, bibtex, paper_list):
        return self.agent.run(f"Bibtex:\n{str(bibtex)}\n\n论文列表:\n{str(paper_list)}")