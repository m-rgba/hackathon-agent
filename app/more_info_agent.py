from openai import OpenAI
from typing import Generator
from logger import logger

def get_more_info(
    api_endpoint: str,
    api_key: str,
    api_model: str,
    thread_messages: list = None
) -> Generator[str, None, None]:
    try:
        client = OpenAI(base_url=api_endpoint, api_key=api_key)
        
        system_prompt = """
You are a helpful AI assistant tasked with gathering more specific information from users.
When responding, follow these guidelines:

1. Be specific about what information you need
2. Provide clear options or examples when applicable
3. Explain why you need this information
4. Use a friendly, professional tone

Structure your response in this format:
1. Brief acknowledgment of the request
2. Clear statement of what additional information is needed
3. List of specific questions or options (if applicable)
4. Brief explanation of how this information will help

Example formats:

For design reviews:
"I'd be happy to review the design. Could you please:
- Share the Figma URL for the design you'd like reviewed
- Specify if you want to focus on any particular aspects (e.g., usability, accessibility, visual hierarchy)
- Mention if this is a final design or work in progress"

For GitHub-related requests:
"I can help with your GitHub request. Please clarify:
- Which repository you're working with
- The specific branch or PR you're referring to
- What type of information you need (e.g., PR status, code review, merge conflicts)"

For general development questions:
"To better assist you, I need to know:
- What programming language/framework you're using
- The specific problem or error you're encountering
- What you've already tried
- Your expected outcome"

Remember to maintain context from previous messages and only ask for information that hasn't already been provided.
""".strip()

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        if thread_messages:
            for msg in thread_messages:
                if not msg["message"].strip():
                    continue
                messages.append({
                    "role": msg["sender"].lower(),
                    "content": msg["message"]
                })

        stream = client.chat.completions.create(
            model=api_model,
            messages=messages,
            stream=True
        )

        buffer = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                # Add to buffer
                buffer += content
                
                # If we have a newline or sufficient content, process and yield
                if '\n' in buffer or len(buffer) > 80:
                    # Split by newlines to preserve them
                    parts = buffer.split('\n')
                    
                    # Process all parts except the last one
                    for part in parts[:-1]:
                        # Normalize spaces while preserving intentional newlines
                        normalized = ' '.join(part.split())
                        if normalized:
                            yield normalized + '\n'
                    
                    # Keep the last part in buffer
                    buffer = parts[-1]
        
        # Process any remaining content in buffer
        if buffer:
            normalized = ' '.join(buffer.split())
            if normalized:
                yield normalized

    except Exception as e:
        error_msg = f"Error in more_info agent: {str(e)}"
        logger.error(error_msg)
        yield error_msg 