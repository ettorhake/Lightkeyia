#!/usr/bin/env python3
"""
LightKeyia - Client Ollama avec support multi-instances
"""

import os
import json
import time
import base64
import threading
import tempfile
import random
import requests
from PIL import Image
from config import logger, RAW_EXTENSIONS, RAWPY_AVAILABLE, DEFAULT_OLLAMA_URL

class OllamaInstance:
    """Représente une instance d'Ollama avec son URL et ses statistiques"""
    
    def __init__(self, url):
        self.url = url
        self.active_requests = 0
        self.total_requests = 0
        self.failed_requests = 0
        self.total_processing_time = 0
        self.last_response_time = 0
        self.is_available = True
        self.last_check_time = 0
        self.models = []
        self.semaphore = None  # Sera initialisé par OllamaClient
    
    def update_stats(self, success, response_time):
        """Mettre à jour les statistiques de l'instance"""
        self.total_requests += 1
        self.last_response_time = response_time
        self.total_processing_time += response_time
        
        if not success:
            self.failed_requests += 1
    
    def get_average_response_time(self):
        """Obtenir le temps de réponse moyen"""
        if self.total_requests > 0:
            return self.total_processing_time / self.total_requests
        return 0
    
    def get_success_rate(self):
        """Obtenir le taux de succès"""
        if self.total_requests > 0:
            return (self.total_requests - self.failed_requests) / self.total_requests * 100
        return 100
    
    def __str__(self):
        return f"Ollama Instance: {self.url} (Active: {self.active_requests}, Total: {self.total_requests}, Avg Time: {self.get_average_response_time():.2f}s)"

    def is_overloaded(self):
        """Déterminer si l'instance est surchargée"""
        # Une instance est considérée comme surchargée si :
        # 1. Elle a beaucoup de requêtes actives (proche du maximum)
        # 2. Son temps de réponse moyen récent est élevé
        # 3. Son taux d'échec récent est élevé
        
        # Vérifier le nombre de requêtes actives
        if self.active_requests >= self.semaphore._value * 0.8:  # 80% de la capacité maximale
            return True
        
        # Vérifier le temps de réponse récent (si disponible)
        if self.total_requests > 5 and self.last_response_time > 10:  # Plus de 10 secondes
            return True
        
        # Vérifier le taux d'échec récent
        recent_failure_threshold = 0.3  # 30% d'échecs
        if self.total_requests > 5 and self.failed_requests / self.total_requests > recent_failure_threshold:
            return True
        
        return False
    
    def get_health_score(self):
        """Calculer un score de santé pour l'instance (plus élevé = meilleure santé)"""
        if not self.is_available:
            return 0
        
        # Score de base
        score = 100
        
        # Pénalité pour les requêtes actives
        if self.semaphore._value > 0:  # Éviter division par zéro
            active_ratio = self.active_requests / self.semaphore._value
            score -= active_ratio * 40  # Jusqu'à -40 points
        
        # Pénalité pour le temps de réponse
        if self.total_requests > 0:
            avg_time = self.get_average_response_time()
            if avg_time > 10:
                score -= min(30, avg_time / 2)  # Jusqu'à -30 points
        
        # Pénalité pour les échecs
        if self.total_requests > 0:
            failure_rate = self.failed_requests / self.total_requests
            score -= failure_rate * 30  # Jusqu'à -30 points
        
        return max(0, score)  # Assurer que le score n'est pas négatif

