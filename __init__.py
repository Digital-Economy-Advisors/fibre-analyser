# -*- coding: utf-8 -*-
"""
Fibre Analyzer
QGIS Plugin Initialization
"""
def classFactory(iface):
    """Load FibreAnalyzer class from file fibre_analyzer."""
    from .fibre_analyzer import FibreAnalyzer
    return FibreAnalyzer(iface)