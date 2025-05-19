#!/usr/bin/env python3
"""
LightKeyia - Standalone Desktop Version (Optimized)
--------------------------------------
A tool to analyze images with Ollama and generate keywords in XMP files.
Compatible with standard and RAW formats.
"""

import os
import sys
import time
import json
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import requests
from PIL import Image
import base64
from datetime import datetime, timedelta
import logging
import re
import concurrent.futures
import tempfile
import platform
import argparse
import shutil


# Define the user prompt
user_prompt = "What do you see in detail?"

# Default system prompt - Optimized version from Ollama script
default_prompt = """You are an image analysis system. Your task is to analyze the provided photograph and extract keywords in different categories.

IMPORTANT: You MUST return ONLY a valid JSON object with the following structure, with NO additional text, NO markdown formatting, NO code blocks, and NO explanations:

{
"subjects": ["keyword1", "keyword2", ...],
"scene": ["A detailed description of the scene in at least one full sentence, providing context and significant details"],
"people": ["gender:male", "age:young", "expression:smiling", "action:walking", ...],
"nudity": ["nudity:no", ...],
"objects": ["specific object1", "specific object2", ...],
"lighting": ["keyword1", "keyword2", ...],
"colors": ["keyword1", "keyword2", ...],
"dominantColors": [
{"name": "color name", "hex": "#HEXCODE"},
{"name": "color name", "hex": "#HEXCODE"}
],
"composition": ["keyword1", "keyword2", ...],
"mood": ["keyword1", "keyword2", ...],
"technical": ["keyword1", "keyword2", ...]
}

DO NOT include any explanatory text, headers, or markdown formatting. ONLY return the JSON object.
IMPORTANT: The "scene" field MUST contain at least one element - a detailed description of the scene in complete sentence form.
"""

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("lightkeyia.log", mode="a")]
)
logger = logging.getLogger("LightKeyia")

# Constants
VERSION = "1.3.0"
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.heif',
                   '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.raf', '.orf', '.rw2',
                   '.pef', '.dng', '.raw', '.rwl', '.iiq', '.3fr', '.x3f')
RAW_EXTENSIONS = ('.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.raf', '.orf', '.rw2',
                 '.pef', '.dng', '.raw', '.rwl', '.iiq', '.3fr', '.x3f')
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".lightkeyia_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Check for rawpy
try:
    import rawpy
    RAWPY_AVAILABLE = True
    logger.info("rawpy is available for RAW file processing")
except ImportError:
    RAWPY_AVAILABLE = False
    logger.warning("rawpy is not available. RAW processing will be limited.")

