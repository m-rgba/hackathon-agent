import requests
import re
import os
import urllib.request
import logging
from typing import Dict, Optional, Tuple, Generator
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_ids_from_url(figma_url: str) -> Tuple[str, str]:
    """Extract File ID and Node ID from a Figma URL."""
    logger.info(f"Attempting to extract IDs from Figma URL: {figma_url}")
    
    file_id_match = re.search(r"design/([a-zA-Z0-9]+)", figma_url)
    node_id_match = re.search(r"node-id=([\w-]+)", figma_url)

    if not (file_id_match and node_id_match):
        error_msg = "Could not extract the file ID or node ID from the URL."
        logger.error(error_msg)
        raise ValueError(error_msg)

    file_id = file_id_match.group(1)
    node_id = node_id_match.group(1)
    logger.info(f"Successfully extracted - File ID: {file_id}, Node ID: {node_id}")
    return file_id, node_id

def find_node(node: Dict, target_id: str) -> Optional[Dict]:
    """Recursively search for a node with a given ID."""
    if node.get("id") == target_id:
        return node
    for child in node.get("children", []):
        result = find_node(child, target_id)
        if result:
            return result
    return None

def review_design(client: OpenAI, image_url: str, api_model: str, thread_messages: list = None):
    system_prompt = """
You are an expert UI/UX designer reviewing a Figma frame. Analyze the design for:
1. Visual hierarchy and layout
2. Color scheme and contrast
3. Typography and readability
4. Spacing and alignment
5. Consistency with design principles
6. Accessibility considerations
7. Interactive elements and affordances
8. Overall user experience

Provide specific, actionable feedback and suggestions for improvement.
Please skip prose, do not include good parts, try to pick apart things which could be improved.
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

    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content

def review_figma_frame(
    figma_url: str, 
    access_token: str, 
    api_endpoint: str,
    api_key: str,
    api_model: str,
    thread_messages: list = None,
) -> Generator[str, None, None]:
    logger.info("Starting Figma frame review process...")
    
    try:
        # Extract File ID and Node ID from URL
        file_id, node_id = extract_ids_from_url(figma_url)
        logger.info(f"Working with File ID: {file_id} and Node ID: {node_id}")
        yield "> Extracted Figma file and node IDs\n\n"
        
        # Convert Node ID to API format (replace first hyphen with colon)
        api_node_id = node_id.replace("-", ":", 1)
        logger.info(f"Converted Node ID to API format: {api_node_id}")
        
        # Set up headers for Figma API requests
        headers = {"X-Figma-Token": access_token}
        
        # Fetch the Figma file JSON
        figma_api_url = f"https://api.figma.com/v1/files/{file_id}"
        response = requests.get(figma_api_url, headers=headers)
        if response.status_code != 200:
            raise Exception("Error fetching Figma file:\n" + response.text)
        data = response.json()
        yield "> Retrieved Figma file data\n\n"
        
        # Find the target frame in the document
        target_node = None
        for page in data["document"]["children"]:
            target_node = find_node(page, api_node_id)
            if target_node:
                break
            
        if target_node is None:
            raise Exception(f"Node with ID {api_node_id} not found in the file.")
        
        yield f"> Found frame: {target_node.get('name')}\n\n"
        
        # Get PNG URL for the frame
        images_api_url = f"https://api.figma.com/v1/images/{file_id}?ids={api_node_id}&format=png"
        img_response = requests.get(images_api_url, headers=headers)
        if img_response.status_code != 200:
            raise Exception("Error fetching PNG URL:\n" + img_response.text)
        
        images_data = img_response.json().get("images", {})
        png_url = images_data.get(api_node_id)
        if not png_url:
            raise Exception("No PNG URL found for the node.")
        
        yield "> Retrieved frame image URL\n\n"
        
        # Initialize OpenAI client and perform design review
        client = OpenAI(base_url=api_endpoint, api_key=api_key)

        # Stream the design review
        for feedback in review_design(client, png_url, api_model, thread_messages):
            yield feedback 
    except Exception as e:
        logger.error(f"Error in review_figma_frame: {e}")
        yield f"Error: {e}" 