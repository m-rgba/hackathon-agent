import logging
from openai import OpenAI
from typing import Generator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def design_review(
    image_url: str,
    api_endpoint: str,
    api_key: str,
    api_model: str,
    thread_messages: list = None,
) -> Generator[str, None, None]:
    logger.info("Starting design review process...")
    
    try:
        client = OpenAI(base_url=api_endpoint, api_key=api_key)
        
        system_prompt = """
Instructions:
You are an expert UI/UX designer reviewing a design.
Provide specific, actionable feedback and suggestions for improvement.
Please skip prose, do not include good parts, try to pick apart things which could be improved.
Formatting:
- Please use basic markdown formatting.
- Avoid using bold, italics, or headers.
- Use bullet points when appropriate.
""".strip()

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add thread history if available
        if thread_messages:
            for msg in thread_messages:
                if not msg["message"].strip():
                    continue
                messages.append({
                    "role": msg["sender"].lower(),
                    "content": msg["message"]
                })

        # Add the final message with the image
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Please review this design and provide detailed feedback:"},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
            ],
        })

        stream = client.chat.completions.create(
            model=api_model,
            messages=messages,
            stream=True
        )

        buffer = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                buffer += chunk.choices[0].delta.content
                # Yield complete sentences when we find sentence-ending punctuation
                if any(buffer.endswith(p) for p in ['. ', '! ', '? ', '\n']):
                    yield buffer.strip()
                    buffer = ""
        
        # Yield any remaining content in the buffer
        if buffer:
            yield buffer.strip()
                
    except Exception as e:
        logger.error(f"Error in design review: {e}")
        yield f"Error: {e}" 