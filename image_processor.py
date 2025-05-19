#!/usr/bin/env python3
"""
LightKeyia - Processeur d'images
"""

import os
import time
import json
import threading
import concurrent.futures
import tempfile
from datetime import datetime, timedelta
from PIL import Image
import psutil

from config import RAW_EXTENSIONS, EXIFTOOL_AVAILABLE, USER_PROMPT, DEFAULT_SYSTEM_PROMPT, DEFAULT_OLLAMA_URL, logger
from utils import (_is_in_cache, _add_to_cache, has_keywords_in_xmp, clean_and_repair_json, 
                  extract_keywords_from_json, convert_raw_to_jpeg, save_jpg_metadata_with_exiftool, 
                  save_jpg_metadata_with_pillow, _cleanup_temp_files)
from ollama_client import OllamaClient

class ImageProcessor:
    """Image processor for analysis with Ollama and XMP keyword generation"""
    
    def __init__(self, model="gemma3:4b", ollama_urls=None, load_balancing_strategy="round_robin",
                 max_size=512, temperature=0.5, threads=4, 
                 validate_xmp=True, preserve_xmp=True, write_jpg_metadata=True, force_processing=False,
                 batch_size=5, pause_between_batches=5, skip_chat_api=False, system_prompt=None,
                 request_timeout=300, max_concurrent_requests=3):
        
        self.model = model
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
        self.user_prompt = USER_PROMPT
        self.max_retries = 3
        self.request_timeout = request_timeout
        self.max_concurrent_requests = max_concurrent_requests
        self.load_balancing_strategy = load_balancing_strategy
        
        self.system_prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT
        
        # Processing state
        self.is_processing = False
        self.should_stop = False
        # État de pause
        self.paused = False
        self.pause_event = threading.Event()  # Pour gérer la pause/reprise
        self.pause_event.set()  # Par défaut, non en pause
        self.pause_lock = threading.Lock()
        self.pause_condition = threading.Condition(self.pause_lock)
        self.progress = 0
        self.total_images = 0
        self.processed_images = 0
        self.skipped_images = 0
        self.failed_images = 0
        self.logs = []
        self.start_time = None
        self.pause_start_time = None  # Pour suivre le temps de pause
        self.total_pause_time = 0     # Temps total de pause
        self.processing_images = set()  # Set to track images being processed
        self.last_log_message = None   # To avoid repetitive logs
        self.last_log_time = None      # To limit log frequency
        
        # Statistiques de traitement
        self.processing_times = []  # Liste des temps de traitement pour calculer la moyenne
        
        # Initialize Ollama client
        self.ollama_client = OllamaClient(ollama_urls)
        # Configurer le nombre maximum de requêtes concurrentes
        self.ollama_client.max_concurrent_requests = self.max_concurrent_requests
        # Configurer la stratégie de répartition de charge
        self.ollama_client.load_balancing_strategy = self.load_balancing_strategy
        self._check_ollama_connection()

        # Démarrer le monitoring des instances
        self.monitor_instances_health(interval=60)
        
        # Activer la réinitialisation automatique des statistiques
        self.ollama_client.auto_reset_stats(interval=3600)  # Toutes les heures

    def monitor_instances_health(self, interval=60):
        """Démarrer un thread pour surveiller la santé des instances Ollama"""
        def monitor_thread():
            while True:
                try:
                    if self.is_processing:
                        # Vérifier l'état des instances
                        self.ollama_client._check_instances()
                        
                        # Vérifier les instances surchargées
                        overloaded_instances = [i for i in self.ollama_client.instances if i.is_overloaded()]
                        if overloaded_instances:
                            self.add_log(f"Detected {len(overloaded_instances)} overloaded instances")
                            
                            # Réinitialiser les statistiques des instances surchargées
                            for instance in overloaded_instances:
                                self.add_log(f"Resetting statistics for overloaded instance: {instance.url}")
                                self.ollama_client.reset_instance_stats(instance)
                        
                        # Vérifier si toutes les instances sont indisponibles
                        available_instances = self.ollama_client.get_available_instances()
                        if not available_instances and self.ollama_client.instances:
                            self.add_log("WARNING: All Ollama instances are unavailable!")
                            
                            # Tenter de récupérer les instances
                            self.add_log("Attempting to recover instances...")
                            time.sleep(10)  # Pause pour laisser les instances récupérer
                            self.ollama_client._check_instances()
                except Exception as e:
                    logger.error(f"Error in health monitoring thread: {str(e)}")
                
                time.sleep(interval)
        
        thread = threading.Thread(target=monitor_thread, daemon=True)
        thread.start()
        self.add_log(f"Instance health monitoring started (interval: {interval}s)")

    def _check_ollama_connection(self):
        try:
            if self.ollama_client.is_ollama_running():
                logger.info(f"Connection to Ollama established with {len(self.ollama_client.get_available_instances())} available instances")
                return True
            else:
                logger.error(f"Error connecting to Ollama: No available instances")
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
        
        # Limiter la taille de la liste des logs pour éviter les problèmes de mémoire
        if len(self.logs) >= 1000:
            # Garder seulement les 500 derniers logs
            self.logs = self.logs[-500:]
        
        self.logs.append(log_entry)
        logger.info(message)
        
        # Update last message and time
        self.last_log_message = message
        self.last_log_time = current_time

    def clear_cache(self):
        from utils import clear_cache
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

    def process_directory(self, directory, recursive=True):
        if self.is_processing:
            self.add_log("Processing already in progress")
            return False
        
        self.is_processing = True
        self.should_stop = False
        self.paused = False
        self.pause_event.set()  # Réinitialiser l'événement de pause
        self.progress = 0
        self.processed_images = 0
        self.skipped_images = 0
        self.failed_images = 0
        self.logs = []  # Réinitialiser les logs au début du traitement
        self.processing_times = []  # Réinitialiser les temps de traitement
        self.start_time = datetime.now()
        self.pause_start_time = None
        self.total_pause_time = 0
        self.processing_images.clear()  # Reset the set of images being processed
        
        try:
            # Préchargement du modèle avant de commencer le traitement
            self.add_log(f"Préchargement du modèle {self.model} sur toutes les instances...")
            if not self.ollama_client.load_model(self.model):
                self.add_log(f"Avertissement: Le préchargement du modèle a échoué, mais le traitement continue")
            else:
                self.add_log(f"Modèle {self.model} préchargé avec succès sur les instances disponibles")
            
            # Collect all images
            image_files = []
            self.add_log(f"Searching for images in {directory}")
            
            for root, _, files in os.walk(directory):
                if not recursive and root != directory:
                    continue
                
                for file in files:
                    if file.lower().endswith(RAW_EXTENSIONS) or any(file.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.heif']):
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
            if self.total_images > 0:  # Éviter la division par zéro
                self.progress = (self.processed_images + self.skipped_images + self.failed_images) / self.total_images * 100
            
            # Traiter les images par lots avec une gestion adaptative de la charge
            batch_index = 0
            consecutive_failures = 0
            adaptive_pause = self.pause_between_batches
            stats_check_counter = 0
            
            while batch_index < len(image_files):
                # Vérifier si le traitement doit être arrêté
                if self.should_stop:
                    self.add_log("Processing stopped by user")
                    break
                
                # Vérifier si le traitement est en pause
                if self.paused:
                    # Si c'est le début de la pause, enregistrer le temps de début
                    if self.pause_start_time is None:
                        self.pause_start_time = datetime.now()
                        self.add_log("Processing paused")
                    
                    # Attendre que la pause soit terminée
                    self.pause_event.wait(1)  # Vérifier toutes les secondes
                    continue
                elif self.pause_start_time is not None:
                    # Si on sort de la pause, calculer le temps de pause
                    pause_duration = (datetime.now() - self.pause_start_time).total_seconds()
                    self.total_pause_time += pause_duration
                    self.add_log(f"Processing resumed after {pause_duration:.1f} seconds")
                    self.pause_start_time = None
                
                # Déterminer la taille du lot en fonction des échecs précédents
                current_batch_size = max(1, self.batch_size - consecutive_failures)
                batch = image_files[batch_index:batch_index+current_batch_size]
                batch_index += len(batch)
                
                self.add_log(f"Processing batch of {len(batch)} images (adaptive size: {current_batch_size})")
                
                # Vérifier la charge du système avant de soumettre le lot
                system_load = psutil.cpu_percent(interval=0.5)
                if system_load > 90:  # Charge CPU élevée
                    self.add_log(f"System load is high ({system_load}%), pausing for recovery")
                    time.sleep(10)  # Pause plus longue pour récupération
                    continue
                
                # Only submit images that aren't already being processed
                futures = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
                    for image_path in batch:
                        # Vérifier si le traitement est en pause
                        if self.paused:
                            # Attendre que la pause soit terminée
                            self.pause_event.wait(1)  # Vérifier toutes les secondes
                            continue
                        
                        if image_path not in self.processing_images:
                            self.processing_images.add(image_path)
                            futures[executor.submit(self.process_image, image_path)] = image_path
                
                    # Compter les succès et échecs pour ce lot
                    batch_failures = 0
                    
                    for future in concurrent.futures.as_completed(futures):
                        image_path = futures[future]
                        try:
                            result, processing_time = future.result()
                            if processing_time:
                                self.processing_times.append(processing_time)
                            
                            if result == "SKIPPED":
                                self.skipped_images += 1
                            elif result:
                                self.processed_images += 1
                            else:  # None = failed
                                self.failed_images += 1
                                batch_failures += 1
                            
                            # Remove the image from the set of images being processed
                            self.processing_images.discard(image_path)
                            
                            # Update progress
                            if self.total_images > 0:  # Éviter la division par zéro
                                self.progress = (self.processed_images + self.skipped_images + self.failed_images) / self.total_images * 100
                        except Exception as e:
                            self.add_log(f"Error processing {image_path}: {str(e)}")
                            self.failed_images += 1
                            self.processing_images.discard(image_path)
                            batch_failures += 1
                
                # Ajuster la pause et la taille du lot en fonction des résultats
                if batch_failures > 0:
                    consecutive_failures += 1
                    # Augmenter la pause si des échecs se produisent
                    adaptive_pause = min(60, adaptive_pause * 1.5)  # Maximum 60 secondes
                    self.add_log(f"Batch had {batch_failures} failures, increasing pause to {adaptive_pause:.1f}s")
                else:
                    consecutive_failures = max(0, consecutive_failures - 1)
                    # Réduire progressivement la pause si tout va bien
                    adaptive_pause = max(self.pause_between_batches, adaptive_pause * 0.8)
                
                # Pause adaptative entre les lots
                if batch_index < len(image_files) and adaptive_pause > 0 and not self.should_stop and not self.paused:
                    self.add_log(f"Pausing for {adaptive_pause:.1f} seconds between batches")
                    time.sleep(adaptive_pause)
                
                # Vérifier périodiquement l'état des instances Ollama
                stats_check_counter += 1
                if stats_check_counter % 5 == 0:  # Tous les 5 lots
                    self.add_log("--- Instance Statistics ---")
                    for i, instance in enumerate(self.ollama_client.instances):
                        if instance.is_available:
                            self.add_log(f"Instance {i+1} ({instance.url}): Active: {instance.active_requests}, Total: {instance.total_requests}, Avg Time: {instance.get_average_response_time():.2f}s")
                    self.add_log("-------------------------")
            
            self.add_log(f"=== PROCESSING COMPLETE === Processed: {self.processed_images}, Skipped: {self.skipped_images}, Failed: {self.failed_images}")
            
            # Calculer et afficher les statistiques de traitement
            if self.processing_times:
                avg_time = sum(self.processing_times) / len(self.processing_times)
                self.add_log(f"Average processing time per image: {avg_time:.2f} seconds")
                
                if self.processed_images > 0:
                    total_time = (datetime.now() - self.start_time).total_seconds() - self.total_pause_time
                    images_per_second = self.processed_images / total_time if total_time > 0 else 0
                    self.add_log(f"Processing speed: {images_per_second:.2f} images per second")
                    self.add_log(f"Total pause time: {self.total_pause_time:.1f} seconds")
            
            # Afficher les statistiques des instances
            self.add_log("Instance statistics:")
            for i, instance in enumerate(self.ollama_client.instances):
                if instance.is_available:
                    self.add_log(f"Instance {i+1} ({instance.url}): {instance.total_requests} requests, {instance.get_average_response_time():.2f}s avg time")
            
            return True
        except Exception as e:
            self.add_log(f"Error processing directory: {str(e)}")
            return False
        finally:
            self.is_processing = False
            self.paused = False
            self.pause_event.set()
            self.processing_images.clear()

    def process_image(self, image_path):
        """Process a single image and generate keywords"""
        temp_files_to_clean = []  # List to track all temporary files created
        start_time = time.time()  # Mesurer le temps de traitement
        processing_time = None
        
        try:
            if self.should_stop:
                return False, None
            
            # Vérifier si le traitement est en pause
            self.pause_event.wait()
        
            self.add_log(f"Processing {image_path}")
            self.add_log(f"Using model: {self.model} with temperature: {self.temperature}")
        
            # Check if image is already in cache
            if _is_in_cache(image_path, self.force_processing):
                self.add_log(f"Image already processed (in cache): {image_path}")
                return "SKIPPED", None
        
            # Check if an XMP file already exists and has keywords
            xmp_path = os.path.splitext(image_path)[0] + '.xmp'
        
            # If XMP validation is enabled and XMP file already exists with keywords
            if self.validate_xmp and os.path.exists(xmp_path):
                if has_keywords_in_xmp(xmp_path):
                    self.add_log(f"XMP file with keywords already exists, skipped")
                    # Add to cache to prevent future processing
                    _add_to_cache(image_path)
                    return "SKIPPED", None
            
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
                        return None, None
                    
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
                    max_retries=self.max_retries,
                    request_timeout=self.request_timeout
                )
            
                if not response:
                    self.add_log(f"Failed to analyze image: {image_path}")
                    return None, None
                
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
            
                # Calculer le temps de traitement
                processing_time = time.time() - start_time
                self.add_log(f"Image processed successfully in {processing_time:.2f} seconds: {image_path}")
                
                self.update_progress_state()
                return True, processing_time
                
            finally:
                # Clean up all temporary files
                _cleanup_temp_files(temp_files_to_clean)
                
        except Exception as e:
            self.add_log(f"Error processing {image_path}: {str(e)}")
            return None, None

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
        """Arrêter le traitement"""
        if self.is_processing:
            self.should_stop = True
            self.paused = False
            self.pause_event.set()  # Réveiller les threads en attente
            self.add_log("Processing stop requested...")
            return True
        return False
    
    def pause_processing(self):
        """Mettre en pause le traitement des images"""
        self.paused = True
        self.pause_event.clear()  # Bloquer l'événement de pause
        self.add_log("Traitement mis en pause")
            
    def resume_processing(self):
        """Reprendre le traitement des images"""
        self.paused = False
        self.pause_event.set()  # Débloquer l'événement de pause
        self.add_log("Traitement repris")
            
    def is_paused(self):
        """Vérifier si le traitement est en pause"""
        return self.paused

    def get_progress(self):
        """Obtenir l'état actuel du traitement"""
        # Calculer le temps écoulé
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            # Soustraire le temps de pause si on est en pause
            if self.paused and self.pause_start_time:
                pause_time = datetime.now() - self.pause_start_time
                elapsed = elapsed - pause_time
            # Soustraire le temps total de pause
            elapsed = elapsed - timedelta(seconds=self.total_pause_time)
            elapsed_str = str(elapsed).split('.')[0]  # Format HH:MM:SS
        else:
            elapsed_str = "00:00:00"
        
        # Calculer le nombre total d'images traitées
        processed_total = self.processed_images + self.skipped_images + self.failed_images
        
        # Calculer le pourcentage de progression
        if self.total_images > 0:
            progress_percent = min(100, (processed_total / self.total_images) * 100)
        else:
            progress_percent = 0
        
        # Calculer le temps restant estimé
        if self.is_processing and processed_total > 0 and self.total_images > processed_total:
            if self.start_time:
                elapsed_seconds = (datetime.now() - self.start_time).total_seconds() - self.total_pause_time
                if self.paused and self.pause_start_time:
                    elapsed_seconds -= (datetime.now() - self.pause_start_time).total_seconds()
                
                if elapsed_seconds > 0:
                    seconds_per_image = elapsed_seconds / processed_total
                    remaining_images = self.total_images - processed_total
                    remaining_seconds = seconds_per_image * remaining_images
                    remaining = timedelta(seconds=int(remaining_seconds))
                    remaining_str = str(remaining).split('.')[0]  # Format HH:MM:SS
                else:
                    remaining_str = "--:--:--"
            else:
                remaining_str = "--:--:--"
        else:
            remaining_str = "--:--:--"
        
        # Déterminer le statut
        if not self.is_processing:
            status = "idle"
        elif self.should_stop:
            status = "stopping"
        elif self.paused:
            status = "paused"
        else:
            status = "processing"
        
        # Calculer les statistiques de traitement
        avg_processing_time = 0
        images_per_second = 0
        
        if self.processing_times:
            avg_processing_time = sum(self.processing_times) / len(self.processing_times)
            
            if elapsed_seconds > 0:
                images_per_second = self.processed_images / elapsed_seconds
        
        return {
            "status": status,
            "progress": progress_percent,
            "total": self.total_images,
            "processed": self.processed_images,
            "skipped": self.skipped_images,
            "failed": self.failed_images,
            "logs": self.logs[-200:] if len(self.logs) > 200 else self.logs,  # Limiter le nombre de logs pour éviter les problèmes de mémoire
            "timeElapsed": elapsed_str,
            "timeRemaining": remaining_str,
            "avgProcessingTime": avg_processing_time,
            "imagesPerSecond": images_per_second,
            "isPaused": self.is_paused
        }

    def update_progress_state(self):
        """Mettre à jour l'état de progression"""
        if self.total_images > 0:
            self.progress = min(100, (self.processed_images + self.skipped_images + self.failed_images) / self.total_images * 100)
        else:
            self.progress = 0
