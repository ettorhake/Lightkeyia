import tkinter as tk
from tkinter import ttk
import os
import logging
from tkinter import font
from tkinter.font import Font
import base64

# Configuration du logger
logger = logging.getLogger("LightKeyia")

# Couleurs du thème rétro gaming
COLORS = {
    'bg': '#1a1b26',           # Fond principal sombre
    'fg': '#a9b1d6',           # Texte principal
    'accent': '#7aa2f7',       # Accent bleu néon
    'accent2': '#bb9af7',      # Accent violet
    'success': '#9ece6a',      # Vert néon
    'warning': '#e0af68',      # Orange
    'error': '#f7768e',        # Rouge néon
    'input_bg': '#24283b',     # Fond des champs de saisie
    'button_bg': '#414868',    # Fond des boutons
    'progressbar': '#7aa2f7'   # Barre de progression
}

def load_pixelify_font():
    """Charger la police Pixelify Sans"""
    font_path = os.path.join(os.path.dirname(__file__), 'assets', 'PixelifySans-Regular.ttf')
    bold_font_path = os.path.join(os.path.dirname(__file__), 'assets', 'PixelifySans-Bold.ttf')
    
    try:
        # Créer un objet Font temporaire pour charger la police
        temp_font = Font(family="TkDefaultFont", size=10)
        temp_font.configure(file=font_path)
        
        # Si on arrive ici, la police est chargée avec succès
        return "PixelifySans"
    except Exception as e:
        logger.warning(f"Could not load Pixelify Sans font: {e}")
        return get_system_font()

def get_system_font():
    """Obtenir une police de secours du système"""
    system_fonts = ['Consolas', 'Lucida Console', 'Courier New', 'Terminal']
    for font_name in system_fonts:
        if font_name in font.families():
            return font_name
    return 'TkFixedFont'

def apply_theme(root):
    """Appliquer le thème personnalisé"""
    style = ttk.Style()
    style.theme_create("RetroGaming", parent="alt", settings={
        # Configuration générale
        ".": {
            "configure": {
                "background": COLORS['bg'],
                "foreground": COLORS['fg'],
                "fieldbackground": COLORS['input_bg'],
                "troughcolor": COLORS['input_bg'],
                "selectbackground": COLORS['accent'],
                "selectforeground": COLORS['bg'],
                "borderwidth": 0
            }
        },
        
        # Boutons
        "TButton": {
            "configure": {
                "background": COLORS['button_bg'],
                "foreground": COLORS['fg'],
                "padding": [12, 6],
                "borderwidth": 3,
                "relief": "raised",
                "highlightthickness": 2,
                "highlightcolor": COLORS['accent'],
                "anchor": "center"
            },
            "map": {
                "background": [
                    ("active", COLORS['accent']),
                    ("pressed", COLORS['accent2'])
                ],
                "foreground": [
                    ("active", COLORS['bg']),
                    ("pressed", COLORS['bg'])
                ],
                "relief": [
                    ("pressed", "sunken")
                ]
            }
        },
          # Champs de saisie
        "TEntry": {
            "configure": {
                "fieldbackground": COLORS['input_bg'],
                "foreground": COLORS['fg'],
                "padding": [5, 3],
                "borderwidth": 2,
                "relief": "sunken",
                "highlightthickness": 1,
                "highlightcolor": COLORS['accent']
            }
        },
        
        # Scrollbars
        "Vertical.TScrollbar": {
            "configure": {
                "background": COLORS['button_bg'],
                "troughcolor": COLORS['bg'],
                "borderwidth": 1,
                "relief": "raised"
            },
            "map": {
                "background": [
                    ("active", COLORS['accent']),
                    ("pressed", COLORS['accent2'])
                ]
            }
        },
        
        # Labels
        "TLabel": {
            "configure": {
                "background": COLORS['bg'],
                "foreground": COLORS['fg']
            }
        },
        
        # Frames
        "TFrame": {
            "configure": {
                "background": COLORS['bg']
            }
        },
        
        # LabelFrames
        "TLabelframe": {
            "configure": {
                "background": COLORS['bg'],
                "foreground": COLORS['fg']
            }
        },
        "TLabelframe.Label": {
            "configure": {
                "background": COLORS['bg'],
                "foreground": COLORS['accent']
            }
        },
          # Notebook
        "TNotebook": {
            "configure": {
                "background": COLORS['bg'],
                "tabmargins": [2, 5, 2, 0]
            }
        },
        "TNotebook.Tab": {
            "configure": {
                "padding": [15, 5],
                "background": COLORS['button_bg'],
                "foreground": COLORS['fg'],
                "borderwidth": 2,
                "relief": "raised"
            },
            "map": {
                "background": [
                    ("selected", COLORS['accent']),
                    ("active", COLORS['accent2'])
                ],
                "foreground": [
                    ("selected", COLORS['bg']),
                    ("active", COLORS['bg'])
                ],
                "relief": [
                    ("selected", "sunken"),
                    ("active", "raised")
                ]
            }
        },        # Barres de progression
        "Horizontal.TProgressbar": {
            "configure": {
                "background": COLORS['progressbar'],
                "troughcolor": COLORS['input_bg'],
                "borderwidth": 2,
                "relief": "sunken",
                "thickness": 20  # Barre plus épaisse pour un look plus rétro
            }
        },
        
        # Text widgets
        "Text": {
            "configure": {
                "background": COLORS['input_bg'],
                "foreground": COLORS['fg'],
                "insertbackground": COLORS['accent'],  # Couleur du curseur
                "selectbackground": COLORS['accent'],
                "selectforeground": COLORS['bg'],
                "relief": "sunken",
                "borderwidth": 2,
                "padx": 5,
                "pady": 5
            }
        }
    })
    
    # Appliquer le thème
    style.theme_use("RetroGaming")    # Configurer la fenêtre principale
    root.configure(bg=COLORS['bg'])
    
    # Configurer les polices
    pixel_font = load_pixelify_font()
    style.fonts = {
        'normal': (pixel_font, 10),
        'large': (pixel_font, 12),
        'title': (pixel_font, 16, 'bold'),
        'small': (pixel_font, 9)
    }
    
    # Ajouter un effet de bordure rétro aux widgets
    style.layout('Retro.TButton', [
        ('Button.border', {
            'sticky': 'nswe',
            'border': '2',
            'children': [
                ('Button.padding', {
                    'sticky': 'nswe',
                    'children': [
                        ('Button.label', {'sticky': 'nswe'})
                    ]
                })
            ]
        })
    ])
    
    # Appliquer les polices aux widgets
    style.configure('TLabel', font=style.fonts['normal'])
    style.configure('TButton', font=style.fonts['normal'])
    style.configure('TEntry', font=style.fonts['normal'])
    style.configure('TNotebook.Tab', font=style.fonts['normal'])
    style.configure('Title.TLabel', font=style.fonts['title'])
    
    return style
