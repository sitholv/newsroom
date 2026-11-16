# Configuration file for the Sphinx documentation builder.
#
# Built-in configuration values are described in the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'newsroom.settings')
# Autodoc must import models without a running database server.
os.environ.setdefault('NEWSROOM_SQLITE', '1')
django.setup()

# Project information.

project = 'Bay Newsroom'
copyright = '2026, Vusi Sithole'
author = 'Vusi Sithole'

version = '1.0'
release = '1.0'

# Build behaviour.

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
]
autodoc_member_order = 'bysource'
html_title = 'Bay Newsroom documentation'

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

language = 'en'

# HTML output.

html_theme = 'alabaster'
html_static_path = ['_static']
