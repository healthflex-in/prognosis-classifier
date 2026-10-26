"""
MongoDB connection utility with optimized timeout and retry settings.
Standardizes MongoDB client creation across the application.
"""

from pymongo import MongoClient
from typing import Optional
import os
import threading

_shared_clients: dict = {}
_shared_lock = threading.Lock()


def create_mongo_client(mongo_uri: Optional[str] = None) -> MongoClient:
    """
    Create a MongoDB client with optimized connection settings.
    
    Args:
        mongo_uri: MongoDB connection string (defaults to MONGO_URI env var)
        
    Returns:
        MongoClient instance with optimized settings
    """
    if mongo_uri is None:
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            raise ValueError("MongoDB URI not provided and MONGO_URI env var not set")
    
    return MongoClient(
        mongo_uri,
        tlsAllowInvalidCertificates=True,
        tlsAllowInvalidHostnames=True,
        # Timeout settings (increased for network issues)
        serverSelectionTimeoutMS=30000,  # 30 seconds to find a server
        connectTimeoutMS=30000,  # 30 seconds to establish connection
        socketTimeoutMS=60000,  # 60 seconds for socket operations
        # Retry settings
        retryWrites=True,
        retryReads=True,
        # Connection pooling
        maxPoolSize=50,
        minPoolSize=10,
        # Heartbeat to keep connection alive
        heartbeatFrequencyMS=10000,  # Check connection every 10 seconds
    )


def get_mongo_db(db_name: Optional[str] = None) -> tuple[MongoClient, any]:
    """
    Get MongoDB database instance.
    
    Args:
        db_name: Database name (defaults to MONGO_DB env var or 'stance-dashboard')
        
    Returns:
        Tuple of (MongoClient, Database)
    """
    if db_name is None:
        db_name = os.getenv("MONGO_DB", "stance-dashboard")

    # One pooled client per URI: building a client per call re-opens the whole
    # TLS connection pool, which dominated first-query latency on every request.
    uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
    with _shared_lock:
        client = _shared_clients.get(uri)
        if client is None:
            client = create_mongo_client()
            _shared_clients[uri] = client
    return client, client[db_name]
