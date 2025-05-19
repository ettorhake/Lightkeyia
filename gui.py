#!/usr/bin/env python3
"""
LightKeyia - Interface graphique
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog
import threading
import platform
import time
import psutil  # Pour surveiller l'utilisation des ressources
import webbrowser
import requests

from config import VERSION, logger, DEFAULT_OLLAMA_URL, DEFAULT_MODEL, DEFAULT_PROMPT, DEFAULT_BATCH_SIZE, DEFAULT_MAX_CONCURRENT_REQUESTS
from image_processor import ImageProcessor
from docker_manager import DockerManager
from ollama_client import OllamaClient
from theme import apply_theme, COLORS

class ImageProcessorGUI:
    """GUI for the image processor"""
    
    def __init__(self, master):
        self.root = master
        self.root.title(f"Lightkey.ia - Ollama (Standalone) v{VERSION}")
        self.root.geometry("900x700")
        
        # Appliquer le thème personnalisé
        self.style = apply_theme(self.root)
        
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
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.ollama_url_var = tk.StringVar(value=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL))
        self.max_size_var = tk.IntVar(value=896)
        self.temperature_var = tk.DoubleVar(value=0.5)
        self.threads_var = tk.IntVar(value=4)
        self.batch_size_var = tk.IntVar(value=DEFAULT_BATCH_SIZE)
        self.pause_between_batches_var = tk.IntVar(value=5)
        self.validate_xmp_var = tk.BooleanVar(value=True)
        self.preserve_xmp_var = tk.BooleanVar(value=True)
        self.write_jpg_metadata_var = tk.BooleanVar(value=True)
        self.force_processing_var = tk.BooleanVar(value=False)
        self.skip_chat_api_var = tk.BooleanVar(value=False)
        self.recursive_var = tk.BooleanVar(value=True)
        
        # Variables pour les instances Ollama multiples
        self.ollama_instances_var = tk.StringVar(value=DEFAULT_OLLAMA_URL)
        self.load_balancing_strategy_var = tk.StringVar(value="round_robin")
        
        # Variables pour Docker
        self.docker_base_name_var = tk.StringVar(value="ollama")
        self.docker_start_port_var = tk.IntVar(value=11434)
        self.docker_container_count_var = tk.IntVar(value=3)
        self.use_docker_network_var = tk.BooleanVar(value=True)
        self.use_local_ollama_var = tk.BooleanVar(value=True)
        
        # Ajouter une variable pour le timeout
        self.request_timeout_var = tk.IntVar(value=300)
        
        # Ajouter une variable pour le nombre maximum de requêtes concurrentes
        self.max_concurrent_requests_var = tk.IntVar(value=DEFAULT_MAX_CONCURRENT_REQUESTS)
        
        # Variables pour le contrôle des logs
        self.displayed_logs = set()  # Pour suivre les logs déjà affichés
        self.update_timer = None     # Pour suivre le timer de mise à jour
        self.is_processing = False   # Pour suivre l'état du traitement
        
        # Ajouter une variable pour le mode cloud
        self.cloud_mode_var = tk.BooleanVar(value=False)
        
        # Initialize Docker manager
        self.docker_manager = DockerManager()
        
        # Ajouter après la ligne "self.docker_manager = DockerManager()"
        self.processor_initialized = False
        
        # Create UI first
        self.create_ui()
        
        # Initialize processor after UI is created
        self.processor = None
        self.update_processor()
        
        # Initial model refresh
        self.refresh_models()
        
        # Start progress update thread
        self.progress_thread = threading.Thread(target=self.update_progress, daemon=True)
        self.progress_thread.start()
        
        # Start resource monitoring thread
        self.resource_thread = threading.Thread(target=self.monitor_resources, daemon=True)
        self.resource_thread.start()
    
    def create_ui(self):
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create tabs
        process_tab = ttk.Frame(notebook)
        settings_tab = ttk.Frame(notebook)
        instances_tab = ttk.Frame(notebook)  # Onglet pour les instances Ollama
        docker_tab = ttk.Frame(notebook)     # Nouvel onglet pour Docker
        monitor_tab = ttk.Frame(notebook)    # Onglet pour le monitoring
        about_tab = ttk.Frame(notebook)
        
        notebook.add(process_tab, text="Process")
        notebook.add(settings_tab, text="Settings")
        notebook.add(instances_tab, text="Instances")
        notebook.add(docker_tab, text="Docker")      # Ajouter l'onglet Docker
        notebook.add(monitor_tab, text="Monitor")
        notebook.add(about_tab, text="About")
        
        # Process tab
        self.create_process_tab(process_tab)
        
        # Settings tab
        self.create_settings_tab(settings_tab)
        
        # Instances tab
        self.create_instances_tab(instances_tab)
        
        # Docker tab
        self.create_docker_tab(docker_tab)
        
        # Monitor tab
        self.create_monitor_tab(monitor_tab)
        
        # About tab
        self.create_about_tab(about_tab)
    
    def create_process_tab(self, parent):
        # Directory selection
        dir_frame = ttk.LabelFrame(parent, text="Directory", padding="10")
        dir_frame.pack(fill=tk.X, pady=5)
        
        self.dir_entry = ttk.Entry(dir_frame)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        browse_btn = ttk.Button(dir_frame, text="Browse", command=self.browse_directory)
        browse_btn.pack(side=tk.RIGHT)
        
        # Options frame
        options_frame = ttk.LabelFrame(parent, text="Processing Options", padding="10")
        options_frame.pack(fill=tk.X, pady=5)
        
        # Model selection
        model_frame = ttk.Frame(options_frame)
        model_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(model_frame, text="Model:").pack(side=tk.LEFT)
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var)
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        refresh_btn = ttk.Button(model_frame, text="Refresh", command=self.refresh_models)
        refresh_btn.pack(side=tk.RIGHT)
        
        # Ajouter un bouton pour précharger le modèle
        preload_btn = ttk.Button(model_frame, text="Précharger", command=self.preload_model)
        preload_btn.pack(side=tk.RIGHT, padx=5)
        
        # Recursive checkbox
        recursive_check = ttk.Checkbutton(options_frame, text="Process subdirectories", variable=self.recursive_var)
        recursive_check.pack(anchor=tk.W, pady=2)
        
        # Force processing checkbox
        force_check = ttk.Checkbutton(options_frame, text="Force processing (ignore cache)", variable=self.force_processing_var)
        force_check.pack(anchor=tk.W, pady=2)
        
        # Buttons frame
        buttons_frame = ttk.Frame(parent)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        self.process_btn = ttk.Button(buttons_frame, text="Process Images", command=self.start_processing)
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        # Bouton Pause/Resume
        self.pause_btn = ttk.Button(buttons_frame, text="Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(buttons_frame, text="Stop", command=self.stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Ajouter un bouton pour effacer les logs
        clear_logs_btn = ttk.Button(buttons_frame, text="Clear Logs", command=self.clear_logs)
        clear_logs_btn.pack(side=tk.LEFT, padx=5)
        
        clear_cache_btn = ttk.Button(buttons_frame, text="Clear Cache", command=self.clear_cache)
        clear_cache_btn.pack(side=tk.RIGHT, padx=5)
        
        # Progress frame
        progress_frame = ttk.LabelFrame(parent, text="Progress", padding="10")
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # Progress info
        info_frame = ttk.Frame(progress_frame)
        info_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(info_frame, text="Status:").grid(row=0, column=0, sticky=tk.W)
        self.status_label = ttk.Label(info_frame, text="Idle")
        self.status_label.grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(info_frame, text="Images:").grid(row=1, column=0, sticky=tk.W)
        self.images_label = ttk.Label(info_frame, text="0/0")
        self.images_label.grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(info_frame, text="Time:").grid(row=2, column=0, sticky=tk.W)
        self.time_label = ttk.Label(info_frame, text="00:00:00 / --:--:--")
        self.time_label.grid(row=2, column=1, sticky=tk.W)
        
        # Log frame
        log_frame = ttk.LabelFrame(progress_frame, text="Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.configure_text_widget(self.log_text)
        
        # Initial model refresh
        #self.refresh_models()
    
    def create_settings_tab(self, parent):
        # Ollama settings
        ollama_frame = ttk.LabelFrame(parent, text="Ollama Settings", padding="10")
        ollama_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(ollama_frame, text="Temperature:").grid(row=0, column=0, sticky=tk.W, pady=2)
        temperature_spinbox = ttk.Spinbox(ollama_frame, from_=0.0, to=1.0, increment=0.1, textvariable=self.temperature_var, width=10)
        temperature_spinbox.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Checkbutton(ollama_frame, text="Skip chat API (use generate API only)", variable=self.skip_chat_api_var).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Après les autres paramètres dans ollama_frame
        ttk.Label(ollama_frame, text="Request timeout (s):").grid(row=2, column=0, sticky=tk.W, pady=2)
        timeout_spinbox = ttk.Spinbox(ollama_frame, from_=60, to=600, increment=30, textvariable=self.request_timeout_var, width=10)
        timeout_spinbox.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        # Ajouter le paramètre de requêtes concurrentes
        ttk.Label(ollama_frame, text="Max concurrent requests:").grid(row=3, column=0, sticky=tk.W, pady=2)
        concurrent_spinbox = ttk.Spinbox(ollama_frame, from_=1, to=10, increment=1, textvariable=self.max_concurrent_requests_var, width=10)
        concurrent_spinbox.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # Image processing settings
        image_frame = ttk.LabelFrame(parent, text="Image Processing", padding="10")
        image_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(image_frame, text="Max image size:").grid(row=0, column=0, sticky=tk.W, pady=2)
        max_size_spinbox = ttk.Spinbox(image_frame, from_=256, to=2048, increment=64, textvariable=self.max_size_var, width=10)
        max_size_spinbox.delete(0, tk.END)
        max_size_spinbox.insert(0, "896")
        max_size_spinbox.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(image_frame, text="Threads:").grid(row=1, column=0, sticky=tk.W, pady=2)
        threads_spinbox = ttk.Spinbox(image_frame, from_=1, to=32, increment=1, textvariable=self.threads_var, width=10)
        threads_spinbox.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(image_frame, text="Batch size:").grid(row=2, column=0, sticky=tk.W, pady=2)
        batch_size_spinbox = ttk.Spinbox(image_frame, from_=1, to=50, increment=1, textvariable=self.batch_size_var, width=10)
        batch_size_spinbox.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(image_frame, text="Pause between batches (s):").grid(row=3, column=0, sticky=tk.W, pady=2)
        pause_spinbox = ttk.Spinbox(image_frame, from_=0, to=60, increment=1, textvariable=self.pause_between_batches_var, width=10)
        pause_spinbox.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # XMP settings
        xmp_frame = ttk.LabelFrame(parent, text="Metadata Settings", padding="10")
        xmp_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(xmp_frame, text="Skip images with existing XMP keywords", variable=self.validate_xmp_var).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(xmp_frame, text="Preserve existing XMP settings", variable=self.preserve_xmp_var).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(xmp_frame, text="Write metadata to JPG files", variable=self.write_jpg_metadata_var).pack(anchor=tk.W, pady=2)
        
        # Mode Cloud frame
        cloud_frame = ttk.LabelFrame(parent, text="Mode Cloud", padding="10")
        cloud_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(cloud_frame, text="Utiliser Ollama dans le cloud (Google Colab)", 
                       variable=self.cloud_mode_var, 
                       command=self.toggle_cloud_mode).pack(anchor=tk.W, pady=2)
        
        ttk.Label(cloud_frame, text="Pour plus de puissance, utilisez Ollama dans le cloud:").pack(anchor=tk.W, pady=2)
        colab_link = ttk.Label(cloud_frame, text="Ouvrir le notebook Google Colab", foreground="blue", cursor="hand2")
        colab_link.pack(anchor=tk.W, pady=2)
        colab_link.bind("<Button-1>", lambda e: self.open_colab_notebook())
        
        # Apply button
        apply_btn = ttk.Button(parent, text="Apply Settings", command=self.update_processor)
        apply_btn.pack(pady=10)
        
        # Configure grid
        parent.columnconfigure(0, weight=1)
    
    def toggle_cloud_mode(self):
        if self.cloud_mode_var.get():
            # Open Colab notebook automatically
            self.open_colab_notebook()
            
            # Show instructions dialog
            messagebox.showinfo("Configuration Cloud",
                             "1. Le notebook Google Colab va s'ouvrir dans votre navigateur\n" +
                             "2. Dans Colab, cliquez sur l'icône 🔑 dans le panneau de gauche\n" +
                             "3. Ajoutez NGROK_AUTH_TOKEN avec votre token ngrok\n" +
                             "4. Exécutez les cellules du notebook dans l'ordre\n" +
                             "5. Copiez l'URL ngrok affichée et collez-la ci-dessous\n\n" +
                             "Une fois prêt, cliquez OK pour configurer l'URL.")
            
            url = simpledialog.askstring("Configuration Cloud", 
                                       "Entrez l'URL ngrok fournie par Google Colab\n(exemple: https://votre-url.ngrok.app):")
            if url and self.validate_cloud_url(url):
                # Sauvegarder l'URL locale actuelle
                if self.ollama_url_var.get() == DEFAULT_OLLAMA_URL:
                    self.local_url = self.ollama_url_var.get()
                
                # Mettre à jour l'URL avec celle de ngrok
                self.ollama_url_var.set(url)
                # Mettre à jour les instances Ollama et désactiver les fonctionnalités locales
                self.ollama_instances_var.set(url)
                self.use_local_ollama_var.set(False)
                
                # Disable Docker controls
                if hasattr(self, 'docker_controls'):
                    for widget in self.docker_controls:
                        widget.configure(state='disabled')

                # Update processor with cloud configuration
                self.update_processor()
                
                messagebox.showinfo("Mode Cloud", 
                                  "Mode cloud activé avec succès!\n\n" +
                                  "Utilisation de l'instance Ollama dans le cloud via ngrok.\n" +
                                  "Le traitement des images sera plus rapide grâce au GPU gratuit de Google Colab.")
            else:
                self.cloud_mode_var.set(False)
        else:
            # Restore local URL and configuration
            if hasattr(self, 'local_url'):
                # Restore local URL
                self.ollama_url_var.set(self.local_url)
                self.ollama_instances_var.set(self.local_url)
                
                # Re-enable local features
                self.use_local_ollama_var.set(True)
                if hasattr(self, 'docker_controls'):
                    for widget in self.docker_controls:
                        widget.configure(state='normal')
                
                # Update processor with local configuration
                self.update_processor()
                
                messagebox.showinfo("Mode Local", 
                                  "Configuration restaurée en mode local.\n" +
                                  "Utilisation de l'instance Ollama locale.")

    def open_colab_notebook(self):
        """Open the Google Colab notebook in the default browser"""
        colab_url = "https://colab.research.google.com/github/ettorhake/lightkeyia/blob/main/lightkeyia_colab.ipynb"
        try:
            webbrowser.open(colab_url)
        except Exception as e:
            messagebox.showerror("Erreur",
                              f"Impossible d'ouvrir le notebook Colab: {str(e)}\n\n" +
                              "Veuillez ouvrir manuellement le lien suivant:\n" +
                              colab_url)
    
    def validate_cloud_url(self, url):
        """Valider l'URL ngrok et tester la connexion"""
        if not url:
            messagebox.showerror("Erreur", "L'URL ne peut pas être vide")
            return False
        
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("Erreur", "L'URL doit commencer par http:// ou https://")
            return False
        
        if "ngrok" not in url.lower():
            messagebox.showerror("Erreur", "L'URL doit être une URL ngrok valide")
            return False
        
        try:
            # Try to connect to the Ollama API
            response = requests.get(f"{url}/api/tags", timeout=10)
            if response.status_code != 200:
                messagebox.showerror("Erreur", 
                                   f"Impossible de se connecter à l'instance Ollama (status: {response.status_code})")
                return False

            # Check if Gemma model is available
            models = response.json().get("models", [])
            if not any("gemma" in model["name"].lower() for model in models):
                messagebox.showwarning("Attention", 
                                     "Le modèle Gemma n'est pas encore disponible sur l'instance cloud.\n" +
                                     "Assurez-vous d'avoir exécuté toutes les cellules du notebook Colab et " +
                                     "que le modèle ait fini de se télécharger.")
            return True
            
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Erreur", f"Impossible de se connecter à l'URL: {str(e)}")
            return False
        
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur inattendue lors de la validation de l'URL: {str(e)}")
            return False
    
    # Modifier la méthode create_instances_tab pour ajouter une explication sur l'utilisation d'Ollama local et Docker
    def create_instances_tab(self, parent):
        """Créer l'onglet de gestion des instances Ollama"""
        # Frame pour les instances Ollama
        instances_frame = ttk.LabelFrame(parent, text="Ollama Instances", padding="10")
        instances_frame.pack(fill=tk.X, pady=5)
        
        # Explication sur l'utilisation d'Ollama local et Docker
        explanation_frame = ttk.LabelFrame(instances_frame, text="Mode d'utilisation", padding="10")
        explanation_frame.pack(fill=tk.X, pady=5)
        
        explanation_text = scrolledtext.ScrolledText(explanation_frame, height=4, wrap=tk.WORD)
        explanation_text.pack(fill=tk.BOTH, expand=True)
        explanation_text.insert(tk.END, """Vous pouvez utiliser Ollama en mode local (installé sur votre machine) ou via des conteneurs Docker, ou les deux en même temps.
Pour configurer les instances Docker, utilisez l'onglet Docker et cliquez sur "Launch Ollama Instances" après avoir démarré les conteneurs.
Pour utiliser uniquement Ollama local, assurez-vous que l'URL "http://localhost:11434" est présente dans la liste ci-dessous.""")
        explanation_text.config(state=tk.DISABLED)
        
        # Liste des instances Ollama (séparées par des virgules)
        ttk.Label(instances_frame, text="Instances URLs (comma separated):").pack(anchor=tk.W, pady=2)
        instances_entry = ttk.Entry(instances_frame, textvariable=self.ollama_instances_var)
        instances_entry.pack(fill=tk.X, pady=2)
        
        # Exemple d'URL
        ttk.Label(instances_frame, text="Example: http://localhost:11434,http://localhost:11435").pack(anchor=tk.W, pady=2)
        
        # Stratégie de répartition de charge
        ttk.Label(instances_frame, text="Load Balancing Strategy:").pack(anchor=tk.W, pady=5)
        
        strategies = ["round_robin", "least_busy", "fastest", "random", "health_based"]
        strategy_combo = ttk.Combobox(instances_frame, textvariable=self.load_balancing_strategy_var, values=strategies)
        strategy_combo.pack(fill=tk.X, pady=2)
        
        # Description des stratégies
        strategies_frame = ttk.LabelFrame(instances_frame, text="Strategies Description", padding="10")
        strategies_frame.pack(fill=tk.X, pady=5)
        
        strategies_text = scrolledtext.ScrolledText(strategies_frame, height=8, wrap=tk.WORD)
        strategies_text.pack(fill=tk.BOTH, expand=True)
        strategies_text.insert(tk.END, """round_robin: Distributes requests evenly across all instances in sequence.
least_busy: Sends requests to the instance with the fewest active requests.
fastest: Selects the instance with the lowest average response time.
random: Randomly selects an instance for each request.
health_based: Selects instances based on a comprehensive health score (recommended).""")
        strategies_text.config(state=tk.DISABLED)
        
        # Boutons pour gérer les instances
        buttons_frame = ttk.Frame(parent)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        # Bouton pour vérifier les instances
        check_instances_btn = ttk.Button(buttons_frame, text="Check Instances", command=self.check_instances)
        check_instances_btn.pack(side=tk.LEFT, padx=5)
        
        # Bouton pour précharger le modèle sur toutes les instances
        preload_all_btn = ttk.Button(buttons_frame, text="Preload Model on All Instances", command=self.preload_model_all_instances)
        preload_all_btn.pack(side=tk.LEFT, padx=5)

        # Bouton pour réinitialiser les statistiques des instances
        reset_stats_btn = ttk.Button(buttons_frame, text="Reset Instance Stats", command=self.reset_instance_stats)
        reset_stats_btn.pack(side=tk.LEFT, padx=5)
        
        # Bouton pour appliquer les changements
        apply_instances_btn = ttk.Button(buttons_frame, text="Apply Changes", command=self.update_processor)
        apply_instances_btn.pack(side=tk.RIGHT, padx=5)
        
        # Frame pour afficher l'état des instances
        status_frame = ttk.LabelFrame(parent, text="Instances Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.instances_status_text = scrolledtext.ScrolledText(status_frame, height=10)
        self.instances_status_text.pack(fill=tk.BOTH, expand=True)
        self.configure_text_widget(self.instances_status_text)
    
    def create_docker_tab(self, parent):
        """Créer l'onglet de gestion des conteneurs Docker"""
        # Initialize list to track Docker-related widgets that should be disabled in cloud mode
        self.docker_controls = []
        
        if not self.docker_manager.docker_available:
            ttk.Label(parent, text="Docker n'est pas disponible sur ce système").pack(pady=20)
            return
        # Vérifier si Docker est disponible
        docker_available = self.docker_manager.docker_available
        
        # Frame pour les options de configuration
        config_frame = ttk.LabelFrame(parent, text="Configuration", padding="10")
        config_frame.pack(fill=tk.X, pady=5)
        
        # Option pour utiliser Ollama local ou Docker
        ttk.Checkbutton(config_frame, text="Utiliser Ollama local (en plus des conteneurs Docker)", 
                   variable=self.use_local_ollama_var).pack(anchor=tk.W, pady=2)
        
        # Option pour utiliser le réseau Docker
        ttk.Checkbutton(config_frame, text="Utiliser le réseau Docker 'ollama-network'", 
                   variable=self.use_docker_network_var).pack(anchor=tk.W, pady=2)
        
        # Bouton pour créer le réseau Docker
        if docker_available:
            network_btn = ttk.Button(config_frame, text="Créer réseau ollama-network", 
                               command=self.create_docker_network)
            network_btn.pack(anchor=tk.W, pady=5)
        
        # Frame pour la création de conteneurs
        create_frame = ttk.LabelFrame(parent, text="Create Ollama Containers", padding="10")
        create_frame.pack(fill=tk.X, pady=5)
        
        # Container base name
        name_frame = ttk.Frame(create_frame)
        name_frame.pack(fill=tk.X, pady=2)
        name_label = ttk.Label(name_frame, text="Container base name:")
        name_label.pack(side=tk.LEFT, padx=(0, 5))
        name_entry = ttk.Entry(name_frame, textvariable=self.docker_base_name_var)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.docker_controls.append(name_entry)
        
        # Starting port
        port_frame = ttk.Frame(create_frame)
        port_frame.pack(fill=tk.X, pady=2)
        port_label = ttk.Label(port_frame, text="Starting port:")
        port_label.pack(side=tk.LEFT, padx=(0, 5))
        port_spinbox = ttk.Spinbox(port_frame, from_=11434, to=65535, textvariable=self.docker_start_port_var)
        port_spinbox.pack(side=tk.LEFT)
        self.docker_controls.append(port_spinbox)
        
        # Number of containers
        count_frame = ttk.Frame(create_frame)
        count_frame.pack(fill=tk.X, pady=2)
        count_label = ttk.Label(count_frame, text="Number of containers:")
        count_label.pack(side=tk.LEFT, padx=(0, 5))
        count_spinbox = ttk.Spinbox(count_frame, from_=1, to=10, textvariable=self.docker_container_count_var)
        count_spinbox.pack(side=tk.LEFT)
        self.docker_controls.append(count_spinbox)
        
        # Docker network option
        network_check = ttk.Checkbutton(create_frame, text="Use Docker network", variable=self.use_docker_network_var)
        network_check.pack(anchor=tk.W, pady=2)
        self.docker_controls.append(network_check)
        
        # Use local Ollama option
        local_check = ttk.Checkbutton(create_frame, text="Use local Ollama instance", variable=self.use_local_ollama_var)
        local_check.pack(anchor=tk.W, pady=2)
        self.docker_controls.append(local_check)
        
        # Buttons frame
        buttons_frame = ttk.Frame(create_frame)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        create_btn = ttk.Button(buttons_frame, text="Create Containers", 
                              command=lambda: self.create_ollama_containers())
        create_btn.pack(side=tk.LEFT, padx=5)
        self.docker_controls.append(create_btn)
        
        launch_btn = ttk.Button(buttons_frame, text="Launch Ollama Instances",
                             command=self.launch_ollama_instances)
        launch_btn.pack(side=tk.LEFT, padx=5)
        self.docker_controls.append(launch_btn)
        
        # Containers list
        containers_frame = ttk.LabelFrame(parent, text="Ollama Containers", padding="10")
        containers_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create treeview with scrollbar for container list
        tree_frame = ttk.Frame(containers_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.containers_tree = ttk.Treeview(tree_frame, columns=("Name", "Status", "Port", "URL"),
                                          selectmode="extended")
        self.containers_tree.heading("#0", text="ID")
        self.containers_tree.heading("Name", text="Name")
        self.containers_tree.heading("Status", text="Status")
        self.containers_tree.heading("Port", text="Port")
        self.containers_tree.heading("URL", text="URL")
        
        self.containers_tree.column("#0", width=100)
        self.containers_tree.column("Name", width=150)
        self.containers_tree.column("Status", width=150)
        self.containers_tree.column("Port", width=100)
        self.containers_tree.column("URL", width=200)
        
        self.containers_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.containers_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.containers_tree.configure(yscrollcommand=scrollbar.set)
        
        # Bind right-click for context menu
        self.containers_tree.bind("<Button-3>", self.show_container_menu)
        self.docker_controls.append(self.containers_tree)
        
        # Refresh button
        refresh_btn = ttk.Button(containers_frame, text="Refresh List", 
                               command=self.refresh_container_list)
        refresh_btn.pack(pady=5)
        self.docker_controls.append(refresh_btn)
        
        # Initial container list refresh
        self.refresh_container_list()
    
    def create_monitor_tab(self, parent):
        """Créer l'onglet de monitoring des ressources"""
        # Frame pour les ressources système
        system_frame = ttk.LabelFrame(parent, text="System Resources", padding="10")
        system_frame.pack(fill=tk.X, pady=5)
        
        # CPU Usage
        ttk.Label(system_frame, text="CPU Usage:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.cpu_label = ttk.Label(system_frame, text="0%")
        self.cpu_label.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        # Memory Usage
        ttk.Label(system_frame, text="Memory Usage:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.memory_label = ttk.Label(system_frame, text="0 MB")
        self.memory_label.grid(row=1, column=1, sticky=tk.W)
        
        # Ollama Process
        ttk.Label(system_frame, text="Ollama Process:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.ollama_label = ttk.Label(system_frame, text="Not found")
        self.ollama_label.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        # Active Threads
        ttk.Label(system_frame, text="Active Threads:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.threads_label = ttk.Label(system_frame, text="0")
        self.threads_label.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # Concurrent Requests
        ttk.Label(system_frame, text="Concurrent Requests:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.requests_label = ttk.Label(system_frame, text="0")
        self.requests_label.grid(row=4, column=1, sticky=tk.W, pady=2)
        
        # Frame pour les statistiques de traitement
        stats_frame = ttk.LabelFrame(parent, text="Processing Statistics", padding="10")
        stats_frame.pack(fill=tk.X, pady=5)
        
        # Images per second
        ttk.Label(stats_frame, text="Images per second:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.ips_label = ttk.Label(stats_frame, text="0")
        self.ips_label.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        # Average processing time
        ttk.Label(stats_frame, text="Avg. processing time:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.avg_time_label = ttk.Label(stats_frame, text="0 sec")
        self.avg_time_label.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # Frame pour les statistiques des instances
        instances_stats_frame = ttk.LabelFrame(parent, text="Instances Statistics", padding="10")
        instances_stats_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.instances_stats_text = scrolledtext.ScrolledText(instances_stats_frame, height=10)
        self.instances_stats_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid
        system_frame.columnconfigure(1, weight=1)
        stats_frame.columnconfigure(1, weight=1)
    
    def create_about_tab(self, parent):
        about_frame = ttk.Frame(parent, padding="20")
        about_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(about_frame, text=f"LightKeyia v{VERSION}", style='Title.TLabel')
        title_label.pack(pady=10)
        ttk.Label(about_frame, text="A tool to analyze images with Ollama and generate keywords in XMP files.").pack(pady=5)
        ttk.Label(about_frame, text="Compatible with standard and RAW formats.").pack(pady=5)
        
        # Dependencies info
        deps_frame = ttk.LabelFrame(about_frame, text="Dependencies", padding="10")
        deps_frame.pack(fill=tk.X, pady=10)
        
        from config import RAWPY_AVAILABLE, EXIFTOOL_AVAILABLE
        
        ttk.Label(deps_frame, text=f"rawpy: {'Available' if RAWPY_AVAILABLE else 'Not available'}").pack(anchor=tk.W)
        ttk.Label(deps_frame, text=f"ExifTool: {'Available' if EXIFTOOL_AVAILABLE else 'Not available'}").pack(anchor=tk.W)
        ttk.Label(deps_frame, text=f"Docker: {'Available' if self.docker_manager.docker_available else 'Not available'}").pack(anchor=tk.W)
        
        # Credits
        credits_frame = ttk.LabelFrame(about_frame, text="Credits", padding="10")
        credits_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(credits_frame, text="Developed by LightKeyia Team").pack(anchor=tk.W)
        ttk.Label(credits_frame, text="Uses Ollama for AI image analysis").pack(anchor=tk.W)
    
    # Modifier la méthode update_processor pour prendre en compte le choix entre Ollama local et Docker
    def update_processor(self):
        # Récupérer la liste des instances Ollama
        if self.cloud_mode_var.get():
            # En mode cloud, utiliser uniquement l'URL ngrok
            ollama_urls = [self.ollama_url_var.get()]
        else:
            # En mode local, utiliser la liste des instances configurées
            ollama_urls = [url.strip() for url in self.ollama_instances_var.get().split(',') if url.strip()]
            
            # Si aucune URL n'est spécifiée, utiliser localhost par défaut
            if not ollama_urls:
                ollama_urls = [DEFAULT_OLLAMA_URL]

        # Éviter les initialisations multiples avec les mêmes paramètres
        if self.processor_initialized and hasattr(self, 'processor') and self.processor is not None:
            # Mettre à jour uniquement les paramètres sans recréer l'objet
            self.processor.model = self.model_var.get()
            self.processor.max_size = self.max_size_var.get()
            self.processor.temperature = self.temperature_var.get()
            self.processor.threads = self.threads_var.get()
            self.processor.validate_xmp = self.validate_xmp_var.get()
            self.processor.preserve_xmp = self.preserve_xmp_var.get()
            self.processor.write_jpg_metadata = self.write_jpg_metadata_var.get()
            self.processor.force_processing = self.force_processing_var.get()
            self.processor.batch_size = self.batch_size_var.get()
            self.processor.pause_between_batches = self.pause_between_batches_var.get()
            self.processor.skip_chat_api = self.skip_chat_api_var.get()
            self.processor.request_timeout = self.request_timeout_var.get()
            self.processor.max_concurrent_requests = self.max_concurrent_requests_var.get()
            
            # Mettre à jour la stratégie de répartition de charge
            if self.processor.load_balancing_strategy != self.load_balancing_strategy_var.get():
                self.processor.load_balancing_strategy = self.load_balancing_strategy_var.get()
                self.processor.ollama_client.load_balancing_strategy = self.load_balancing_strategy_var.get()
            
            # Vérifier si les URLs ont changé
            current_urls = [instance.url for instance in self.processor.ollama_client.instances]
            if set(current_urls) != set(ollama_urls):
                # Recréer le client Ollama avec les nouvelles URLs
                self.processor.ollama_client = OllamaClient(ollama_urls)
                self.processor.ollama_client.max_concurrent_requests = self.processor.max_concurrent_requests
                self.processor.ollama_client.load_balancing_strategy = self.processor.load_balancing_strategy
                self.processor._check_ollama_connection()
        else:
            # Créer un nouveau processeur
            self.processor = ImageProcessor(
                model=self.model_var.get(),
                ollama_urls=ollama_urls,
                load_balancing_strategy=self.load_balancing_strategy_var.get(),
                max_size=self.max_size_var.get(),
                temperature=self.temperature_var.get(),
                threads=self.threads_var.get(),
                validate_xmp=self.validate_xmp_var.get(),
                preserve_xmp=self.preserve_xmp_var.get(),
                write_jpg_metadata=self.write_jpg_metadata_var.get(),
                force_processing=self.force_processing_var.get(),
                batch_size=self.batch_size_var.get(),
                pause_between_batches=self.pause_between_batches_var.get(),
                skip_chat_api=self.skip_chat_api_var.get(),
                request_timeout=self.request_timeout_var.get(),
                max_concurrent_requests=self.max_concurrent_requests_var.get()
            )
            self.processor_initialized = True
    
        # Mettre à jour l'affichage des instances
        self.update_instances_status()
    
    def check_instances(self):
        """Vérifier la disponibilité des instances Ollama"""
        if not self.processor:
            self.update_processor()
        
        self.instances_status_text.delete(1.0, tk.END)
        self.instances_status_text.insert(tk.END, "Checking Ollama instances...\n")
        
        # Vérifier les instances dans un thread séparé
        def check_thread():
            self.processor.ollama_client._check_instances()
            self.root.after(0, self.update_instances_status)
        
        threading.Thread(target=check_thread, daemon=True).start()
    
    def update_instances_status(self):
        """Mettre à jour l'affichage de l'état des instances"""
        if not self.processor or not hasattr(self.processor, 'ollama_client'):
            return
        
        # Vérifier que l'attribut instances_status_text existe
        if not hasattr(self, 'instances_status_text'):
            return
            
        self.instances_status_text.delete(1.0, tk.END)
        
        # Ajouter un message d'information sur la répartition des tâches
        self.instances_status_text.insert(tk.END, f"Stratégie de répartition: {self.load_balancing_strategy_var.get()}\n")
        self.instances_status_text.insert(tk.END, f"Nombre d'instances disponibles: {len(self.processor.ollama_client.get_available_instances())}\n\n")
        
        for i, instance in enumerate(self.processor.ollama_client.instances):
            status = "Available" if instance.is_available else "Unavailable"
            models = ", ".join(instance.models) if instance.models else "None"
            
            self.instances_status_text.insert(tk.END, f"Instance {i+1}: {instance.url}\n")
            self.instances_status_text.insert(tk.END, f"  Status: {status}\n")
            self.instances_status_text.insert(tk.END, f"  Models: {models}\n")
            self.instances_status_text.insert(tk.END, f"  Active Requests: {instance.active_requests}\n")
            self.instances_status_text.insert(tk.END, f"  Total Requests: {instance.total_requests}\n")
            
            if instance.total_requests > 0:
                avg_time = instance.get_average_response_time()
                success_rate = instance.get_success_rate()
                self.instances_status_text.insert(tk.END, f"  Avg Response Time: {avg_time:.2f}s\n")
                self.instances_status_text.insert(tk.END, f"  Success Rate: {success_rate:.1f}%\n")
            
            # Vérifier si gemma3:4b est disponible
            has_gemma = self.docker_manager.check_model_available(instance.url, "gemma3:4b")
            self.instances_status_text.insert(tk.END, f"  gemma3:4b: {'Available' if has_gemma else 'Not available'}\n")

            # Afficher le score de santé
            health_score = instance.get_health_score()
            health_status = "Good" if health_score > 70 else "Fair" if health_score > 40 else "Poor"
            self.instances_status_text.insert(tk.END, f"  Health Score: {health_score:.1f} ({health_status})\n")
            
            # Indiquer si l'instance est surchargée
            if instance.is_overloaded():
                self.instances_status_text.insert(tk.END, f"  STATUS: OVERLOADED\n")
            
            self.instances_status_text.insert(tk.END, "\n")
    
    def preload_model_all_instances(self):
        """Précharger le modèle sur toutes les instances"""
        model = self.model_var.get()
        if not model:
            messagebox.showerror("Erreur", "Veuillez sélectionner un modèle")
            return
        
        # Mettre à jour le processeur avec les paramètres actuels
        self.update_processor()
        
        # Afficher un message dans les logs
        self.log_text.insert(tk.END, f"Préchargement du modèle {model} sur toutes les instances...\n")
        self.log_text.see(tk.END)
        
        # Précharger le modèle dans un thread séparé
        def load_thread():
            success = self.processor.ollama_client.load_model(model)
            self.root.after(0, lambda: self.log_text.insert(tk.END, 
                f"Modèle {model} {'préchargé avec succès' if success else 'échec du préchargement'} sur les instances\n"))
            self.root.after(0, lambda: self.log_text.see(tk.END))
            self.root.after(0, self.update_instances_status)
        
        threading.Thread(target=load_thread, daemon=True).start()

    def reset_instance_stats(self):
        """Réinitialiser les statistiques des instances Ollama"""
        if not self.processor:
            self.update_processor()
        
        # Réinitialiser les statistiques dans un thread séparé
        def reset_thread():
            self.processor.ollama_client.reset_instance_stats()
            self.root.after(0, lambda: self.log_text.insert(tk.END, "Instance statistics reset\n"))
            self.root.after(0, lambda: self.log_text.see(tk.END))
            self.root.after(0, self.update_instances_status)
        
        threading.Thread(target=reset_thread, daemon=True).start()
    
    def create_containers(self):
        """Créer plusieurs conteneurs Ollama"""
        if not self.docker_manager.docker_available:
            messagebox.showerror("Erreur", "Docker n'est pas disponible sur ce système")
            return
        
        base_name = self.docker_base_name_var.get()
        start_port = self.docker_start_port_var.get()
        count = self.docker_container_count_var.get()
        use_network = self.use_docker_network_var.get()
        
        if not base_name:
            messagebox.showerror("Erreur", "Veuillez spécifier un nom de base pour les conteneurs")
            return
        
        # Créer les conteneurs dans un thread séparé
        def create_thread():
            self.log_text.insert(tk.END, f"Création de {count} conteneurs Ollama...\n")
            if use_network:
                self.log_text.insert(tk.END, f"Utilisation du réseau Docker 'ollama-network'\n")
            self.log_text.see(tk.END)
            
            results = self.docker_manager.create_multiple_containers(base_name, start_port, count, use_network=use_network)
            
            # Afficher les résultats
            for result in results:
                status = "créé avec succès" if result["success"] else "échec de création"
                self.log_text.insert(tk.END, f"Conteneur {result['name']} (port {result['port']}): {status}\n")
                if not result["success"]:
                    self.log_text.insert(tk.END, f"  Erreur: {result['message']}\n")
            
            self.log_text.see(tk.END)
            
            # Mettre à jour la liste des conteneurs
            self.root.after(0, self.refresh_containers)
            
            # Mettre à jour la liste des instances si l'option est activée
            if self.use_local_ollama_var.get():
                self.root.after(0, self.launch_ollama_instances)
        
        threading.Thread(target=create_thread, daemon=True).start()
    
    def refresh_containers(self):
        """Rafraîchir la liste des conteneurs"""
        # Effacer la liste actuelle
        for item in self.containers_tree.get_children():
            self.containers_tree.delete(item)
        
        # Récupérer la liste des conteneurs
        containers = self.docker_manager.list_ollama_containers()
        
        # Ajouter les conteneurs à la liste
        for container in containers:
            status = "Running" if container["is_running"] else "Stopped"
            self.containers_tree.insert("", "end", values=(
                container["name"],
                status,
                container["port"],
                container["id"]
            ))
    
    def show_container_menu(self, event):
        """Afficher le menu contextuel pour les conteneurs"""
        # Sélectionner l'élément sous le curseur
        item = self.containers_tree.identify_row(event.y)
        if item:
            self.containers_tree.selection_set(item)
            self.container_menu.post(event.x_root, event.y_root)
    
    def container_double_click(self, event):
        """Gérer le double-clic sur un conteneur"""
        item = self.containers_tree.identify_row(event.y)
        if item:
            # Récupérer les valeurs du conteneur
            values = self.containers_tree.item(item, "values")
            status = values[1]
            
            # Démarrer ou arrêter le conteneur selon son état
            if status == "Running":
                self.stop_container()
            else:
                self.start_container()
    
    def get_selected_container(self):
        """Récupérer le conteneur sélectionné"""
        selection = self.containers_tree.selection()
        if not selection:
            messagebox.showerror("Erreur", "Veuillez sélectionner un conteneur")
            return None
        
        # Récupérer les valeurs du conteneur
        values = self.containers_tree.item(selection[0], "values")
        container_id = values[3]
        
        return {
            "id": container_id,
            "name": values[0],
            "status": values[1],
            "port": values[2]
        }
    
    def start_container(self, container_id):
        """Start a Docker container"""
        success = self.docker_manager.start_container(container_id)
        if success:
            messagebox.showinfo("Succès", "Le conteneur a été démarré avec succès")
            self.refresh_container_list()
        else:
            messagebox.showerror("Erreur", "Impossible de démarrer le conteneur")
    
    def stop_container(self, container_id):
        """Stop a Docker container"""
        success = self.docker_manager.stop_container(container_id)
        if success:
            messagebox.showinfo("Succès", "Le conteneur a été arrêté avec succès")
            self.refresh_container_list()
        else:
            messagebox.showerror("Erreur", "Impossible d'arrêter le conteneur")
    
    def remove_container(self, container_id):
        """Remove a Docker container"""
        if messagebox.askyesno("Confirmation",
                             "Êtes-vous sûr de vouloir supprimer ce conteneur ?"):
            success = self.docker_manager.remove_container(container_id, force=True)
            if success:
                messagebox.showinfo("Succès", "Le conteneur a été supprimé avec succès")
                self.refresh_container_list()
            else:
                messagebox.showerror("Erreur", "Impossible de supprimer le conteneur")
    
    def check_container_api(self):
        """Vérifier l'API du conteneur sélectionné"""
        container = self.get_selected_container()
        if not container:
            return
        
        # Vérifier l'API dans un thread séparé
        def check_thread():
            url = f"http://localhost:{container['port']}"
            is_available = self.docker_manager.check_ollama_api(url)
            
            if is_available:
                self.log_text.insert(tk.END, f"API Ollama disponible sur {url}\n")
                
                # Vérifier si gemma3:4b est disponible
                has_gemma = self.docker_manager.check_model_available(url, "gemma3:4b")
                self.log_text.insert(tk.END, f"Modèle gemma3:4b: {'disponible' if has_gemma else 'non disponible'} sur {url}\n")
            else:
                self.log_text.insert(tk.END, f"API Ollama non disponible sur {url}\n")
            
            self.log_text.see(tk.END)
        
        threading.Thread(target=check_thread, daemon=True).start()
    
    def pull_model_to_container(self, model_name=None):
        """Télécharger un modèle sur le conteneur sélectionné"""
        container = self.get_selected_container()
        if not container:
            return
        
        if container["status"] != "Running":
            messagebox.showerror("Erreur", f"Le conteneur {container['name']} n'est pas en cours d'exécution")
            return
        
        # Utiliser le modèle spécifié ou celui sélectionné dans l'interface
        if not model_name:
            model_name = self.model_var.get()
        
        if not model_name:
            messagebox.showerror("Erreur", "Veuillez spécifier un modèle")
            return
        
        # Télécharger le modèle dans un thread séparé
        def pull_thread():
            url = f"http://localhost:{container['port']}"
            self.log_text.insert(tk.END, f"Téléchargement du modèle {model_name} sur {url}...\n")
            self.log_text.see(tk.END)
            
            success, message = self.docker_manager.pull_model(url, model_name)
            
            if success:
                self.log_text.insert(tk.END, f"Modèle {model_name} téléchargé avec succès sur {url}\n")
            else:
                self.log_text.insert(tk.END, f"Erreur lors du téléchargement du modèle {model_name} sur {url}: {message}\n")
            
            self.log_text.see(tk.END)
            
            # Mettre à jour l'état des instances
            self.root.after(0, self.update_instances_status)
        
        threading.Thread(target=pull_thread, daemon=True).start()
    
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, directory)
    
    def refresh_models(self):
        if self.processor:
            models = self.processor.ollama_client.list_models()
            model_names = [model.get('name', '') for model in models]
            self.model_combo['values'] = model_names
            
            # Log models
            self.log_text.insert(tk.END, f"Available models: {', '.join(model_names)}\n")
            self.log_text.see(tk.END)
    
    def preload_model(self):
        """Précharge le modèle sélectionné"""
        model = self.model_var.get()
        if not model:
            messagebox.showerror("Erreur", "Veuillez sélectionner un modèle")
            return
        
        # Mettre à jour le processeur avec les paramètres actuels
        self.update_processor()
        
        # Afficher un message dans les logs
        self.log_text.insert(tk.END, f"Préchargement du modèle {model}...\n")
        self.log_text.see(tk.END)
        
        # Précharger le modèle dans un thread séparé
        def load_thread():
            success = self.processor.ollama_client.load_model(model)
            self.root.after(0, lambda: self.log_text.insert(tk.END, 
                f"Modèle {model} {'préchargé avec succès' if success else 'échec du préchargement'}\n"))
            self.root.after(0, lambda: self.log_text.see(tk.END))
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def clear_logs(self):
        """Effacer les logs de l'interface"""
        self.log_text.delete(1.0, tk.END)
        self.displayed_logs.clear()
        if self.processor:
            self.processor.logs.clear()
    
    def start_processing(self):
        directory = self.dir_entry.get()
        if not directory:
            messagebox.showerror("Error", "Please select a directory")
            return
        
        if not os.path.isdir(directory):
            messagebox.showerror("Error", "Selected path is not a directory")
            return
        
        # Update processor with current settings
        self.update_processor()
        
        # Clear logs and reset displayed logs tracking
        self.clear_logs()
        
        # Set processing state
        self.is_processing = True
        
        # Start processing in a separate thread
        self.process_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=self.process_directory, args=(directory,), daemon=True).start()

    def toggle_pause(self):
        """Mettre en pause ou reprendre le traitement"""
        if not hasattr(self, 'processor') or self.processor is None:
            return
        
        if self.processor.is_paused():
            self.processor.resume_processing()
            self.pause_btn.config(text="Pause")
            self.log_text.insert(tk.END, "Traitement repris\n")
            self.log_text.see(tk.END)
        else:
            self.processor.pause_processing()
            self.pause_btn.config(text="Reprendre")
            self.log_text.insert(tk.END, "Traitement mis en pause\n")
            self.log_text.see(tk.END)
    
    def process_directory(self, directory):
        """Traiter un répertoire d'images"""
        try:
            # Configurer un timer pour forcer la mise à jour de la progression toutes les secondes
            def schedule_update():
                if self.is_processing:
                    self.force_update_progress()
                    self.update_timer = self.root.after(1000, schedule_update)
        
        # Démarrer le timer de mise à jour
            self.update_timer = self.root.after(1000, schedule_update)
        
        # Traiter le répertoire
            self.processor.process_directory(directory, recursive=self.recursive_var.get())
        
        # Arrêter le timer de mise à jour
            if self.update_timer:
                self.root.after_cancel(self.update_timer)
                self.update_timer = None
            
        # Forcer une dernière mise à jour
            self.force_update_progress()
        
        # Ajouter un message de fin de traitement
            self.log_text.insert(tk.END, "--- Processing completed ---\n")
            self.log_text.see(tk.END)
        finally:
        # Marquer la fin du traitement
            self.is_processing = False
        
        # Réinitialiser l'état de pause
            if self.processor and self.processor.is_paused():
                self.processor.resume_processing()
            
        # Re-enable buttons
            self.root.after(0, lambda: self.process_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.pause_btn.config(state=tk.DISABLED, text="Pause"))
            self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))
    
    def stop_processing(self):
        if self.processor:
            self.processor.stop_processing()
            # Arrêter le timer de mise à jour
            if self.update_timer:
                self.root.after_cancel(self.update_timer)
                self.update_timer = None
    
    def clear_cache(self):
        if self.processor:
            if self.processor.clear_cache():
                messagebox.showinfo("Success", "Cache cleared successfully")
            else:
                messagebox.showerror("Error", "Failed to clear cache")
    
    def force_update_progress(self):
        """Force la mise à jour de la barre de progression"""
        if self.processor:
            progress = self.processor.get_progress()
            self.progress_var.set(progress["progress"])
            self.status_label.config(text=progress["status"].capitalize())
            images_text = f"{progress['processed'] + progress['skipped'] + progress['failed']}/{progress['total']} (Processed: {progress['processed']}, Skipped: {progress['skipped']}, Failed: {progress['failed']})"
            self.images_label.config(text=images_text)
            time_text = f"{progress['timeElapsed']} / {progress['timeRemaining']}"
            self.time_label.config(text=time_text)
            
            # Mettre à jour les logs sans duplication
            self.update_logs(progress["logs"])
            
            # Mettre à jour les statistiques des instances
            self.update_instances_stats()
            
            # Forcer la mise à jour de l'interface
            self.root.update_idletasks()
    
    def update_logs(self, logs):
        """Mettre à jour les logs sans duplication"""
        for log in logs:
            if log and log not in self.displayed_logs:
                self.log_text.insert(tk.END, log + "\n")
                self.displayed_logs.add(log)
        
        # Limiter la taille de l'ensemble des logs affichés
        if len(self.displayed_logs) > 1000:
            # Garder seulement les 500 derniers logs
            self.displayed_logs = set(list(self.displayed_logs)[-500:])
        
        # Défiler vers le bas
        self.log_text.see(tk.END)
    
    def update_instances_stats(self):
        """Mettre à jour les statistiques des instances"""
        if not self.processor or not hasattr(self.processor, 'ollama_client'):
            return
        
        self.instances_stats_text.delete(1.0, tk.END)
        
        for i, instance in enumerate(self.processor.ollama_client.instances):
            if instance.is_available:
                self.instances_stats_text.insert(tk.END, f"Instance {i+1}: {instance.url}\n")
                self.instances_stats_text.insert(tk.END, f"  Active: {instance.active_requests}\n")
                self.instances_stats_text.insert(tk.END, f"  Total: {instance.total_requests}\n")
                
                if instance.total_requests > 0:
                    avg_time = instance.get_average_response_time()
                    success_rate = instance.get_success_rate()
                    self.instances_stats_text.insert(tk.END, f"  Avg Time: {avg_time:.2f}s\n")
                    self.instances_stats_text.insert(tk.END, f"  Success: {success_rate:.1f}%\n")
                
                self.instances_stats_text.insert(tk.END, "\n")
    
    def monitor_resources(self):
        """Surveiller l'utilisation des ressources système"""
        while True:
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent()
                
                # Memory usage
                memory_info = psutil.virtual_memory()
                memory_used_mb = memory_info.used / (1024 * 1024)
                
                # Find Ollama process
                ollama_process = None
                for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                    if 'ollama' in proc.info['name'].lower():
                        ollama_process = proc
                        break
                
                # Active threads
                active_threads = threading.active_count()
                
                # Update UI on main thread
                self.root.after(0, lambda: self.cpu_label.config(text=f"{cpu_percent:.1f}%"))
                self.root.after(0, lambda: self.memory_label.config(text=f"{memory_used_mb:.1f} MB"))
                
                if ollama_process:
                    ollama_memory = ollama_process.memory_info().rss / (1024 * 1024)
                    self.root.after(0, lambda: self.ollama_label.config(text=f"PID: {ollama_process.pid}, Memory: {ollama_memory:.1f} MB"))
                else:
                    self.root.after(0, lambda: self.ollama_label.config(text="Not found"))
                
                self.root.after(0, lambda: self.threads_label.config(text=str(active_threads)))
                
                # Update concurrent requests if processor exists
                if self.processor and hasattr(self.processor, 'ollama_client'):
                    # Compter les requêtes actives sur toutes les instances
                    active_requests = sum(instance.active_requests for instance in self.processor.ollama_client.instances)
                    self.root.after(0, lambda: self.requests_label.config(text=str(active_requests)))
                
                # Update processing statistics if processing
                if self.is_processing and self.processor:
                    progress = self.processor.get_progress()
                    elapsed_time = progress.get("timeElapsed", "00:00:00")
                    
                    # Convert elapsed time to seconds
                    h, m, s = map(int, elapsed_time.split(':'))
                    total_seconds = h * 3600 + m * 60 + s
                    
                    # Calculate images per second
                    processed_total = progress.get("processed", 0) + progress.get("skipped", 0)
                    if total_seconds > 0:
                        ips = processed_total / total_seconds
                        avg_time = total_seconds / processed_total if processed_total > 0 else 0
                        
                        self.root.after(0, lambda: self.ips_label.config(text=f"{ips:.2f}"))
                        self.root.after(0, lambda: self.avg_time_label.config(text=f"{avg_time:.1f} sec"))
                
                # Mettre à jour les statistiques des instances
                if hasattr(self, 'instances_stats_text'):
                    self.root.after(0, self.update_instances_stats)
            except Exception as e:
                print(f"Error monitoring resources: {str(e)}")
            
            # Update every 2 seconds
            time.sleep(2)
    
    def update_progress(self):
        """Thread pour mettre à jour la progression en temps réel"""
        while True:
            try:
                # Ne mettre à jour que si nous sommes en cours de traitement
                # et que le timer de mise à jour forcée n'est pas actif
                if self.processor and self.is_processing and not self.update_timer:
                    progress = self.processor.get_progress()
                    
                    # Mettre à jour la barre de progression sur le thread principal
                    self.root.after(0, lambda p=progress["progress"]: self.progress_var.set(p))
                    
                    # Mettre à jour le statut sur le thread principal
                    self.root.after(0, lambda s=progress["status"].capitalize(): self.status_label.config(text=s))
                    
                    # Mettre à jour le compteur d'images sur le thread principal
                    images_text = f"{progress['processed'] + progress['skipped'] + progress['failed']}/{progress['total']} (Processed: {progress['processed']}, Skipped: {progress['skipped']}, Failed: {progress['failed']})"
                    self.root.after(0, lambda t=images_text: self.images_label.config(text=t))
                    
                    # Mettre à jour le temps sur le thread principal
                    time_text = f"{progress['timeElapsed']} / {progress['timeRemaining']}"
                    self.root.after(0, lambda t=time_text: self.time_label.config(text=t))
                    
                    # Mettre à jour les logs sur le thread principal
                    self.root.after(0, lambda l=progress["logs"]: self.update_logs(l))
                    
                    # Forcer la mise à jour de l'interface
                    self.root.after(0, self.root.update_idletasks)
            except Exception as e:
                # Éviter que les erreurs ne bloquent la boucle de mise à jour
                print(f"Erreur dans la mise à jour de la progression: {str(e)}")
            
            # Pause courte pour éviter de surcharger le CPU
            time.sleep(0.5)

    # Ajouter les nouvelles méthodes pour gérer le réseau Docker et lancer les instances
    def create_docker_network(self):
        """Créer le réseau Docker pour les instances Ollama"""
        if not self.docker_manager.docker_available:
            messagebox.showerror("Erreur", "Docker n'est pas disponible sur ce système")
            return
        
        # Créer le réseau dans un thread séparé
        def create_thread():
            success, message = self.docker_manager.create_ollama_network()
            
            if success:
                self.log_text.insert(tk.END, f"Réseau Docker créé avec succès: {message}\n")
            else:
                self.log_text.insert(tk.END, f"Erreur lors de la création du réseau Docker: {message}\n")
            
            self.log_text.see(tk.END)
        
        threading.Thread(target=create_thread, daemon=True).start()

    def launch_ollama_instances(self):
        """Lancer les instances Ollama Docker et mettre à jour la configuration"""
        if not self.docker_manager.docker_available:
            messagebox.showerror("Erreur", "Docker n'est pas disponible sur ce système")
            return
        
        # Récupérer la liste des conteneurs
        containers = self.docker_manager.list_ollama_containers()
        running_containers = [c for c in containers if c["is_running"]]
        
        if not running_containers and not self.use_local_ollama_var.get():
            messagebox.showinfo("Information", "Aucun conteneur Ollama en cours d'exécution. Veuillez démarrer au moins un conteneur ou activer l'option 'Utiliser Ollama local'.")
            return
        
        # Construire la liste des URLs des instances
        instance_urls = []
        
        # Ajouter l'instance locale si demandé
        if self.use_local_ollama_var.get():
            instance_urls.append(DEFAULT_OLLAMA_URL)
        
        # Ajouter les instances Docker
        for container in running_containers:
            instance_urls.append(f"http://localhost:{container['port']}")
        
        # Mettre à jour la variable des instances
        self.ollama_instances_var.set(','.join(instance_urls))
        
        # Mettre à jour le processeur
        self.update_processor()
        
        # Afficher un message de confirmation
        self.log_text.insert(tk.END, f"Configuration mise à jour avec {len(instance_urls)} instances Ollama\n")
        self.log_text.see(tk.END)
        
        # Afficher les instances dans les logs
        for url in instance_urls:
            self.log_text.insert(tk.END, f"  - {url}\n")
        
        self.log_text.see(tk.END)

    def create_ollama_containers(self):
        """Create Docker containers for Ollama"""
        containers = self.docker_manager.create_multiple_containers(
            self.docker_base_name_var.get(),
            self.docker_start_port_var.get(),
            self.docker_container_count_var.get(),
            self.use_docker_network_var.get()
        )
        
        success = all(container["success"] for container in containers)
        if success:
            messagebox.showinfo("Succès", 
                              "Conteneurs Ollama créés avec succès.\n" +
                              "Utilisez 'Launch Ollama Instances' pour les configurer.")
            self.refresh_container_list()
        else:
            failed = [c for c in containers if not c["success"]]
            error_msg = "\n".join(f"- {c['name']}: {c['message']}" for c in failed)
            messagebox.showerror("Erreur",
                               f"Erreur lors de la création des conteneurs:\n{error_msg}")
    
    def refresh_container_list(self):
        """Refresh the container list in the treeview"""
        for item in self.containers_tree.get_children():
            self.containers_tree.delete(item)
        
        containers = self.docker_manager.list_ollama_containers()
        for container in containers:
            self.containers_tree.insert("", "end",
                                      iid=container["id"],
                                      text=container["id"][:12],
                                      values=(container["name"],
                                             container["status"],
                                             container["port"],
                                             container["url"]))
    
    def show_container_menu(self, event):
        """Show context menu for container actions"""
        tree = event.widget
        iid = tree.identify_row(event.y)
        if iid:
            tree.selection_set(iid)
            item = tree.selection()[0]
            container_menu = tk.Menu(self.root, tearoff=0)
            
            # Get container status
            values = tree.item(item)["values"]
            is_running = "Up" in values[1]
            
            if is_running:
                container_menu.add_command(label="Stop",
                                         command=lambda: self.stop_container(item))
            else:
                container_menu.add_command(label="Start",
                                         command=lambda: self.start_container(item))
            
            container_menu.add_command(label="Remove",
                                     command=lambda: self.remove_container(item))
            
            container_menu.tk_popup(event.x_root, event.y_root)
    
    def start_container(self, container_id):
        """Start a Docker container"""
        success = self.docker_manager.start_container(container_id)
        if success:
            messagebox.showinfo("Succès", "Le conteneur a été démarré avec succès")
            self.refresh_container_list()
        else:
            messagebox.showerror("Erreur", "Impossible de démarrer le conteneur")
    
    def stop_container(self, container_id):
        """Stop a Docker container"""
        success = self.docker_manager.stop_container(container_id)
        if success:
            messagebox.showinfo("Succès", "Le conteneur a été arrêté avec succès")
            self.refresh_container_list()
        else:
            messagebox.showerror("Erreur", "Impossible d'arrêter le conteneur")
    
    def remove_container(self, container_id):
        """Remove a Docker container"""
        if messagebox.askyesno("Confirmation",
                             "Êtes-vous sûr de vouloir supprimer ce conteneur ?"):
            success = self.docker_manager.remove_container(container_id, force=True)
            if success:
                messagebox.showinfo("Succès", "Le conteneur a été supprimé avec succès")
                self.refresh_container_list()
            else:
                messagebox.showerror("Erreur", "Impossible de supprimer le conteneur")

    def log_message(self, message):
        """Ajouter un message au log"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def configure_text_widget(self, widget):
        """Configure l'apparence d'un widget Text ou ScrolledText"""
        widget.configure(
            background=COLORS['input_bg'],
            foreground=COLORS['fg'],
            insertbackground=COLORS['accent'],
            selectbackground=COLORS['accent'],
            selectforeground=COLORS['bg'],
            relief="sunken",
            borderwidth=2,
            padx=5,
            pady=5,
            font=self.style.fonts['normal']
        )
        # Configurer la scrollbar avec le style rétro
        if hasattr(widget, 'vbar'):
            widget.vbar.configure(
                background=COLORS['button_bg'],
                troughcolor=COLORS['bg'],
                activebackground=COLORS['accent'],
                relief="raised",
                width=12
            )

    def create_styled_title(self, parent, text):
        """Créer un titre stylisé avec effet rétro gaming"""
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill=tk.X, pady=(10, 5))
        
        label = ttk.Label(
            title_frame,
            text=text,
            style='Title.TLabel',
            foreground=COLORS['accent'],
            font=self.style.fonts['title']
        )
        label.pack(anchor=tk.CENTER)
        
        # Ajouter une ligne de séparation stylisée
        separator = ttk.Frame(title_frame, height=2, style='Separator.TFrame')
        separator.pack(fill=tk.X, pady=(2, 5))
        
        return label

    def create_action_button(self, parent, text, command, is_primary=False):
        """Créer un bouton d'action stylisé"""
        btn = ttk.Button(
            parent,
            text=text,
            command=command,
            style='Retro.TButton'
        )
        
        if is_primary:
            btn.configure(style='Primary.TButton')
            
        return btn
