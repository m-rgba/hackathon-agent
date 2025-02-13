import requests
import re
import os
import urllib.request
from typing import Generator, Dict, List, Tuple
from logger import logger

def extract_figma_images(figma_token: str, figma_url: str) -> Generator[str, None, None]:
    """
    Extract images from Figma and return a generator that yields status updates and results.
    """
    try:
        # Initial status update
        yield "> Extracting images from Figma...\n\n"

        # --- Step 1: Extract File ID and Node ID from the URL ---
        file_id_match = re.search(r"design/([a-zA-Z0-9]+)", figma_url)
        node_id_match = re.search(r"node-id=([\w-]+)", figma_url)
        
        if not (file_id_match and node_id_match):
            raise ValueError("Could not extract the file ID or node ID from the URL.")

        file_id = file_id_match.group(1)
        node_id = node_id_match.group(1)
        api_node_id = node_id.replace("-", ":", 1)
        
        yield "> Successfully extracted file and node IDs\n\n"

        # --- Step 2: Fetch the Figma file JSON ---
        headers = {"X-Figma-Token": figma_token}
        figma_api_url = f"https://api.figma.com/v1/files/{file_id}"
        response = requests.get(figma_api_url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Error fetching Figma file: {response.text}")

        data = response.json()
        yield "> Successfully fetched Figma file data\n\n"

        # --- Helper functions ---
        def find_node(node: Dict, target_id: str) -> Dict:
            if node.get("id") == target_id:
                return node
            for child in node.get("children", []):
                result = find_node(child, target_id)
                if result:
                    return result
            return None

        def extract_top_level_frames(container_node: Dict) -> List[Dict]:
            return [child for child in container_node.get("children", []) 
                   if child.get("type") == "FRAME"]

        # --- Step 3: Find frames to export ---
        target_node = None
        for page in data["document"]["children"]:
            target_node = find_node(page, api_node_id)
            if target_node:
                break

        frames = []
        if target_node:
            if target_node.get("type") == "FRAME":
                frames = [target_node]
            else:
                frames = extract_top_level_frames(target_node)
                if not frames:
                    frames = extract_top_level_frames(data["document"]["children"][0])
        else:
            frames = extract_top_level_frames(data["document"]["children"][0])

        if not frames:
            raise Exception("No frames found to export.")

        yield f"> Found {len(frames)} frame(s) to export\n\n"

        # Create frame ID mapping
        frame_ids = [frame["id"] for frame in frames]
        frame_names = {frame["id"]: frame["name"] for frame in frames}

        # --- Step 4: Get image URLs ---
        ids_param = ",".join(frame_ids)
        images_api_url = f"https://api.figma.com/v1/images/{file_id}?ids={ids_param}&format=png"
        img_response = requests.get(images_api_url, headers=headers)
        
        if img_response.status_code != 200:
            raise Exception(f"Error fetching PNG URLs: {img_response.text}")
            
        images_data = img_response.json().get("images", {})
        yield "> Successfully retrieved image URLs\n\n"

        # --- Step 5: Generate markdown table ---
        markdown_table = "| Frame Name | Image URL |\n| --- | --- |\n"
        image_urls = []

        for fid in frame_ids:
            png_url = images_data.get(fid)
            if png_url:
                frame_name = frame_names[fid]
                markdown_table += f"| {frame_name} | {png_url} |\n"
                image_urls.append(png_url)

        yield markdown_table + "\n\n"
        yield "Your images have been successfully extracted! Would you like me to review the design now? I also have the ability to analyze the tone and copy of your designs."
        
        return image_urls

    except Exception as e:
        error_msg = f"Error during Figma image extraction: {str(e)}"
        logger.error(error_msg)
        yield f"Error: {error_msg}\n\n"
        return [] 