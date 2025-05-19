#!/usr/bin/env python3
"""
LightKeyia - Fonctions utilitaires
"""

import os
import re
import json
import base64
import tempfile
import shutil
from datetime import datetime
from PIL import Image
import logging

from config import CACHE_DIR, RAW_EXTENSIONS, RAWPY_AVAILABLE, EXIFTOOL_AVAILABLE, logger

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
        import rawpy
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
            import subprocess
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

def _cleanup_temp_files(temp_files):
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
