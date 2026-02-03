#!/usr/bin/env python3
"""
VALD Data Injector for LangChain
Fetches and transforms VALD data from MongoDB for use as LLM input.
"""

import os
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

# LangChain imports
try:
    from langchain_core.documents import Document
except ImportError:
    # Fallback if langchain not installed
    class Document:
        def __init__(self, page_content: str, metadata: Dict = None):
            self.page_content = page_content
            self.metadata = metadata or {}

# Load environment variables
try:
    from dotenv import load_dotenv
    # Try backend/.env first, then root .env as fallback
    backend_env = Path(__file__).parent.parent / ".env"
    root_env = Path(__file__).parent.parent.parent / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
    elif root_env.exists():
        load_dotenv(root_env)
    else:
        # Try loading from current directory or system env
        load_dotenv()
except ImportError:
    pass

# Import VALD transformer
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from fetch_and_transform_vald import VALDTransformer


class VALDDataInjector:
    """
    LangChain-compatible data injector for VALD performance data.
    Fetches VALD data from MongoDB and converts it to Document format for LLM input.
    """
    
    def __init__(self, mongo_uri: Optional[str] = None, db_name: Optional[str] = None):
        """
        Initialize VALD data injector.
        
        Args:
            mongo_uri: MongoDB connection string (defaults to env var)
            db_name: Database name (defaults to env var or 'stance-dashboard')
        """
        self.transformer = VALDTransformer(mongo_uri=mongo_uri, db_name=db_name)
    
    def load_data(self, stance_id: str) -> List[Document]:
        """
        Load VALD data for a specific patient and convert to LangChain Documents.
        
        Args:
            stance_id: The patient's stance ID
            
        Returns:
            List of Document objects containing VALD data
        """
        # Fetch and transform VALD data
        vald_records = self.transformer.get_vald_data_for_patient(stance_id)
        
        if not vald_records:
            return []
        
        # Convert to LangChain Documents
        documents = []
        
        for record in vald_records:
            # Create a structured JSON representation
            vald_content = {
                'user_id': record.get('user_id'),
                'name': record.get('name'),
                'vald_id': record.get('vald_id'),
                'date_of_birth': record.get('date_of_birth'),
                'sex': record.get('sex'),
                'last_recorded_utc': record.get('last_recorded_utc'),
                'is_active': record.get('is_active'),
                'exercises': record.get('exercises', {})
            }
            
            # Convert to JSON string for LLM input
            content = json.dumps(vald_content, indent=2, default=str)
            
            # Create metadata
            metadata = {
                'source': 'vald_mongodb',
                'stance_id': stance_id,
                'user_id': record.get('user_id'),
                'vald_id': record.get('vald_id'),
                'record_type': 'vald_performance_data',
                'last_recorded': record.get('last_recorded_utc'),
                'is_active': record.get('is_active', False)
            }
            
            documents.append(Document(page_content=content, metadata=metadata))
        
        return documents
    
    def load_data_stream(self, stance_id: str):
        """
        Stream VALD data as Documents (generator).
        
        Args:
            stance_id: The patient's stance ID
            
        Yields:
            Document objects containing VALD data
        """
        vald_records = self.transformer.get_vald_data_for_patient(stance_id)
        
        for record in vald_records:
            vald_content = {
                'user_id': record.get('user_id'),
                'name': record.get('name'),
                'vald_id': record.get('vald_id'),
                'date_of_birth': record.get('date_of_birth'),
                'sex': record.get('sex'),
                'last_recorded_utc': record.get('last_recorded_utc'),
                'is_active': record.get('is_active'),
                'exercises': record.get('exercises', {})
            }
            
            content = json.dumps(vald_content, indent=2, default=str)
            
            metadata = {
                'source': 'vald_mongodb',
                'stance_id': stance_id,
                'user_id': record.get('user_id'),
                'vald_id': record.get('vald_id'),
                'record_type': 'vald_performance_data',
                'last_recorded': record.get('last_recorded_utc'),
                'is_active': record.get('is_active', False)
            }
            
            yield Document(page_content=content, metadata=metadata)
    
    def close(self):
        """Close MongoDB connection."""
        if self.transformer:
            self.transformer.close()


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vald_data_injector.py <stance_id>")
        sys.exit(1)
    
    stance_id = sys.argv[1]
    
    injector = VALDDataInjector()
    documents = injector.load_data(stance_id)
    
    print(f"\n✅ Loaded {len(documents)} VALD documents for stance ID: {stance_id}")
    
    for i, doc in enumerate(documents):
        print(f"\n--- Document {i+1} ---")
        print(f"Metadata: {doc.metadata}")
        print(f"Content preview: {doc.page_content[:200]}...")
    
    injector.close()
