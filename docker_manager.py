#!/usr/bin/env python3
"""
LightKeyia - Gestionnaire de conteneurs Docker Ollama
"""

import os
import time
import json
import subprocess
import requests
from config import logger

class DockerManager:
    """Gestionnaire de conteneurs Docker pour Ollama"""
    
    def __init__(self):
        self.docker_available = self._check_docker_available()
        self.logger = logger
    
    def _check_docker_available(self):
        """Vérifier si Docker est disponible sur le système"""
        try:
            result = subprocess.run(["docker", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                logger.info(f"Docker disponible: {result.stdout.strip()}")
                return True
            else:
                logger.warning("Docker n'est pas disponible sur ce système")
                return False
        except Exception as e:
            logger.error(f"Erreur lors de la vérification de Docker: {str(e)}")
            return False
    
    def create_ollama_network(self):
        """Créer un réseau Docker pour les instances Ollama s'il n'existe pas déjà"""
        if not self.docker_available:
            return False, "Docker n'est pas disponible"
        
        try:
            # Vérifier si le réseau existe déjà
            result = subprocess.run(
                ["docker", "network", "ls", "--filter", "name=ollama-network", "--format", "{{.Name}}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        
            if "ollama-network" in result.stdout:
                logger.info("Le réseau ollama-network existe déjà")
                return True, "Le réseau ollama-network existe déjà"
        
            # Créer le réseau
            result = subprocess.run(
                ["docker", "network", "create", "ollama-network"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        
            if result.returncode != 0:
                logger.error(f"Erreur lors de la création du réseau: {result.stderr}")
                return False, f"Erreur lors de la création du réseau: {result.stderr}"
        
            logger.info("Réseau ollama-network créé avec succès")
            return True, "Réseau ollama-network créé avec succès"
        except Exception as e:
            logger.error(f"Erreur lors de la création du réseau: {str(e)}")
            return False, str(e)

    def list_ollama_containers(self):
        """Lister tous les conteneurs Ollama (en cours d'exécution ou non)"""
        if not self.docker_available:
            return []
        
        try:
            # Lister tous les conteneurs avec le filtre "ollama"
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", "ancestor=ollama/ollama", "--format", "{{.ID}}|{{.Names}}|{{.Status}}|{{.Ports}}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Erreur lors de la liste des conteneurs: {result.stderr}")
                return []
            
            containers = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('|')
                if len(parts) >= 4:
                    container_id, name, status, ports = parts[:4]
                    
                    # Extraire le port mappé
                    port = 11434  # Port par défaut
                    if "0.0.0.0:" in ports:
                        try:
                            port_part = ports.split("0.0.0.0:")[1].split("->")[0]
                            port = int(port_part)
                        except:
                            pass
                    
                    # Déterminer si le conteneur est en cours d'exécution
                    is_running = status.startswith("Up ")
                    
                    containers.append({
                        "id": container_id,
                        "name": name,
                        "status": status,
                        "is_running": is_running,
                        "port": port,
                        "url": f"http://localhost:{port}"
                    })
            
            return containers
        except Exception as e:
            logger.error(f"Erreur lors de la liste des conteneurs: {str(e)}")
            return []
    
    def create_ollama_container(self, name, port, volume_name=None, use_network=True):
        """Créer un nouveau conteneur Ollama"""
        if not self.docker_available:
            return False, "Docker n'est pas disponible"
        
        try:
            # Vérifier si le port est déjà utilisé
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Ports}}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            if result.returncode != 0:
                return False, f"Erreur lors de la vérification des ports: {result.stderr}"
            
            for line in result.stdout.strip().split('\n'):
                if f"0.0.0.0:{port}->" in line:
                    return False, f"Le port {port} est déjà utilisé par un autre conteneur"
        
            # Créer le volume si nécessaire
            if not volume_name:
                volume_name = f"ollama_{name}_data"
        
            # Créer le réseau si nécessaire et si demandé
            if use_network:
                self.create_ollama_network()
        
            # Créer le conteneur
            cmd = [
                "docker", "run", "-d",
                "--name", name,
                "-p", f"{port}:11434",
                "-v", f"{volume_name}:/root/.ollama"
            ]
        
            # Connecter au réseau si demandé
            if use_network:
                cmd.extend(["--network", "ollama-network"])
        
            # Ajouter des options pour la GPU si disponible
            if self._check_gpu_available():
                cmd.extend(["--gpus", "all"])
        
            cmd.append("ollama/ollama")
        
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
            if result.returncode != 0:
                return False, f"Erreur lors de la création du conteneur: {result.stderr}"
        
            container_id = result.stdout.strip()
            logger.info(f"Conteneur Ollama créé: {name} (ID: {container_id}, Port: {port})")
        
            # Attendre que le conteneur soit prêt
            time.sleep(2)
        
            return True, container_id
        except Exception as e:
            logger.error(f"Erreur lors de la création du conteneur: {str(e)}")
            return False, str(e)
    
    def start_container(self, container_id):
        """Démarrer un conteneur existant"""
        if not self.docker_available:
            return False, "Docker n'est pas disponible"
        
        try:
            result = subprocess.run(
                ["docker", "start", container_id],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            if result.returncode != 0:
                return False, f"Erreur lors du démarrage du conteneur: {result.stderr}"
            
            logger.info(f"Conteneur démarré: {container_id}")
            return True, "Conteneur démarré avec succès"
        except Exception as e:
            logger.error(f"Erreur lors du démarrage du conteneur: {str(e)}")
            return False, str(e)
    
    def stop_container(self, container_id):
        """Arrêter un conteneur"""
        if not self.docker_available:
            return False, "Docker n'est pas disponible"
        
        try:
            result = subprocess.run(
                ["docker", "stop", container_id],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            if result.returncode != 0:
                return False, f"Erreur lors de l'arrêt du conteneur: {result.stderr}"
            
            logger.info(f"Conteneur arrêté: {container_id}")
            return True, "Conteneur arrêté avec succès"
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt du conteneur: {str(e)}")
            return False, str(e)
    
    def remove_container(self, container_id, force=False):
        """Supprimer un conteneur"""
        if not self.docker_available:
            return False, "Docker n'est pas disponible"
        
        try:
            cmd = ["docker", "rm"]
            if force:
                cmd.append("-f")
            cmd.append(container_id)
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                return False, f"Erreur lors de la suppression du conteneur: {result.stderr}"
            
            logger.info(f"Conteneur supprimé: {container_id}")
            return True, "Conteneur supprimé avec succès"
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du conteneur: {str(e)}")
            return False, str(e)
    
    def check_ollama_api(self, url):
        """Vérifier si l'API Ollama est accessible à l'URL spécifiée"""
        try:
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def check_model_available(self, url, model_name):
        """Vérifier si un modèle spécifique est disponible sur l'instance Ollama"""
        try:
            response = requests.get(f"{url}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get('models', [])
                for model in models:
                    if model.get('name') == model_name:
                        return True
            return False
        except:
            return False
    
    def pull_model(self, url, model_name):
        """Télécharger un modèle sur une instance Ollama"""
        try:
            response = requests.post(
                f"{url}/api/pull",
                json={"name": model_name},
                timeout=600  # Timeout plus long pour le téléchargement
            )
            
            if response.status_code == 200:
                logger.info(f"Modèle {model_name} téléchargé avec succès sur {url}")
                return True, "Modèle téléchargé avec succès"
            else:
                logger.error(f"Erreur lors du téléchargement du modèle: {response.status_code} - {response.text}")
                return False, f"Erreur: {response.text}"
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement du modèle: {str(e)}")
            return False, str(e)
    
    def _check_gpu_available(self):
        """Vérifier si une GPU est disponible pour Docker"""
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.Runtimes}}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            if result.returncode == 0 and "nvidia" in result.stdout:
                return True
            
            # Vérifier avec nvidia-smi
            nvidia_result = subprocess.run(
                ["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            
            return nvidia_result.returncode == 0
        except:
            return False
    
    def create_multiple_containers(self, base_name, start_port, count, use_network=True):
        """Créer plusieurs conteneurs Ollama"""
        results = []
        
        # Créer le réseau si nécessaire et si demandé
        if use_network:
            network_success, network_message = self.create_ollama_network()
            if not network_success:
                logger.warning(f"Problème lors de la création du réseau: {network_message}")
        
        for i in range(count):
            name = f"{base_name}{i+1}"
            port = start_port + i
            success, message = self.create_ollama_container(name, port, use_network=use_network)
            results.append({
                "name": name,
                "port": port,
                "success": success,
                "message": message
            })
        
        return results
