from openai import OpenAI
import re
import weave
from datetime import datetime
from agent_review_frame import review_figma_frame
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
### Design review, single frame
- You have the ability to review a single frame from a Figma file.
- Format: <review_design_frame>[FIGMA_FRAME_URL]</review_design_frame>
- Example: <review_design_frame>https://www.figma.com/design/GlOG8RNAhlJwrCKHXy7NHp/Wireframe---Filter-Selectors?node-id=2133-51202&t=lcZiEKYhylq0sbkM-4</review_design_frame>

### Design review, page
- You have the ability to review a full page from a Figma file.
- Format: <review_designs_page>[FIGMA_PAGE_URL]</review_designs_page>
- Example: <review_designs_page>https://www.figma.com/design/GlOG8RNAhlJwrCKHXy7NHp/Wireframe---Filter-Selectors?node-id=2101-19789</review_designs_page>

## GitHub ({github_status})
### My active pull requests (PRs)
- You have the ability to view your active pull requests (PRs), a description of the PR, the status of the PR, and the size.
- Format: <my_active_prs/>

## Other
### Follow up
- You have the ability to follow up with the user if you need more information to execute a task.
- Format: <follow_up/>

### Pass
- You have the ability to continue talking without using any tools.
- Format: <continue_conversation/>

## Guidelines
- Only use the tags provided.
- Do not include any extra text, explanations, or formatting.
- If no action applies, return <continue_conversation/>.
- If a feature requires credentials that are disabled, return <follow_up/>.
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
        
        # Handle Figma frame review
        frame_pattern = r'<review_design_frame>(.*?)</review_design_frame>'
        frame_urls = re.findall(frame_pattern, routing_response)
        if frame_urls and not handled:
            handled = True
            if not figma_token:
                logger.warning("Figma token not configured")
                yield "Error: Figma API token not configured in settings\n\n"
            else:
                logger.info("Processing Figma frame review")
                yield "> Reviewing Figma frame... \n\n"
                url = frame_urls[0]
                try:
                    for content in review_figma_frame(
                        figma_url=url,
                        access_token=figma_token,
                        api_endpoint=api_endpoint,
                        api_key=api_key,
                        api_model=api_model,
                        thread_messages=thread_messages
                    ):
                        yield content + "\n"
                except Exception as e:
                    logger.error(f"Error processing Figma frame: {str(e)}")
                    yield f"Error processing Figma frame: {str(e)}\n\n"

        # Handle Figma page review
        page_pattern = r'<review_designs_page>(.*?)</review_designs_page>'        
        page_urls = re.findall(page_pattern, routing_response)
        if page_urls and not handled:
            handled = True
            if not figma_token:
                logger.warning("Figma token not configured")
                yield "Error: Figma API token not configured in settings\n\n"
            else:
                logger.info("Processing Figma page review")
                yield "> Reviewing Figma page for frames... \n\n"
                url = page_urls[0]
                yield f"Page review for URL: {url}\n\n"

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