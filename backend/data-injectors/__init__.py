"""
Data Injectors for LangChain
Provides data loaders for VALD and MongoDB clinical reports.
"""

try:
    from .vald_data_injector import VALDDataInjector
    from .mongo_reports_injector import MongoReportsInjector
except ImportError:
    # Fallback for direct imports
    from vald_data_injector import VALDDataInjector
    from mongo_reports_injector import MongoReportsInjector

__all__ = ['VALDDataInjector', 'MongoReportsInjector']
