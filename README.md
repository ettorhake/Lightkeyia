# LightKeyia

Une application de bureau open source conçue pour analyser des images avec Ollama et générer automatiquement des mots-clés dans des fichiers XMP. Ce programme a été créé initialement pour faciliter l'organisation et le classement de photos dans Adobe Lightroom en utilisant des mots-clés générés par intelligence artificielle, permettant ainsi de créer facilement des séries thématiques.

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
git clone https://github.com/ettorhake/lightkeyia.git
cd lightkeyia
```

2. Installer les dépendances :
```bash
pip install -r requirements.txt
```

3. S'assurer qu'Ollama est installé et en cours d'exécution

4. Installer le modèle Gemma avec Ollama :
```bash
ollama pull gemma3:4b
```
Note : LightKeyia a été optimisé et testé avec le modèle gemma3:4b qui offre un excellent rapport performance/qualité pour l'analyse d'images.

## Utilisation

### Mode Cloud (Recommandé pour de meilleures performances)

LightKeyia peut utiliser Google Colab pour exécuter Ollama dans le cloud, offrant ainsi de meilleures performances grâce aux GPUs gratuits :

1. Créez un compte sur [ngrok.com](https://ngrok.com) et récupérez votre token d'authentification
2. Ouvrez le notebook [LightKeyia_Cloud.ipynb](https://colab.research.google.com/github/ettorhake/lightkeyia/blob/main/lightkeyia_colab.ipynb) dans Google Colab
3. Dans Colab, configurer vos variables secrètes :
   - Cliquez sur l'icône 🔑 dans le panneau de gauche
   - Ajoutez `NGROK_AUTH_TOKEN` avec votre token ngrok
4. Exécutez les cellules du notebook dans l'ordre
5. Copiez l'URL ngrok générée
6. Lancez LightKeyia en local avec cette URL :
```bash
python main.py --ollama-url https://votre-url-ngrok.ngrok.app
```

### Mode Local

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

### Importation dans Lightroom

1. Une fois que LightKeyia a traité vos images, des fichiers XMP contenant les mots-clés générés sont créés à côté de vos photos
2. Dans Lightroom :
   - Sélectionnez les photos concernées
   - Faites un clic droit et choisissez "Métadonnées > Lire les métadonnées depuis le fichier"
   - Les mots-clés générés par LightKeyia seront alors importés et associés à vos photos
3. Vous pouvez maintenant utiliser ces mots-clés pour :
   - Rechercher des photos spécifiques
   - Créer des collections intelligentes
   - Organiser vos séries thématiques

## Téléchargement de la version compilée (.exe)

Si vous ne souhaitez pas installer Python ou les dépendances, vous pouvez télécharger directement la version Windows compilée de LightKeyia :

- Rendez-vous dans le répertoire `dist` du projet pour récupérer le fichier exécutable `.exe`.
- Double-cliquez sur le fichier `.exe` pour lancer l'application sans installation supplémentaire.

> **Remarque :** Si vous ne trouvez pas le dossier `dist`, il se peut que la version compilée ne soit pas encore disponible. Vous pouvez la générer vous-même avec [PyInstaller](https://www.pyinstaller.org/) ou attendre la prochaine release.

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

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.

## Auteur

Créé par **ettorhake**

Ce projet est open source et les contributions sont les bienvenues ! N'hésitez pas à ouvrir des issues ou proposer des pull requests.
