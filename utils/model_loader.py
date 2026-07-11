import os
import requests
import socket
import urllib.parse
from requests.exceptions import RequestException
from dotenv import load_dotenv
from typing import Optional, Any
from pydantic import BaseModel, Field
from utils.config_loader import load_config
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
import logging


class HuggingFaceLLM:
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    def bind_tools(self, tools=None):
        return self

    def invoke(self, messages):
        prompt = self._build_prompt(messages)
        return self._call_huggingface(prompt)

    def _build_prompt(self, messages):
        if isinstance(messages, str):
            return messages
        if hasattr(messages, "content"):
            return getattr(messages, "content")
        if isinstance(messages, list):
            parts = []
            for item in messages:
                if hasattr(item, "content"):
                    parts.append(getattr(item, "content"))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(messages)

    def _call_huggingface(self, prompt: str):
        hf_base_url = os.getenv("HUGGINGFACE_API_URL", "https://api-inference.huggingface.co")
        parsed_url = urllib.parse.urlparse(hf_base_url)
        if not parsed_url.scheme:
            raise RuntimeError(
                f"Invalid HUGGINGFACE_API_URL: '{hf_base_url}'. It must include http:// or https://."
            )

        url = f"{hf_base_url.rstrip('/')}/models/{self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 512,
                "temperature": 0.7,
                "return_full_text": False,
            },
        }

