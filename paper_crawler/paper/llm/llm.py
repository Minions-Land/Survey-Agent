import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def _build_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise ValueError("?? .env ??? OPENAI_API_KEY")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    return OpenAI(**client_kwargs)


class LLM:
    def __init__(self, system_prompt, model="gpt-4.1-mini", temperature=0):
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.client = _build_openai_client()

    def run(self, prompt):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": str(prompt)}
                ],
                response_format={"type": "json_object"},
                temperature=self.temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"An error occurred: {str(e)}"