# Check for exiftool
try:
    import subprocess
    result = subprocess.run(["exiftool", "-ver"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    EXIFTOOL_AVAILABLE = result.returncode == 0
    if EXIFTOOL_AVAILABLE:
        logger.info(f"ExifTool found: version {result.stdout.strip()}")
    else:
        logger.warning("ExifTool is not available. Metadata writing will be limited.")
except Exception:
    EXIFTOOL_AVAILABLE = False
    logger.warning("ExifTool is not available. Metadata writing will be limited.")

def _get_cache_key(image_path):
    """Generate a cache key for an image path"""
    return base64.b64encode(image_path.encode()).decode('utf-8')

def _is_in_cache(image_path, force_processing=False):
    """Check if an image is in the cache"""
    if force_processing:
        return False
    
    cache_key = _get_cache_key(image_path)
    cache_file = os.path.join(CACHE_DIR, cache_key)
    
    # Check if cache file exists and log the result
    is_cached = os.path.exists(cache_file)
    if is_cached:
        logger.info(f"Cache hit for {image_path}")
    
    return is_cached

def _add_to_cache(image_path):
    """Add an image to the cache"""
    cache_key = _get_cache_key(image_path)
    cache_file = os.path.join(CACHE_DIR, cache_key)
    with open(cache_file, 'w') as f:
        f.write(datetime.now().isoformat())

def clear_cache():
    """Clear the cache"""
    try:
        for file in os.listdir(CACHE_DIR):
            file_path = os.path.join(CACHE_DIR, file)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        logger.info("Cache cleared successfully")
        return True
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return False

def has_keywords_in_xmp(xmp_path):
    """Check if XMP file has keywords"""
    try:
        if not os.path.exists(xmp_path):
            return False
        
        with open(xmp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for keywords
        if '<dc:subject>' in content and '<rdf:li>' in content:
            return True
        
        # Check for Lightroom hierarchical keywords
        if '<lr:hierarchicalSubject>' in content and '<rdf:li>' in content:
            return True
        
        return False
    except Exception as e:
        logger.warning(f"Error checking keywords in {xmp_path}: {str(e)}")
        return False

def clean_and_repair_json(json_str):
    """Clean and attempt to repair a potentially malformed JSON"""
    try:
        # Log the raw JSON string for debugging
        logger.info(f"Raw JSON before cleaning: {json_str[:200]}...")
        
        # Find JSON in the string
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx+1]
            json_str = re.sub(r'\s+', ' ', json_str)
            
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error: {str(e)}")
                
                # Basic repair attempts
                # 1. Replace missing commas between braces
                json_str = re.sub(r'}\s*{', '},{', json_str)
                
                # 2. Add missing commas after strings
                json_str = re.sub(r'"\s*"', '","', json_str)
                
                # 3. Fix trailing commas in lists
                json_str = re.sub(r',\s*]', ']', json_str)
                
                # 4. Fix trailing commas in objects
                json_str = re.sub(r',\s*}', '}', json_str)
                
                # 5. Add missing commas between elements (common issue)
                json_str = re.sub(r'(:\s*"[^"]*")\s*(")', r'\1,\2', json_str)
                json_str = re.sub(r'(:\s*\d+)\s*(")', r'\1,\2', json_str)
                json_str = re.sub(r'(:\s*true|false)\s*(")', r'\1,\2', json_str)
                json_str = re.sub(r'(:\s*\[[^\]]*\])\s*(")', r'\1,\2', json_str)
                
                # 6. Fix unescaped quotes in strings
                json_str = re.sub(r'(?<=[^\\])"(?=[^,\{\}\[\]:])', r'\"', json_str)
                
                # 7. Fix boolean and null values
                json_str = re.sub(r':\s*True', r': true', json_str)
                json_str = re.sub(r':\s*False', r': false', json_str)
                json_str = re.sub(r':\s*None', r': null', json_str)
                
                # 8. Fix malformed arrays
                json_str = re.sub(r'(\[[^\],]*)"([^"\],]*)"([^\],]*)"', r'\1"\2","\3"', json_str)
                
                # Try again
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e2:
                    logger.warning(f"JSON repair failed: {str(e2)}")
                    
                    # More aggressive repair attempt
                    try:
                        # Extract key values using regex
                        subjects = re.findall(r'"subjects"\s*:\s*\[(.*?)\]', json_str)
                        objects = re.findall(r'"objects"\s*:\s*\[(.*?)\]', json_str)
                        scene = re.findall(r'"scene"\s*:\s*\[(.*?)\]', json_str)
                        
                        result = {"subjects": [], "objects": [], "scene": ["Description not available"]}
                        
                        # Process subjects
                        if subjects:
                            items = re.findall(r'"([^"]*)"', subjects[0])
                            result["subjects"] = items
                        
                        # Process objects
                        if objects:
                            items = re.findall(r'"([^"]*)"', objects[0])
                            result["objects"] = items
                        
                        # Process scene
                        if scene:
                            items = re.findall(r'"([^"]*)"', scene[0])
                            if items:
                                result["scene"] = items
                        
                        return result
                    except Exception as e3:
                        logger.warning(f"Manual extraction failed: {str(e3)}")
                        # If still invalid, create minimal JSON
                        logger.warning("Creating minimal JSON with available data")
                        return {"subjects": [], "objects": [], "scene": ["Description not available"]}
        
        # If no valid JSON found, create minimal JSON
        return {"subjects": [], "objects": [], "scene": ["Description not available"]}
    except Exception as e:
        logger.error(f"Error cleaning JSON: {str(e)}")
        return {"subjects": [], "objects": [], "scene": ["Description not available"]}

def extract_keywords_from_json(json_data):
    """Extract keywords from JSON data generated by the model"""
    try:
        # Log the raw JSON data for debugging
        if isinstance(json_data, str):
            logger.info(f"Raw JSON data before extraction: {json_data[:200]}...")
        else:
            logger.info(f"Raw JSON data before extraction: {str(json_data)[:200]}...")
        
        # Clean and repair JSON if it's a string
        if isinstance(json_data, str):
            data = clean_and_repair_json(json_data)
        else:
            data = json_data
        
        # Extract keywords from different categories
        keywords = []
        scene_description = None
        
        # Categories to process
        categories = [
            'subjects', 'objects', 'lighting', 'colors', 'composition', 
            'mood', 'technical', 'people', 'nudity'
        ]
        
        # Process each category
        for category in categories:
            if category in data and isinstance(data[category], list):
                for item in data[category]:
                    if isinstance(item, str):
                        keywords.append(item)
                    elif isinstance(item, dict):
                        for key, value in item.items():
                            if isinstance(value, str):
                                keywords.append(f"{key}:{value}")
        
        # Scene (add as description)
        if 'scene' in data:
            if isinstance(data['scene'], list) and data['scene']:
                scene_description = data['scene'][0]
            elif isinstance(data['scene'], str):
                scene_description = data['scene']
        
        # Clean keywords and remove duplicates
        cleaned_keywords = []
        for kw in keywords:
            if isinstance(kw, str):
                kw = kw.strip()
                if kw:
                    # Remove any "1" prefix that might have been added incorrectly
                    if kw.startswith("1") and len(kw) > 1 and not kw[1].isdigit():
                        kw = kw[1:]
                    cleaned_keywords.append(kw)
        
        # Log the extracted keywords for debugging
        logger.info(f"Extracted keywords: {cleaned_keywords[:10]}...")
        logger.info(f"Extracted {len(cleaned_keywords)} unique keywords and scene description: {scene_description[:50] if scene_description else 'None'}...")
        
        return list(set(cleaned_keywords)), scene_description
    except Exception as e:
        logger.error(f"Error extracting keywords from JSON: {str(e)}")
        return [], None

def convert_raw_to_jpeg(image_path, max_size=512):
    """Convert RAW file to JPEG for processing"""
    try:
        if not RAWPY_AVAILABLE:
            logger.warning("rawpy not available, cannot convert RAW file")
            return None, None
        
        # Create temporary directory if needed
        temp_dir = tempfile.mkdtemp()
        
        # Process RAW file
        with rawpy.imread(image_path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, half_size=True, no_auto_bright=False, output_bps=8)
            img = Image.fromarray(rgb)
            
            # Resize if necessary
            width, height = img.size
            if max(width, height) > max_size:
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                img = img.resize((new_width, new_height), Image.LANCZOS)
            
            # Save to temporary file
            temp_image_path = os.path.join(temp_dir, f"temp_raw_{os.path.basename(image_path)}.jpg")
            img.save(temp_image_path, "JPEG", quality=85)
            
            logger.info(f"RAW file converted to JPEG: {temp_image_path}")
            return temp_image_path, temp_dir
    except Exception as e:
        logger.error(f"Error converting RAW file: {str(e)}")
        return None, None

def save_jpg_metadata_with_exiftool(jpg_path, keywords, scene_description=None):
    """Save metadata to JPG file using ExifTool"""
    try:
        # Prepare ExifTool commands
        commands = []
        
        # Add IPTC keywords
        if keywords:
            # Convert keyword list to string for ExifTool
            keywords_str = ','.join(f'"{kw}"' for kw in keywords)
            commands.append(f'-IPTC:Keywords={keywords_str}')
            commands.append(f'-XMP:Subject={keywords_str}')
        
        # Add description if available
        if scene_description:
            commands.append(f'-IPTC:Caption-Abstract="{scene_description}"')
            commands.append(f'-XMP:Description="{scene_description}"')
        
        if commands:
            # Execute ExifTool
            cmd = ["exiftool", "-overwrite_original"]
            cmd.extend(commands)
            cmd.append(jpg_path)
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                logger.error(f"ExifTool error: {result.stderr}")
                return False
            
            logger.info(f"Metadata written to JPG file with ExifTool")
            return True
        return False
    except Exception as e:
        logger.error(f"Error writing metadata with ExifTool: {str(e)}")
        return False

def save_jpg_metadata_with_pillow(jpg_path, keywords, scene_description=None):
    """Save metadata to JPG file using Pillow (limited capabilities)"""
    try:
        # Open image with Pillow
        img = Image.open(jpg_path)
        
        # Pillow has limited capabilities for writing metadata
        # Save the image with new metadata
        img.save(jpg_path, format="JPEG", quality=85)
        
        logger.info(f"Metadata written to JPG file with Pillow (limited)")
        return True
    except Exception as e:
        logger.error(f"Error writing metadata with Pillow: {str(e)}")
        return False

class OllamaClient:
    """Client for interacting with the Ollama API"""
    
    def __init__(self, ollama_url="http://127.0.0.1:11434"):
        self.ollama_url = ollama_url
        self.request_lock = threading.Lock()
    
    def is_ollama_running(self):
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
            return response.status_code == 200
        except requests.ConnectionError:
            return False
        except Exception as e:
            logger.error(f"Error checking Ollama: {str(e)}")
            return False
    
    def list_models(self):
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
            if response.status_code == 200:
                return response.json().get("models", [])
            else:
                logger.error(f"Error retrieving models: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error retrieving models: {str(e)}")
            return []
    
    def generate(self, model_name, prompt, temperature=0.0):
        """Generate text from Ollama"""
        data = {
            "prompt": prompt,
            "model": model_name,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature
            }
        }
        try:
            response = requests.post(f"{self.ollama_url}/api/generate", json=data, stream=False)
            response.raise_for_status()
            
            # Collect the complete response
            full_response = ""
            for line in response.iter_lines():
                if line:
                    try:
                        json_line = json.loads(line.decode('utf-8'))
                        full_response += json_line.get("response", "")
                    except json.JSONDecodeError:
                        logger.warning(f"Erreur de décodage JSON: {line}")
                        continue
        
        return full_response.strip()
    except requests.RequestException as e:
        logger.error(f"Erreur lors de la requête à Ollama: {e}")
        return None
    
    def generate_with_image(self, model_name, image_path, system_prompt, user_prompt="What do you see in detail?", temperature=0.9, max_retries=3, skip_chat_api=False):
        """Generate text from Ollama with an image"""
        try:
            # Check if file is a RAW format
            is_raw = image_path.lower().endswith(RAW_EXTENSIONS)
            
            # Process image and get base64 data
            if is_raw:
                image_data = self._process_raw_image(image_path)
                skip_chat_api = True  # Always use generate API for RAW files
            else:
                image_data = self._process_standard_image(image_path)
            
            if not image_data:
                return None
            
            # First try with the chat API with retries
            if not skip_chat_api:
                for retry in range(max_retries):
                    try:
                        # Prepare request for chat API
                        payload = {
                            "model": model_name,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": system_prompt
                                },
                                {
                                    "role": "user",
                                    "content": user_prompt,
                                    "images": [image_data]
                                }
                            ],
                            "temperature": temperature,
                            "stream": False
                        }
                    
                    logger.info(f"Envoi de la requête à l'API chat avec le modèle {model_name} (tentative {retry+1}/{max_retries})")
                    
                    # Use lock to avoid overloading the API
                    with self.request_lock:
                        response = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=180)
                    
                    if response.status_code == 200:
                        result = response.json()
                        raw_response = result.get('message', {}).get('content', '')
                        
                        # Log the raw response
                        logger.info(f"Raw response from model: {raw_response[:200]}...")
                        
                        return self._clean_response(raw_response)
                    else:
                        logger.warning(f"L'API chat a échoué avec le code {response.status_code}, réponse: {response.text[:200]}")
                        time.sleep(2)  # Wait before retrying
                except requests.RequestException as e:
                    logger.warning(f"Erreur avec l'API chat: {str(e)}, nouvelle tentative...")
                    time.sleep(2)  # Wait before retrying
            
            logger.warning(f"Toutes les tentatives avec l'API chat ont échoué, passage à l'API generate")
        
        # Fallback to generate API
        payload = {
            "model": model_name,
            "prompt": f"Analyze this image and extract keywords as specified in the instructions.\n\n[IMAGE]",
            "system": system_prompt,
            "images": [image_data],
            "temperature": temperature,
            "stream": False
        }
    
        logger.info(f"Envoi de la requête à l'API generate avec le modèle {model_name}")
        
        for retry in range(max_retries):
            try:
                with self.request_lock:
                    response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=180)
                
                if response.status_code == 200:
                    result = response.json()
                    response_text = result.get('response', '')
                    # Log the raw response
                    logger.info(f"Raw model response: {response_text[:200]}...")
                    return self._clean_response(response_text)
                else:
                    logger.error(f"Erreur lors de la génération: Code {response.status_code}, Message: {response.text[:200]}")
                    time.sleep(2)
            except requests.RequestException as e:
                logger.error(f"Erreur lors de la génération avec image: {str(e)}")
                time.sleep(2)
        
        logger.error("Toutes les tentatives ont échoué")
        return None
    except Exception as e:
        logger.error(f"Erreur inattendue lors de la génération avec image: {str(e)}")
        return None
    
    def _process_raw_image(self, self):
        """Process RAW image and return base64 data"""
        try:
            if RAWPY_AVAILABLE:
                try:
                    logger.info(f"Processing RAW file with rawpy: {image_path}")
                    with rawpy.imread(image_path) as raw:
                        rgb = raw.postprocess(use_camera_wb=True, half_size=True, no_auto_bright=False, output_bps=8)
                        img = Image.fromarray(rgb)
                        
                        # Resize if necessary
                        max_size = 512
                        width, height = img.size
                        if max(width, height) > max_size:
                            if width > height:
                                new_width = max_size
                                new_height = int(height * (max_size / width))
                            else:
                                new_height = max_size
                                new_width = int(width * (max_size / height))
                            img = img.resize((new_width, new_height), Image.LANCZOS)
                        
                        # Save to temporary file
                        temp_image_path = os.path.join(tempfile.gettempdir(), f"temp_raw_{os.path.basename(image_path)}.jpg")
                        img.save(temp_image_path, "JPEG", quality=85)
                        
                        # Read optimized image
                        with open(temp_image_path, "rb") as image_file:
                            image_data = base64.b64encode(image_file.read()).decode('utf-8')
                        
                        # Clean up temporary file
                        try:
                            os.remove(temp_image_path)
                        except:
                            pass
                        
                        return image_data
                except Exception as e:
                    logger.warning(f"Error processing RAW with rawpy: {str(e)}, reading directly")
            
            # Fallback: read RAW file directly
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error reading RAW file: {str(e)}")
            return None
    
    def _process_standard_image(self, self):
        """Process standard image and return base64 data"""
        temp_image_path = None
        try:
            with Image.open(image_path) as img:
                max_size = 512
                width, height = img.size
                if max(width, height) > max_size:
                    if width > height:
                        new_width = max_size
                        new_height = int(height * (max_size / width))
                    else:
                        new_height = max_size
                        new_width = int(width * (max_size / height))
                    img = img.resize((new_width, new_height), Image.LANCZOS)
                    
                    # Convert to RGB if needed
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Save to temporary file with reduced quality
                    temp_image_path = os.path.join(tempfile.gettempdir(), f"temp_send_{os.path.basename(image_path)}")
                    img.save(temp_image_path, "JPEG", quality=85)
                    image_path = temp_image_path
            
            # Read the image file
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Clean up temporary file if created
            if temp_image_path and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                except:
                    pass
            
            return image_data
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return None
    
    def _clean_response(self, response_text):
        """Clean the response to extract JSON"""
        response_text = response_text.strip()
        
        # Check for code blocks - fixed escape sequences
        if "\`\`\`json" in response_text:
            # Extract content between \`\`\`json and \`\`\`
            start = response_text.find("\`\`\`json") + 7
            end = response_text.find("\`\`\`", start)
            if end != -1:
                return response_text[start:end].strip()
        elif "\`\`\`" in response_text:
            # Extract content between \`\`\` and \`\`\`
            start = response_text.find("\`\`\`") + 3
            end = response_text.find("\`\`\`", start)
            if end != -1:
                return response_text[start:end].strip()
        
        # If we have a response with markdown bullet points, try to convert to JSON
        if "**Keywords:**" in response_text or "*   **" in response_text:
            logger.info("Detected markdown response, attempting to convert to JSON")
            try:
                # Create a basic JSON structure
                result = {
                    "subjects": [],
                    "objects": [],
                    "scene": ["Description extracted from markdown response"],
                    "people": [],
                    "lighting": [],
                    "colors": [],
                    "mood": [],
                    "technical": []
                }
                
                # Extract bullet points
                lines = response_text.split('\n')
                current_category = "subjects"  # Default category
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Check for category headers
                    if "person" in line.lower() or "people" in line.lower():
                        current_category = "people"
                    elif "object" in line.lower():
                        current_category = "objects"
                    elif "light" in line.lower():
                        current_category = "lighting"
                    elif "color" in line.lower():
                        current_category = "colors"
                    elif "mood" in line.lower():
                        current_category = "mood"
                    elif "technical" in line.lower():
                        current_category = "technical"
                    elif "scene" in line.lower() or "description" in line.lower():
                        current_category = "scene"
                    
                    # Extract keywords from bullet points
                    if line.startswith("*") or line.startswith("-"):
                        # Clean up the bullet point
                        keyword = line.lstrip("*- ")
                        # Remove bold markdown if present
                        keyword = keyword.replace("**", "")
                        # Remove any trailing colons
                        if ":" in keyword:
                            parts = keyword.split(":", 1)
                            if len(parts) == 2 and parts[1].strip():
                                # If there's content after the colon, keep both parts
                                keyword = f"{parts[0].strip()}:{parts[1].strip()}"
                            else:
                                # Otherwise just keep the part before the colon
                                keyword = parts[0].strip()
                        
                        if keyword:
                            result[current_category].append(keyword)
                
                return json.dumps(result)
            except Exception as e:
                logger.error(f"Error converting markdown to JSON: {str(e)}")
        
        # If no JSON found, return the original text
        return response_text