class OllamaClient:
    """Client for interacting with multiple Ollama instances"""
    
    def __init__(self, ollama_urls=None):
        # Si aucune URL n'est fournie, utiliser l'URL par défaut
        if not ollama_urls:
            ollama_urls = [DEFAULT_OLLAMA_URL]
        elif isinstance(ollama_urls, str):
            ollama_urls = [ollama_urls]
        
        # Initialiser les instances
        self.instances = []
        for url in ollama_urls:
            self.instances.append(OllamaInstance(url))
        
        # Paramètres de contrôle de concurrence
        self.max_concurrent_requests = 3  # Nombre maximum de requêtes simultanées par instance
        
        # Initialiser les sémaphores pour chaque instance
        for instance in self.instances:
            instance.semaphore = threading.Semaphore(self.max_concurrent_requests)
        
        # Stratégie de répartition de charge
        self.load_balancing_strategy = "round_robin"  # "round_robin", "least_busy", "random", "fastest"
        self.current_instance_index = 0  # Pour la stratégie round-robin
        
        # Vérifier la disponibilité des instances
        self._check_instances()
    
    def _check_instances(self):
        """Vérifier la disponibilité de toutes les instances"""
        for instance in self.instances:
            try:
                response = requests.get(f"{instance.url}", timeout=5)
                instance.is_available = response.status_code == 200
                instance.last_check_time = time.time()
                
                if instance.is_available:
                    # Récupérer la liste des modèles disponibles
                    try:
                        models_response = requests.get(f"{instance.url}/api/tags", timeout=10)
                        if models_response.status_code == 200:
                            instance.models = [model.get('name', '') for model in models_response.json().get('models', [])]
                    except:
                        instance.models = []
                
                logger.info(f"Instance Ollama {instance.url}: {'Available' if instance.is_available else 'Unavailable'}")
            except Exception as e:
                instance.is_available = False
                logger.error(f"Error checking Ollama instance {instance.url}: {str(e)}")
    
    def reset_instance_stats(self, instance=None):
        """Réinitialiser les statistiques d'une instance ou de toutes les instances"""
        if instance:
            instance.total_requests = 0
            instance.failed_requests = 0
            instance.total_processing_time = 0
            logger.info(f"Statistics reset for instance {instance.url}")
        else:
            for inst in self.instances:
                inst.total_requests = 0
                inst.failed_requests = 0
                inst.total_processing_time = 0
            logger.info("Statistics reset for all instances")
    
    def auto_reset_stats(self, interval=3600):
        """Démarrer un thread pour réinitialiser automatiquement les statistiques"""
        def reset_thread():
            while True:
                time.sleep(interval)
                self.reset_instance_stats()
        
        thread = threading.Thread(target=reset_thread, daemon=True)
        thread.start()
        logger.info(f"Auto-reset of instance statistics enabled (interval: {interval}s)")
    
    def get_available_instances(self):
        """Obtenir la liste des instances disponibles"""
        return [instance for instance in self.instances if instance.is_available]
    
    def get_instance_for_model(self, model_name):
        """Obtenir les instances qui ont le modèle spécifié"""
        available_instances = self.get_available_instances()
        instances_with_model = []
        
        for instance in available_instances:
            if not instance.models or model_name in instance.models:
                instances_with_model.append(instance)
        
        return instances_with_model if instances_with_model else available_instances
    
    def _select_instance(self, model_name=None):
        """Sélectionner une instance selon la stratégie de répartition de charge"""
        available_instances = self.get_instance_for_model(model_name) if model_name else self.get_available_instances()
        
        if not available_instances:
            logger.error("No available Ollama instances")
            return None
        
        # Filtrer les instances surchargées si possible
        healthy_instances = [i for i in available_instances if not i.is_overloaded()]
        
        # S'il n'y a pas d'instances saines, utiliser toutes les instances disponibles
        # mais ajouter une pause pour donner du temps aux instances de récupérer
        if not healthy_instances and len(available_instances) > 0:
            logger.warning("All instances are overloaded, adding a recovery pause")
            time.sleep(2)  # Pause de récupération
            instances_to_use = available_instances
        else:
            instances_to_use = healthy_instances if healthy_instances else available_instances
        
        selected_instance = None
        
        if self.load_balancing_strategy == "round_robin":
            # Stratégie round-robin
            selected_instance = instances_to_use[self.current_instance_index % len(instances_to_use)]
            self.current_instance_index += 1
        
        elif self.load_balancing_strategy == "least_busy":
            # Sélectionner l'instance la moins occupée
            selected_instance = min(instances_to_use, key=lambda x: x.active_requests)
        
        elif self.load_balancing_strategy == "fastest":
            # Sélectionner l'instance avec le temps de réponse moyen le plus rapide
            # Exclure les instances sans historique
            instances_with_history = [i for i in instances_to_use if i.total_requests > 0]
            if instances_with_history:
                selected_instance = min(instances_with_history, key=lambda x: x.get_average_response_time())
            else:
                # Si aucune instance n'a d'historique, utiliser round-robin
                selected_instance = instances_to_use[self.current_instance_index % len(instances_to_use)]
                self.current_instance_index += 1
        
        elif self.load_balancing_strategy == "health_based":
            # Nouvelle stratégie basée sur le score de santé
            # Calculer les scores de santé pour toutes les instances
            instances_with_scores = [(i, i.get_health_score()) for i in instances_to_use]
            
            # Trier par score de santé (du plus élevé au plus bas)
            instances_with_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Sélectionner l'instance avec le meilleur score de santé
            if instances_with_scores:
                selected_instance = instances_with_scores[0][0]
            else:
                # Fallback à round-robin si aucune instance n'a de score
                selected_instance = instances_to_use[self.current_instance_index % len(instances_to_use)]
                self.current_instance_index += 1
        
        else:  # "random" ou autre
            # Sélection aléatoire
            selected_instance = random.choice(instances_to_use)
        
        # Log détaillé de la sélection d'instance
        if selected_instance:
            logger.info(f"Selected instance {selected_instance.url} using strategy '{self.load_balancing_strategy}' (active: {selected_instance.active_requests}, total: {selected_instance.total_requests})")
        
        return selected_instance
    
    def is_ollama_running(self):
        """Vérifier si au moins une instance d'Ollama est disponible"""
        self._check_instances()
        return len(self.get_available_instances()) > 0
    
    def list_models(self):
        """Lister tous les modèles disponibles sur toutes les instances"""
        all_models = []
        
        for instance in self.get_available_instances():
            try:
                response = requests.get(f"{instance.url}/api/tags", timeout=10)
                if response.status_code == 200:
                    models = response.json().get('models', [])
                    all_models.extend(models)
            except Exception as e:
                logger.error(f"Error listing models from {instance.url}: {str(e)}")
        
        # Éliminer les doublons en conservant les métadonnées
        unique_models = {}
        for model in all_models:
            name = model.get('name', '')
            if name and name not in unique_models:
                unique_models[name] = model
        
        return list(unique_models.values())
    
    def load_model(self, model_name):
        """Précharger un modèle sur toutes les instances disponibles"""
        success = False
        
        for instance in self.get_available_instances():
            try:
                # Vérifier si le modèle est déjà téléchargé sur cette instance
                if instance.models and model_name in instance.models:
                    logger.info(f"Modèle {model_name} déjà disponible sur {instance.url}")
                    success = True
                    continue
                
                logger.info(f"Préchargement du modèle {model_name} sur {instance.url}...")
                
                # Télécharger le modèle si nécessaire
                pull_response = requests.post(
                    f"{instance.url}/api/pull",
                    json={"name": model_name},
                    timeout=600  # Timeout plus long pour le téléchargement
                )
                
                if pull_response.status_code != 200:
                    logger.error(f"Erreur lors du téléchargement du modèle sur {instance.url}: {pull_response.status_code}")
                    continue
                
                # Initialiser le modèle avec une requête simple
                response = requests.post(
                    f"{instance.url}/api/generate",
                    json={
                        "model": model_name,
                        "prompt": "Hello",
                        "stream": False
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    logger.info(f"Modèle {model_name} chargé sur {instance.url}")
                    # Ajouter le modèle à la liste des modèles disponibles
                    if model_name not in instance.models:
                        instance.models.append(model_name)
                    success = True
                else:
                    logger.error(f"Erreur lors de l'initialisation du modèle sur {instance.url}: {response.status_code}")
            except Exception as e:
                logger.error(f"Exception lors du chargement du modèle sur {instance.url}: {str(e)}")
        
        return success
    
    def generate(self, model, prompt, system_prompt=None, temperature=0.5, max_retries=3, request_timeout=60):
        """Generate text with Ollama using load balancing"""
        retries = 0
        
        while retries < max_retries:
            # Sélectionner une instance selon la stratégie de répartition
            instance = self._select_instance(model)
            
            if not instance:
                logger.error("No available Ollama instances for generation")
                return None
            
            start_time = time.time()
            success = False
            
            try:
                # Acquérir le sémaphore pour limiter la concurrence
                acquired = instance.semaphore.acquire(timeout=30)  # Attendre jusqu'à 30 secondes
                if not acquired:
                    logger.warning(f"Impossible d'acquérir le sémaphore pour {instance.url} après 30 secondes, nouvelle tentative...")
                    retries += 1
                    continue
                
                # Incrémenter le compteur de requêtes actives
                instance.active_requests += 1
                
                try:
                    payload = {
                        "model": model,
                        "prompt": prompt,
                        "temperature": temperature,
                        "stream": False
                    }
                    
                    if system_prompt:
                        payload["system"] = system_prompt
                    
                    logger.info(f"Envoi de la requête à {instance.url} avec le modèle {model} (tentative {retries+1}/{max_retries})")
                    
                    # Utiliser un en-tête keep-alive pour maintenir la connexion
                    headers = {
                        "Content-Type": "application/json",
                        "Connection": "keep-alive"
                    }
                    
                    response = requests.post(
                        f"{instance.url}/api/generate",
                        json=payload,
                        headers=headers,
                        timeout=request_timeout
                    )
                    
                    response_time = time.time() - start_time
                    
                    if response.status_code == 200:
                        success = True
                        instance.update_stats(True, response_time)
                        return response.json().get('response', '')
                    else:
                        logger.error(f"Error generating text on {instance.url}: {response.status_code} - {response.text}")
                        instance.update_stats(False, response_time)
                        retries += 1
                        time.sleep(2)  # Wait before retrying
                finally:
                    # Décrémenter le compteur de requêtes actives
                    instance.active_requests -= 1
                    # Toujours libérer le sémaphore
                    instance.semaphore.release()
            except Exception as e:
                response_time = time.time() - start_time
                instance.update_stats(False, response_time)
                logger.error(f"Exception generating text on {instance.url}: {str(e)}")
                retries += 1
                time.sleep(2)  # Wait before retrying
                # S'assurer que le sémaphore est libéré en cas d'exception
                try:
                    instance.active_requests -= 1
                    instance.semaphore.release()
                except:
                    pass
        
        return None
    
    def chat(self, model, messages, temperature=0.5, max_retries=3, request_timeout=60):
        """Chat with Ollama using load balancing"""
        retries = 0
        
        while retries < max_retries:
            # Sélectionner une instance selon la stratégie de répartition
            instance = self._select_instance(model)
            
            if not instance:
                logger.error("No available Ollama instances for chat")
                return None
            
            start_time = time.time()
            success = False
            
            try:
                # Acquérir le sémaphore pour limiter la concurrence
                acquired = instance.semaphore.acquire(timeout=30)  # Attendre jusqu'à 30 secondes
                if not acquired:
                    logger.warning(f"Impossible d'acquérir le sémaphore pour {instance.url} après 30 secondes, nouvelle tentative...")
                    retries += 1
                    continue
                
                # Incrémenter le compteur de requêtes actives
                instance.active_requests += 1
                
                try:
                    payload = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": False
                    }
                    
                    logger.info(f"Envoi de la requête chat à {instance.url} avec le modèle {model} (tentative {retries+1}/{max_retries})")
                    
                    # Utiliser un en-tête keep-alive pour maintenir la connexion
                    headers = {
                        "Content-Type": "application/json",
                        "Connection": "keep-alive"
                    }
                    
                    response = requests.post(
                        f"{instance.url}/api/chat",
                        json=payload,
                        headers=headers,
                        timeout=request_timeout
                    )
                    
                    response_time = time.time() - start_time
                    
                    if response.status_code == 200:
                        success = True
                        instance.update_stats(True, response_time)
                        return response.json().get('message', {}).get('content', '')
                    else:
                        logger.error(f"Error chatting on {instance.url}: {response.status_code} - {response.text}")
                        instance.update_stats(False, response_time)
                        retries += 1
                        time.sleep(2)  # Wait before retrying
                finally:
                    # Décrémenter le compteur de requêtes actives
                    instance.active_requests -= 1
                    # Toujours libérer le sémaphore
                    instance.semaphore.release()
            except Exception as e:
                response_time = time.time() - start_time
                instance.update_stats(False, response_time)
                logger.error(f"Exception chatting on {instance.url}: {str(e)}")
                retries += 1
                time.sleep(2)  # Wait before retrying
                # S'assurer que le sémaphore est libéré en cas d'exception
                try:
                    instance.active_requests -= 1
                    instance.semaphore.release()
                except:
                    pass
        
        return None
    
    def _encode_image_to_base64(self, image_path):
        """Encode image to base64"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding image: {str(e)}")
            return None
    
    def generate_with_image(self, model, image_path, system_prompt=None, user_prompt=None, 
                           temperature=0.5, max_retries=3, request_timeout=60, skip_chat_api=False):
        """Generate text with image using Ollama with load balancing"""
        try:
            # Encode image to base64
            base64_image = self._encode_image_to_base64(image_path)
            if not base64_image:
                return None
            
            # Use chat API by default (more reliable for multimodal)
            if not skip_chat_api:
                messages = [
                    {
                        "role": "user",
                        "content": user_prompt or "Analyze this image and provide detailed keywords.",
                        "images": [base64_image]
                    }
                ]
                
                if system_prompt:
                    messages.insert(0, {
                        "role": "system",
                        "content": system_prompt
                    })
                
                return self.chat(model, messages, temperature, max_retries, request_timeout)
            else:
                # Fallback to generate API
                prompt = f"{user_prompt or 'Analyze this image and provide detailed keywords.'}\n"
                prompt += f"![Image](data:image/jpeg;base64,{base64_image})"
                
                return self.generate(model, prompt, system_prompt, temperature, max_retries, request_timeout)
        except Exception as e:
            logger.error(f"Error generating with image: {str(e)}")
            return None
    
    def extract_json_from_response(self, response_text):
        """Extract JSON from response text"""
        try:
            # Try to find JSON block in markdown format
            if "```json" in response_text:
                # Extract JSON from markdown code block
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                if end != -1:
                    json_str = response_text[start:end].strip()
                    return json.loads(json_str)
            elif "```" in response_text:
                # Try generic code block
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                if end != -1:
                    json_str = response_text[start:end].strip()
                    return json.loads(json_str)
            
            # Try to find JSON directly
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = response_text[start:end+1]
                return json.loads(json_str)
            
            # If all else fails, try to parse the entire response
            return json.loads(response_text)
        except Exception as e:
            logger.error(f"Error extracting JSON from response: {str(e)}")
            return None
    
    def _process_raw_image(self, image_path):
        """Process RAW image and return base64 data"""
        try:
            if RAWPY_AVAILABLE:
                try:
                    logger.info(f"Processing RAW file with rawpy: {image_path}")
                    import rawpy
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
    
    def _process_standard_image(self, image_path):
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
        if "```json" in response_text:
            # Extract content between ```json and ```
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end != -1:
                return response_text[start:end].strip()
        elif "```" in response_text:
            # Extract content between ``` and ```
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
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
    
    def force_balanced_usage(self):
        """Forcer l'utilisation équilibrée de toutes les instances"""
        # Réinitialiser les statistiques de toutes les instances
        self.reset_instance_stats()
        
        # Forcer l'utilisation de round-robin pour quelques requêtes
        original_strategy = self.load_balancing_strategy
        self.load_balancing_strategy = "round_robin"
        
        # Réinitialiser l'index pour round-robin
        self.current_instance_index = 0
        
        logger.info("Forcing balanced usage of all instances")
        
        # Restaurer la stratégie originale
        self.load_balancing_strategy = original_strategy
        
        return True
