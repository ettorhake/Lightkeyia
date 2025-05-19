#!/usr/bin/env python3
"""
LightKeyia - Configuration et constantes
"""

import os
import logging
import sys
from datetime import datetime

# Version
VERSION = "1.4.0"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("lightkeyia.log", mode="a")]
)
logger = logging.getLogger("LightKeyia")

# Extensions de fichiers
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.heif',
                   '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.raf', '.orf', '.rw2',
                   '.pef', '.dng', '.raw', '.rwl', '.iiq', '.3fr', '.x3f')
RAW_EXTENSIONS = ('.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.raf', '.orf', '.rw2',
                 '.pef', '.dng', '.raw', '.rwl', '.iiq', '.3fr', '.x3f')

# URLs pour Ollama
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_CLOUD_URL = None  # Sera rempli dynamiquement quand le mode cloud est activé

# Valeurs par défaut pour le traitement d'images
DEFAULT_MODEL = "gemma3:4b"
DEFAULT_PROMPT = "What do you see in detail?"
DEFAULT_BATCH_SIZE = 5
DEFAULT_MAX_CONCURRENT_REQUESTS = 3

# Répertoire de cache
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".lightkeyia_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Vérification des dépendances optionnelles
try:
    import rawpy
    RAWPY_AVAILABLE = True
    logger.info("rawpy is available for RAW file processing")
except ImportError:
    RAWPY_AVAILABLE = False
    logger.warning("rawpy is not available. RAW processing will be limited.")

# Vérification d'ExifTool
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

# Prompts par défaut
USER_PROMPT = "What do you see in detail?"

DEFAULT_SYSTEM_PROMPT = """You are an image analysis system. Your task is to analyze the provided photograph and extract keywords in different categories.

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