class ImageProcessor:
    """Image processor for analysis with Ollama and XMP keyword generation"""
    
    def __init__(self, model="gemma3:4b", ollama_url=None, max_size=512, temperature=0.5, threads=4, 
                 validate_xmp=True, preserve_xmp=True, write_jpg_metadata=True, force_processing=False,
                 batch_size=5, pause_between_batches=5, skip_chat_api=False, system_prompt=None):
        
        self.model = model
        self.ollama_url = ollama_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
        self.max_size = max_size
        self.temperature = temperature
        self.threads = threads
        self.validate_xmp = validate_xmp
        self.preserve_xmp = preserve_xmp
        self.write_jpg_metadata = write_jpg_metadata
        self.force_processing = force_processing
        self.batch_size = batch_size
        self.pause_between_batches = pause_between_batches
        self.skip_chat_api = skip_chat_api
        self.user_prompt = user_prompt
        self.max_retries = 3
        
        self.system_prompt = system_prompt if system_prompt else default_prompt
        
        # Processing state
        self.is_processing = False
        self.should_stop = False
        self.progress = 0
        self.total_images = 0
        self.processed_images = 0
        self.skipped_images = 0
        self.failed_images = 0
        self.logs = []
        self.start_time = None
        self.processing_images = set()  # Set to track images being processed
        self.last_log_message = None   # To avoid repetitive logs
        self.last_log_time = None      # To limit log frequency
        
        # Initialize Ollama client
        self.ollama_client = OllamaClient(self.ollama_url)
        self._check_ollama_connection()

    def _check_ollama_connection(self):
        try:
            if self.ollama_client.is_ollama_running():
                logger.info(f"Connection to Ollama established: {self.ollama_url}")
                return True
            else:
                logger.error(f"Error connecting to Ollama: URL={self.ollama_url}")
                return False
        except Exception as e:
            logger.error(f"Exception connecting to Ollama: {str(e)}")
            return False

    def add_log(self, message):
        # Avoid repetitive logs in a short interval
        current_time = datetime.now()
        
        # If it's the same message as the previous one and less than 2 seconds have passed
        if (self.last_log_message == message and 
            self.last_log_time and 
            (current_time - self.last_log_time).total_seconds() < 2):
            # Don't add the log
            return
        
        timestamp = current_time.strftime("%H:%M:%S" if current_time.microsecond == 0 else "%H:%M:%S.%f")
        log_entry = f"{timestamp} - {message}"
        self.logs.append(log_entry)
        logger.info(message)
        
        # Update last message and time
        self.last_log_message = message
        self.last_log_time = current_time

    def clear_cache(self):
        return clear_cache()

    def extract_image_metadata(self, image_path):
        """Extract basic metadata from image file"""
        try:
            metadata = {}
            
            # Check if it's a RAW file
            ext = os.path.splitext(image_path)[1].lower()
            if ext in RAW_EXTENSIONS:
                # For RAW files, return minimal metadata
                metadata['format'] = ext[1:].upper()  # Format based on extension
                metadata['is_raw'] = True
                metadata['exif'] = {}  # Empty EXIF data for RAW files
                logger.info(f"RAW file detected: {image_path}, minimal metadata created")
            else:
                # For standard formats, try to use PIL
                try:
                    with Image.open(image_path) as img:
                        # Extract basic image info
                        metadata['format'] = img.format
                        metadata['mode'] = img.mode
                        metadata['size'] = img.size
                        
                        # Extract EXIF data if available
                        exif_data = {}
                        if hasattr(img, '_getexif') and img._getexif():
                            exif = img._getexif()
                            if exif:
                                # EXIF tags mapping
                                from PIL.ExifTags import TAGS
                                for tag_id, value in exif.items():
                                    tag = TAGS.get(tag_id, tag_id)
                                    exif_data[tag] = value
                        
                        metadata['exif'] = exif_data
                except Exception as e:
                    logger.warning(f"Could not open image with PIL: {str(e)}")
                    # Create minimal metadata
                    metadata['format'] = ext[1:].upper()
                    metadata['exif'] = {}
            
            # Check for existing XMP file
            xmp_path = os.path.splitext(image_path)[0] + '.xmp'
            if os.path.exists(xmp_path):
                try:
                    with open(xmp_path, 'r', encoding='utf-8') as f:
                        metadata['xmp'] = f.read()
                    logger.info(f"Existing XMP file found: {xmp_path}")
                except Exception as e:
                    logger.warning(f"Could not read existing XMP file: {str(e)}")
            
            return metadata
        except Exception as e:
            logger.error(f"Error extracting metadata from image {image_path}: {str(e)}")
            return {'format': os.path.splitext(image_path)[1][1:].upper(), 'exif': {}}

    def _resize_image_if_needed(self, image_path):
        """Resize image if needed for processing"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                if max(width, height) <= self.max_size:
                    return image_path  # No resize needed
                
                # Resize needed
                if width > height:
                    new_width = self.max_size
                    new_height = int(height * (self.max_size / width))
                else:
                    new_height = self.max_size
                    new_width = int(width * (self.max_size / height))
                
                # Create resized image
                resized_img = img.resize((new_width, new_height), Image.LANCZOS)
                
                # Convert to RGB if needed
                if resized_img.mode != 'RGB':
                    resized_img = resized_img.convert('RGB')
                
                # Save to temporary file
                temp_image_path = os.path.join(tempfile.gettempdir(), f"temp_resize_{os.path.basename(image_path)}")
                resized_img.save(temp_image_path, "JPEG", quality=85)
                
                logger.info(f"Image resized: {image_path} -> {temp_image_path}")
                return temp_image_path
        except Exception as e:
            logger.error(f"Error resizing image: {str(e)}")
            return image_path  # Return original path on error

    def _cleanup_temp_files(self, temp_files):
        """Clean up temporary files and directories"""
        for file_type, path in temp_files:
            try:
                if file_type == "file" and os.path.exists(path):
                    os.remove(path)
                    logger.debug(f"Temporary file removed: {path}")
                elif file_type == "dir" and os.path.exists(path):
                    shutil.rmtree(path)
                    logger.debug(f"Temporary directory removed: {path}")
            except Exception as e:
                logger.warning(f"Error cleaning up temporary {file_type}: {path} - {str(e)}")

    def process_directory(self, directory, recursive=True):
        if self.is_processing:
            self.add_log("Processing already in progress")
            return False
        
        self.is_processing = True
        self.should_stop = False
        self.progress = 0
        self.processed_images = 0
        self.skipped_images = 0
        self.failed_images = 0
        self.logs = []
        self.start_time = datetime.now()
        self.processing_images.clear()  # Reset the set of images being processed
        
        try:
            # Collect all images
            image_files = []
            self.add_log(f"Searching for images in {directory}")
            
            for root, _, files in os.walk(directory):
                if not recursive and root != directory:
                    continue
                
                for file in files:
                    if file.lower().endswith(IMAGE_EXTENSIONS):
                        image_files.append(os.path.join(root, file))
        
            # Remove potential duplicates
            image_files = list(set(image_files))
            
            self.total_images = len(image_files)
            self.add_log(f"Found {self.total_images} images to process")
            
            if self.total_images == 0:
                self.add_log("No images found")
                self.is_processing = False
                return True
            
            # First check which images are already in the cache
            cached_images = []
            for image_path in image_files:
                if _is_in_cache(image_path, self.force_processing):
                    cached_images.append(image_path)
            
            if cached_images:
                self.add_log(f"Found {len(cached_images)} images already in cache")
                self.skipped_images += len(cached_images)
                # Remove cached images from the list to process
                image_files = [img for img in image_files if img not in cached_images]
            
            # Update progress immediately
            self.progress = (self.processed_images + self.skipped_images + self.failed_images) / self.total_images * 100
            
            # Process images in batches
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
                for batch_index in range(0, len(image_files), self.batch_size):
                    if self.should_stop:
                        self.add_log("Processing stopped by user")
                        break
                    
                    batch = image_files[batch_index:batch_index+self.batch_size]
                    
                    # Only submit images that aren't already being processed
                    futures = {}
                    for image_path in batch:
                        if image_path not in self.processing_images:
                            self.processing_images.add(image_path)
                            futures[executor.submit(self.process_image, image_path)] = image_path
                
                    for future in concurrent.futures.as_completed(futures):
                        image_path = futures[future]
                        try:
                            result = future.result()
                            if result == "SKIPPED":
                                self.skipped_images += 1
                            elif result:
                                self.processed_images += 1
                            else:  # None = failed
                                self.failed_images += 1
                            
                            # Remove the image from the set of images being processed
                            self.processing_images.discard(image_path)
                            
                            # Update progress
                            self.progress = (self.processed_images + self.skipped_images + self.failed_images) / self.total_images * 100
                        except Exception as e:
                            self.add_log(f"Error processing {image_path}: {str(e)}")
                            self.failed_images += 1
                            self.processing_images.discard(image_path)
                    
                    # Pause between batches
                    if batch_index + self.batch_size < len(image_files) and self.pause_between_batches > 0 and not self.should_stop:
                        self.add_log(f"Pausing for {self.pause_between_batches} seconds between batches")
                        time.sleep(self.pause_between_batches)
            
            self.add_log(f"Processing complete. Processed: {self.processed_images}, Skipped: {self.skipped_images}, Failed: {self.failed_images}")
            return True
        except Exception as e:
            self.add_log(f"Error processing directory: {str(e)}")
            return False
        finally:
            self.is_processing = False
            self.processing_images.clear()

    def process_image(self, image_path):
        """Process a single image and generate keywords"""
        temp_files_to_clean = []  # List to track all temporary files created
        
        try:
            if self.should_stop:
                return False
        
            self.add_log(f"Processing {image_path}")
            self.add_log(f"Using model: {self.model} with temperature: {self.temperature}")
        
            # Check if image is already in cache
            if _is_in_cache(image_path, self.force_processing):
                self.add_log(f"Image already processed (in cache): {image_path}")
                return "SKIPPED"
        
            # Check if an XMP file already exists and has keywords
            xmp_path = os.path.splitext(image_path)[0] + '.xmp'
        
            # If XMP validation is enabled and XMP file already exists with keywords
            if self.validate_xmp and os.path.exists(xmp_path):
                if has_keywords_in_xmp(xmp_path):
                    self.add_log(f"XMP file with keywords already exists, skipped")
                    # Add to cache to prevent future processing
                    _add_to_cache(image_path)
                    return "SKIPPED"
            
            # Extract metadata
            metadata = self.extract_image_metadata(image_path)
            self.add_log(f"Metadata extracted: {len(metadata)} elements")
            
            # Check if it's a RAW file and convert if necessary
            ext = os.path.splitext(image_path)[1].lower()
            temp_dir = None
            image_to_process = None
            
            try:
                if ext in RAW_EXTENSIONS:
                    # Convert RAW to JPEG temporary
                    temp_image_path, temp_dir = convert_raw_to_jpeg(image_path, self.max_size)
                    if not temp_image_path:
                        self.add_log(f"Could not convert RAW file {image_path}")
                        return None
                    
                    image_to_process = temp_image_path
                    if temp_dir:
                        temp_files_to_clean.append(("dir", temp_dir))
                    if temp_image_path:
                        temp_files_to_clean.append(("file", temp_image_path))
                else:
                    # Resize image if needed
                    image_to_process = self._resize_image_if_needed(image_path)
                    if image_to_process != image_path:
                        temp_files_to_clean.append(("file", image_to_process))
                
                # Add image to cache BEFORE processing to prevent race conditions
                _add_to_cache(image_path)
                
                # Analyze image with Ollama using the new improved function
                response = self.ollama_client.generate_with_image(
                    self.model, 
                    image_to_process,
                    self.system_prompt,
                    self.user_prompt,
                    self.temperature,
                    max_retries=self.max_retries
                )
            
                if not response:
                    self.add_log(f"Failed to analyze image: {image_path}")
                    return None
                
                # Log the raw response from the model
                self.add_log(f"Raw model response for {os.path.basename(image_path)}: {response[:200]}...")
            
                # Try to parse response as JSON
                try:
                    # Clean the response to ensure it's valid JSON
                    if response:
                        # Find the first '{' and the last '}'
                        start_idx = response.find('{')
                        end_idx = response.rfind('}')
                        
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            json_str = response[start_idx:end_idx+1]
                            # Parse JSON to validate it
                            keywords = json.loads(json_str)
                            
                            # Add metadata information if available
                            if metadata.get('exif'):
                                # Extract relevant EXIF data
                                exif = metadata['exif']
                                technical_info = []
                                
                                # Camera model
                                if 'Model' in exif:
                                    technical_info.append(f"camera:{exif['Model']}")
                                
                                # Focal length
                                if 'FocalLength' in exif:
                                    focal_length = exif['FocalLength']
                                    if isinstance(focal_length, tuple) and len(focal_length) == 2:
                                        technical_info.append(f"focal_length:{focal_length[0]/focal_length[1]}mm")
                                    else:
                                        technical_info.append(f"focal_length:{focal_length}mm")
                                
                                # Aperture
                                if 'FNumber' in exif:
                                    f_number = exif['FNumber']
                                    if isinstance(f_number, tuple) and len(f_number) == 2:
                                        technical_info.append(f"aperture:f/{f_number[0]/f_number[1]}")
                                    else:
                                        technical_info.append(f"aperture:f/{f_number}")
                                
                                # ISO
                                if 'ISOSpeedRatings' in exif:
                                    technical_info.append(f"iso:{exif['ISOSpeedRatings']}")
                                
                                # Exposure time
                                if 'ExposureTime' in exif:
                                    exp_time = exif['ExposureTime']
                                    if isinstance(exp_time, tuple) and len(exp_time) == 2:
                                        technical_info.append(f"exposure:{exp_time[0]}/{exp_time[1]}s")
                                    else:
                                        technical_info.append(f"exposure:{exp_time}s")
                                
                                # Add technical info to JSON data if not empty
                                if technical_info and 'technical' in keywords:
                                    keywords['technical'].extend(technical_info)
                            
                            self.add_log(f"Successfully parsed JSON response with metadata")
                        else:
                            self.add_log(f"Invalid JSON structure in response")
                            keywords = clean_and_repair_json(response)
                    else:
                        self.add_log(f"Empty response from model")
                        keywords = {"subjects": [], "objects": [], "scene": ["Description not available"]}
                except json.JSONDecodeError:
                    self.add_log(f"Invalid response (not JSON): {response[:100]}...")
                    keywords = clean_and_repair_json(response)
            
                # Write metadata to XMP file
                self.save_xmp(image_path, xmp_path, keywords)
            
                # Write metadata to JPG file if requested
                if self.write_jpg_metadata:
                    # Check if the file is a JPG or if there's an associated JPG for RAW files
                    jpg_to_update = None
                    
                    if os.path.splitext(image_path)[1].lower() in ['.jpg', '.jpeg']:
                        jpg_to_update = image_path
                    elif os.path.splitext(image_path)[1].lower() in RAW_EXTENSIONS:
                        # Look for associated JPG
                        potential_jpg = os.path.splitext(image_path)[0] + '.jpg'
                        if os.path.exists(potential_jpg):
                            jpg_to_update = potential_jpg
                            self.add_log(f"Associated JPG found for RAW: {jpg_to_update}")
                        else:
                            potential_jpg = os.path.splitext(image_path)[0] + '.jpeg'
                            if os.path.exists(potential_jpg):
                                jpg_to_update = potential_jpg
                                self.add_log(f"Associated JPEG found for RAW: {jpg_to_update}")
                    
                    if jpg_to_update:
                        if EXIFTOOL_AVAILABLE:
                            keywords_list, scene_desc = extract_keywords_from_json(keywords)
                            success = save_jpg_metadata_with_exiftool(jpg_to_update, keywords_list, scene_desc)
                        else:
                            success = save_jpg_metadata_with_pillow(jpg_to_update, None, None)
                        
                        if success:
                            self.add_log(f"Metadata written to JPG file: {jpg_to_update}")
                        else:
                            self.add_log(f"Failed to write metadata to JPG file: {jpg_to_update}")
            
                self.add_log(f"Image processed successfully: {image_path}")
                return True
                
            finally:
                # Clean up all temporary files
                self._cleanup_temp_files(temp_files_to_clean)
                
        except Exception as e:
            self.add_log(f"Error processing {image_path}: {str(e)}")
            return None

    def save_xmp(self, image_path, xmp_path, description):
        """Save description to XMP file"""
        try:
            # Extract keywords from JSON for JPG metadata
            keywords, scene_description = extract_keywords_from_json(description)
            self.add_log(f"Extracted {len(keywords)} keywords for XMP")
            if scene_description:
                self.add_log(f"Scene description: {scene_description[:50]}...")
            
            # Check if XMP file already exists and we want to preserve settings
            existing_xmp_content = None
            if self.preserve_xmp and os.path.exists(xmp_path):
                try:
                    with open(xmp_path, 'r', encoding='utf-8') as f:
                        existing_xmp_content = f.read()
                    self.add_log(f"Existing XMP file found and will be preserved: {xmp_path}")
                except Exception as e:
                    self.add_log(f"Cannot read existing XMP file: {str(e)}")
            
            # Prepare keyword tags in Lightroom format
            keywords_xml = ""
            if keywords:
                keywords_xml = "<dc:subject>\n            <rdf:Bag>\n"
                for keyword in keywords:
                    # Escape XML special characters
                    keyword = keyword.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
                    keywords_xml += f"               <rdf:li>{keyword}</rdf:li>\n"
                keywords_xml += "            </rdf:Bag>\n         </dc:subject>"
            
            # Prepare description (caption) in Lightroom format
            description_xml = ""
            if scene_description:
                # Escape XML special characters
                scene_description = scene_description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
                description_xml = f'<dc:description>\n            <rdf:Alt>\n               <rdf:li xml:lang="x-default">{scene_description}</rdf:li>\n            </rdf:Alt>\n         </dc:description>'
            
            # If we have existing XMP content and want to preserve it
            if existing_xmp_content and self.preserve_xmp:
                try:
                    import re
                    
                    # Replace description if we have a scene description
                    if scene_description:
                        desc_pattern = r'<dc:description>.*?</dc:description>'
                        updated_xmp = re.sub(desc_pattern, description_xml, existing_xmp_content, flags=re.DOTALL)
                    else:
                        updated_xmp = existing_xmp_content
                    
                    # Replace or add keywords
                    if '<dc:subject>' in updated_xmp and keywords:
                        keywords_pattern = r'<dc:subject>.*?</dc:subject>'
                        updated_xmp = re.sub(keywords_pattern, keywords_xml, updated_xmp, flags=re.DOTALL)
                    elif keywords:
                        # Add keywords before the end of rdf:Description
                        updated_xmp = updated_xmp.replace('</rdf:Description>', f'{keywords_xml}\n         </rdf:Description>')
                    
                    # Replace or add lightkeyia:keywords
                    if '<lightkeyia:keywords>' in updated_xmp:
                        keywords_pattern = r'<lightkeyia:keywords>.*?</lightkeyia:keywords>'
                        # Store raw JSON without XML escaping
                        new_keywords = f'<lightkeyia:keywords>{json.dumps(description)}</lightkeyia:keywords>'
                        updated_xmp = re.sub(keywords_pattern, new_keywords, updated_xmp, flags=re.DOTALL)
                    else:
                        # Add lightkeyia namespace if not present
                        if 'xmlns:lightkeyia="http://lightkeyia.com/ns/1.0/"' not in updated_xmp:
                            ns_pattern = r'<rdf:Description rdf:about=""([^>]*)>'
                            ns_replacement = r'<rdf:Description rdf:about=""\1 xmlns:lightkeyia="http://lightkeyia.com/ns/1.0/">'
                            updated_xmp = re.sub(ns_pattern, ns_replacement, updated_xmp)
                        
                        # Add keywords before the end of rdf:Description
                        keywords_insertion = f'         <lightkeyia:keywords>{json.dumps(description)}</lightkeyia:keywords>\n      '
                        updated_xmp = updated_xmp.replace('</rdf:Description>', f'{keywords_insertion}</rdf:Description>')
                    
                    # Write updated XMP
                    with open(xmp_path, 'w', encoding='utf-8') as f:
                        f.write(updated_xmp)
                    
                    self.add_log(f"Updated XMP file preserving existing settings")
                    return True
                    
                except Exception as e:
                    self.add_log(f"Error updating existing XMP file: {str(e)}")
                    self.add_log("Creating new XMP file without preserving settings")
            
            # Create new XMP file
            xmp_content = f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 5.5.0">
   <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
      <rdf:Description rdf:about=""
            xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:xmp="http://ns.adobe.com/xap/1.0/"
            xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/"
            xmlns:lightkeyia="http://lightkeyia.com/ns/1.0/">
         {description_xml}
         {keywords_xml}
         <xmp:MetadataDate>{datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}</xmp:MetadataDate>
         <xmpRights:Marked>True</xmpRights:Marked>
         <lightkeyia:keywords>{json.dumps(description)}</lightkeyia:keywords>
      </rdf:Description>
   </rdf:RDF>
</x:xmpmeta>"""
            
            # Write XMP file
            with open(xmp_path, 'w', encoding='utf-8') as f:
                f.write(xmp_content)
            
            self.add_log(f"New XMP file saved")
            return True
        except Exception as e:
            self.add_log(f"Error saving XMP file: {str(e)}")
            return False

    def stop_processing(self):
        if self.is_processing:
            self.should_stop = True
            self.add_log("Processing stop requested...")
            return True
        return False

    def get_progress(self):
        if not self.is_processing:
            return {
                "status": "idle",
                "progress": 100 if self.total_images > 0 and self.processed_images + self.skipped_images + self.failed_images >= self.total_images else 0,
                "total": self.total_images,
                "processed": self.processed_images,
                "skipped": self.skipped_images,
                "failed": self.failed_images,
                "logs": self.logs,
                "timeElapsed": "00:00:00",
                "timeRemaining": "--:--:--"
            }
        
        # Calculate elapsed time
        elapsed = datetime.now() - self.start_time
        elapsed_str = str(elapsed).split('.')[0]  # Format HH:MM:SS
        
        # Calculate remaining time
        if self.processed_images + self.skipped_images > 0:
            images_done = self.processed_images + self.skipped_images + self.failed_images
            images_left = self.total_images - images_done
            
            if images_left > 0 and images_done > 0:
                seconds_per_image = elapsed.total_seconds() / images_done
                remaining_seconds = images_left * seconds_per_image
                remaining = timedelta(seconds=int(remaining_seconds))
                remaining_str = str(remaining).split('.')[0]  # Format HH:MM:SS
            else:
                remaining_str = "--:--:--"
        else:
            remaining_str = "--:--:--"
        
        return {
            "status": "processing" if not self.should_stop else "stopping",
            "progress": self.progress,
            "total": self.total_images,
            "processed": self.processed_images,
            "skipped": self.skipped_images,
            "failed": self.failed_images,
            "logs": self.logs,
            "timeElapsed": elapsed_str,
            "timeRemaining": remaining_str
        }

class ImageProcessorGUI:
    """GUI for the image processor"""
    
    def __init__(self, master):
        self.root = master
        self.root.title(f"Lightkey.ia - Ollama (Standalone) v{VERSION}")
        self.root.geometry("900x700")
        
        # Set application icon if available
        try:
            if platform.system() == "Windows":
                self.root.iconbitmap("icon.ico")
            elif platform.system() == "Linux":
                img = tk.PhotoImage(file="icon.png")
                self.root.tk.call('wm', 'iconphoto', self.root._w, img)
        except:
            pass
        
        # Initialize variables with default values
        self.model_var = tk.StringVar(value="gemma3:4b")
        self.ollama_url_var = tk.StringVar(value=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
        self.max_size_var = tk.
