from openai import OpenAI
from django.db import models
from typing import Generator

class OpenAIAgent:
    def __init__(self, api_endpoint: str, api_key: str, api_model: str):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.api_model = api_model
        self.client = OpenAI(base_url=api_endpoint, api_key=api_key)

    def generate_streaming_response(self, message: str) -> Generator[str, None, None]:
        """
        Generate a streaming response from OpenAI API
        """
        try:
            # Create streaming completion
            stream = self.client.chat.completions.create(
                model=self.api_model,
                messages=[{"role": "user", "content": message}],
                stream=True
            )

            # Stream the response
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"\nError occurred: {str(e)}"
