import logging
from openai import OpenAI
from typing import Generator
import weave

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@weave.op()
def tone_text_copy_review(
    image_url: str,
    api_endpoint: str,
    api_key: str,
    api_model: str,
    thread_messages: list = None,
) -> Generator[str, None, None]:
    logger.info("Starting tone and text copy review process...")
    
    try:
        client = OpenAI(base_url=api_endpoint, api_key=api_key)
        
        # Step 1: Extract text content from the image
        extraction_prompt = """
You are an expert at extracting text content from UI designs.

## Please list all text content from the image, categorized by:
- Headers
- Button text
- Call-to-action text
- Navigation items
- Form labels and placeholders

This extraction is for a SaaS application that manages LLM observability. Focus on capturing relevant UI text that reflects the actual functionality of the app.

Format the output as a structured list with categories.
Only include text that actually appears in the image.

## Exclusions:
- Do not include placeholder or dummy data used purely for presentation purposes.
- Exclude any sample content that does not represent real UI elements.

## Formatting:
- Please use basic markdown formatting.
- Use bullet points when appropriate.
- Do not nest bullet points.
""".strip()

        messages = [
            {"role": "system", "content": extraction_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Please extract all text content from this design:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                ],
            }
        ]

        # Get text extraction response
        extraction_response = client.chat.completions.create(
            model=api_model,
            messages=messages,
            stream=False
        )
        
        extracted_text = extraction_response.choices[0].message.content

        # Step 2: Review the extracted text for tone, grammar, and style
        review_prompt = """
You are an expert content strategist and copy editor.

## Task
Review the text content that will be provided below. This text has already been extracted from a UI design - you do not need to see the original image.

## Review the text content for:
1. Spelling and grammar issues.
2. Consistency in capitalization (ensure sentence case is used).
3. Tone of voice and brand consistency.
4. Clarity and conciseness.
5. Call-to-action effectiveness.
6. Accessibility and inclusivity.

## For each issue found:
- Clearly state the current text.
- Explain why it should be changed.
- Provide the recommended correction.

Be direct and specific. Skip general feedback and focus on actionable improvements.

## Example outputs:

"Send Now" 
- Issue: Please use sentence case.

"Delte" 
- Issue: Spelling issue

"This button'll disable project."
- Issue: Short form, please expand. Not specific, specify which project will be disabled.

## Formatting:
- Please use basic markdown formatting.
- Use bullet points when appropriate.
- Do not nest bullet points.
""".strip()

        messages = [
            {"role": "system", "content": review_prompt},
            {"role": "user", "content": f"Below is the extracted UI text content to review. Please provide specific feedback on any issues:\n\n{extracted_text}"}
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

        yield "📝 Extracted text content:\n\n"
        yield f"{extracted_text}\n\n"
        yield "🔍 Content review:\n\n"

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
        logger.error(f"Error in tone and text copy review: {e}")
        yield f"Error: {e}" 