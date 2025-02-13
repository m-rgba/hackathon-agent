from openai import OpenAI

def generate_streaming_response(api_endpoint: str, api_key: str, api_model: str, message: str, thread_messages: list = None):
    """Generate a streaming response from the OpenAI API."""
    try:
        client = OpenAI(base_url=api_endpoint, api_key=api_key)
        messages = []
        if thread_messages:
            for msg in thread_messages:
                # Skip empty messages
                if not msg["message"].strip():
                    continue
                messages.append({
                    "role": msg["sender"],
                    "content": msg["message"]
                })
        messages.append({"role": "user", "content": message})        
        stream = client.chat.completions.create(
            model=api_model,
            messages=messages,
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    except Exception as e:
        yield f"\nError occurred: {str(e)}"