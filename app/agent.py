from openai import OpenAI
import re
import weave
from datetime import datetime
from agent_design_review import design_review
from more_info_agent import get_more_info
from logger import logger

@weave.op()
def gen_thread_title(api_endpoint: str, api_key: str, api_model: str, message: str):
    """Generate a title for a thread based on the initial message."""
    client = OpenAI(base_url=api_endpoint, api_key=api_key)
    system_prompt = """
You are an AI that generates concise, descriptive titles based on the given question.
Your response must be in the format: <title>Generated title here</title>. "
Keep the title brief and relevant to the question.

Title examples:
Question: "What are the best practices for securing a FastAPI backend?"
<title>What Securing FastAPI best practices</title>

Question: "What are the key considerations when designing an LLM evaluation framework?"
<title>Designing an LLM eval framework</title>

Question: "How do I optimize OpenAI API costs for large-scale applications?"
<title>Optimizing OpenAI API costs</title>
""".strip()

    title_response = client.chat.completions.create(
        model=api_model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {"role": "user", "content": f"Question: {message}"},
        ]
    )
    
    completion_response = title_response.choices[0].message.content
    pattern = r'<title>(.*?)</title>'
    title = re.findall(pattern, completion_response)[0]
    return title


@weave.op()
def gen_router(client, api_model: str, thread_messages: list = None, figma_token: str = None, github_token: str = None):
    try:        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Starting router at {current_time}")
        
        # Add token status to system prompt
        figma_status = "enabled" if figma_token else "disabled"
        github_status = "enabled" if github_token else "disabled"
        logger.debug(f"Figma status: {figma_status}, GitHub status: {github_status}")
        
        system_prompt = f"""
Current time: {current_time}

Analyze the following conversation and respond using only the specified tags. 
Do not include any additional prose, explanations, or formatting beyond the tags listed. 

## Figma ({figma_status})
### Extract images from Figma
- You have the ability to extract images from Figma.
- Images can be from a single frame or multiple frames.
- Format: <extract_images_from_figma>[FIGMA_DESIGN_URL]</extract_images_from_figma>
- Example: <extract_images_from_figma>https://www.figma.com/design/GlOG8RNAhlJwrCKHXy7NHp/Wireframe---Filter-Selectors?node-id=2133-51202&t=lcZiEKYhylq0sbkM-4</extract_images_from_figma>

### Design review from images
- You have the ability to do design reviews on image links from Figma.
- Figma image links will be in a Figma-based S3 bucket, but will not contain an extension.
- You must have the images extracted first, if the user asks for a design review please run `extract_images_from_figma` first to gather the images for them.
- You can have multiple images in your response.
- Format: <review_design>[FIGMA_IMAGE_URL]</review_design> <review_design>[FIGMA_IMAGE_URL2]</review_design>
- Example: <review_design>https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/e66718fb-d99a-45ab-84dc-8b35babec01e</review_design>

## GitHub ({github_status})
### My active pull requests (PRs)
- You have the ability to view your active pull requests (PRs), a description of the PR, the status of the PR, and the size.
- Format: <my_active_prs/>

## Other
### More info needed
- You have the ability to follow up with the user if you need more information to execute a task.
- Format: <more_info_needed/>

### Pass
- You have the ability to continue talking without using any tools.
- Format: <continue_conversation/>

## Guidelines
- Only use the tags provided.
- Do not include any extra text, explanations, or formatting.
- If no action applies, return <continue_conversation/>.
- If a feature requires credentials that are disabled, return <more_info/>.
        """.strip()

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if thread_messages:
            logger.debug(f"Adding {len(thread_messages)} messages to context")
            for msg in thread_messages:
                if not msg["message"].strip():
                    continue
                messages.append({
                    "role": msg["sender"].lower(),
                    "content": msg["message"]
                })
                logger.debug(f"Added message from {msg['sender']}: {msg['message'][:100]}...")
        
        logger.info("Calling router completion...")
        response = client.chat.completions.create(
            model=api_model,
            messages=messages
        )
        routing_result = response.choices[0].message.content
        logger.info(f"Router response: {routing_result}")
        return routing_result
    except Exception as e:
        error = f"Routing error: {str(e)}"
        logger.error(error)
        return error

@weave.op()
def gen_streaming_response(api_endpoint: str, api_key: str, api_model: str, message: str, thread_messages: list = None, figma_token: str = None, github_token: str = None):
    try:
        client = OpenAI(base_url=api_endpoint, api_key=api_key)
        logger.info("Initialized OpenAI client")
        
        messages = []
        if thread_messages:
            logger.debug(f"Processing {len(thread_messages)} messages for context")
            for msg in thread_messages:
                if not msg["message"].strip():
                    continue
                messages.append({
                    "role": msg["sender"].lower(),
                    "content": msg["message"]
                })        

        ## -- Routing -- ##
        logger.info("Getting routing response")
        routing_response = gen_router(client, api_model, thread_messages, figma_token, github_token)
        handled = False
        
        # Handle more info needed
        if '<more_info_needed/>' in routing_response and not handled:
            handled = True
            logger.info("Processing more info needed request")
            try:
                for content in get_more_info(
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                    api_model=api_model,
                    thread_messages=thread_messages
                ):
                    yield content + "\n"
            except Exception as e:
                logger.error(f"Error processing more info request: {str(e)}")
                yield f"Error processing more info request: {str(e)}\n\n"

        # Handle design review
        frame_pattern = r'<review_design>(.*?)</review_design>'
        frame_urls = re.findall(frame_pattern, routing_response)
        if frame_urls and not handled:
            handled = True
            logger.info("Processing design review")
            yield "> Reviewing design...\n\n"
            url = frame_urls[0]
            try:
                for content in design_review(
                    image_url=url,
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                    api_model=api_model,
                    thread_messages=thread_messages
                ):
                    # Only add a newline if the content doesn't already end with one
                    if content:
                        yield content if content.endswith('\n') else content + ' '
            except Exception as e:
                logger.error(f"Error processing design review: {str(e)}")
                yield f"Error processing design review: {str(e)}\n\n"

        # Handle GitHub PRs
        pr_pattern = r'<my_active_prs/>'
        if re.search(pr_pattern, routing_response) and not handled:
            handled = True
            if not github_token:
                logger.warning("GitHub token not configured")
                yield "Error: GitHub token not configured in settings\n\n"
            else:
                logger.info("Processing GitHub PRs request")
                yield "> Fetching active PRs... \n\n"
                # TODO: Implement GitHub PR fetching logic
                yield "GitHub PR fetching not yet implemented\n\n"

        # Handle conversation or fallback
        if not handled:
            if '<continue_conversation/>' in routing_response or routing_response.strip() == '':
                logger.info("Processing conversation response")
                messages.append({"role": "user", "content": message})
                stream = client.chat.completions.create(
                    model=api_model,
                    messages=messages,
                    stream=True
                )
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        yield chunk.choices[0].delta.content
            else:
                logger.info("Yielding routing response as fallback")
                yield routing_response

    except Exception as e:
        logger.error(f"Error in streaming response: {str(e)}")
        yield f"\nError occurred: {str(e)}"