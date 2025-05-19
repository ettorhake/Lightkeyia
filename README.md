# LightKeyia

Une application de bureau pour analyser des images avec Ollama et générer automatiquement des mots-clés dans des fichiers XMP.

## Caractéristiques

- Interface graphique intuitive pour le traitement des images
- Compatible avec les formats standards (JPG, PNG, etc.) et RAW (CR2, NEF, etc.)
- Utilise l'IA via Ollama pour l'analyse d'images
- Support multi-instances Ollama avec équilibrage de charge
- Gestion intégrée des conteneurs Docker
- Mise en cache des résultats pour éviter les analyses redondantes
- Support complet des métadonnées XMP

## Prérequis

- Python 3.x
- Ollama
- Docker (optionnel, pour le mode multi-instances)
- ExifTool (pour l'écriture des métadonnées)
- rawpy (optionnel, pour le traitement des fichiers RAW)

## Installation

1. Cloner le dépôt :
```bash
git clone https://github.com/votre-username/lightkeyia.git
cd lightkeyia
```

2. Installer les dépendances :
```bash
pip install -r requirements.txt
```

3. S'assurer qu'Ollama est installé et en cours d'exécution

## Utilisation

### Mode Interface Graphique

```bash
python main.py
```

### Mode Ligne de Commande

```bash
python main.py --no-gui --directory /chemin/vers/images
```

Options principales :
- `--directory`, `-d` : Répertoire à traiter
- `--model`, `-m` : Modèle Ollama à utiliser (défaut: gemma3:4b)
- `--recursive`, `-r` : Traiter les sous-répertoires
- `--force`, `-f` : Forcer le retraitement (ignorer le cache)

## Configuration

Le fichier `config.py` contient les paramètres principaux de l'application :
- Modèle par défaut
- URL Ollama
- Extensions de fichiers supportées
- Paramètres de traitement par défaut

## Structure du Projet

- `main.py` : Point d'entrée de l'application
- `gui.py` : Interface graphique
- `image_processor.py` : Traitement des images
- `ollama_client.py` : Client Ollama
- `docker_manager.py` : Gestion des conteneurs Docker
- `utils.py` : Fonctions utilitaires
- `config.py` : Configuration globale

## Licence

[À définir]

## Auteurs

- LightKeyia Team
