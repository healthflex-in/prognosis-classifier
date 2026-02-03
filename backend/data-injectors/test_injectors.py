#!/usr/bin/env python3
"""
Test script for data injectors.
Tests both VALD and MongoDB injectors with sample data.
"""

import sys
from pathlib import Path

# Add parent directories to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

# Import directly from local modules
from vald_data_injector import VALDDataInjector
from mongo_reports_injector import MongoReportsInjector


def test_vald_injector(stance_id: str = None):
    """Test VALD data injector."""
    print("=" * 80)
    print("Testing VALD Data Injector")
    print("=" * 80)
    print()
    
    if not stance_id:
        print("⚠️  No stance_id provided. Skipping VALD test.")
        print("   Usage: python test_injectors.py --vald <stance_id>")
        return False
    
    try:
        injector = VALDDataInjector()
        print(f"📊 Loading VALD data for stance_id: {stance_id}")
        
        # Test batch loading
        documents = injector.load_data(stance_id)
        
        if documents:
            print(f"✅ Successfully loaded {len(documents)} document(s)")
            print()
            
            for i, doc in enumerate(documents):
                print(f"--- Document {i+1} ---")
                print(f"Metadata: {doc.metadata}")
                print(f"Content length: {len(doc.page_content)} characters")
                print(f"Content preview:")
                print(doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content)
                print()
            
            injector.close()
            return True
        else:
            print("⚠️  No documents returned. Check if stance_id exists in database.")
            injector.close()
            return False
            
    except Exception as e:
        print(f"❌ Error testing VALD injector: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mongo_injector(patient_id: str = None, stance_id: str = None):
    """Test MongoDB reports injector."""
    print("=" * 80)
    print("Testing MongoDB Reports Injector")
    print("=" * 80)
    print()
    
    if not patient_id:
        print("⚠️  No patient_id provided. Skipping MongoDB test.")
        print("   Usage: python test_injectors.py --mongo <patient_id> [stance_id]")
        return False
    
    try:
        injector = MongoReportsInjector()
        print(f"📋 Loading MongoDB reports for patient_id: {patient_id}")
        if stance_id:
            print(f"   Using stance_id: {stance_id} for VALD data matching")
        print(f"   Filtering for FirstAssessment=true and matching VALD tests...")
        
        # Test batch loading
        documents = injector.load_data(patient_id, stance_id=stance_id, max_days_range=7)
        
        if documents:
            print(f"✅ Successfully loaded {len(documents)} document(s)")
            print()
            
            for i, doc in enumerate(documents):
                doc_type = doc.metadata.get('record_type', 'unknown')
                print(f"--- Document {i+1}: {doc_type} ---")
                print(f"Metadata: {doc.metadata}")
                print(f"Content length: {len(doc.page_content)} characters")
                print(f"Content preview:")
                print(doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content)
                print()
            
            # Verify we got FirstAssessment
            has_first_assessment = any(
                doc.metadata.get('record_type') == 'first_assessment' 
                for doc in documents
            )
            
            if has_first_assessment:
                print("✅ First Assessment document found")
            else:
                print("⚠️  No First Assessment document found (expected at least one)")
            
            # Check for matching VALD tests
            has_vald_tests = any(
                doc.metadata.get('record_type') == 'matching_vald_tests' 
                for doc in documents
            )
            
            if has_vald_tests:
                vald_doc = next((d for d in documents if d.metadata.get('record_type') == 'matching_vald_tests'), None)
                if vald_doc:
                    test_count = vald_doc.metadata.get('test_count', 0)
                    print(f"✅ Matching VALD tests document found ({test_count} test record(s))")
            else:
                print("ℹ️  No matching VALD tests found (this is okay if no VALD tests match the FirstAssessment date)")
            
            injector.close()
            return True
        else:
            print("⚠️  No documents returned. Check if patient_id exists and has FirstAssessment.")
            injector.close()
            return False
            
    except Exception as e:
        print(f"❌ Error testing MongoDB injector: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_streaming(stance_id: str = None, patient_id: str = None):
    """Test streaming functionality."""
    print("=" * 80)
    print("Testing Streaming Functionality")
    print("=" * 80)
    print()
    
    # Test VALD streaming
    if stance_id:
        try:
            print("📊 Testing VALD streaming...")
            injector = VALDDataInjector()
            count = 0
            for doc in injector.load_data_stream(stance_id):
                count += 1
                print(f"   Streamed document {count}: {doc.metadata.get('record_type', 'vald_data')}")
            print(f"✅ VALD streaming: {count} document(s)")
            injector.close()
        except Exception as e:
            print(f"❌ VALD streaming error: {e}")
    
    # Test MongoDB streaming
    if patient_id:
        try:
            print("📋 Testing MongoDB streaming...")
            injector = MongoReportsInjector()
            count = 0
            for doc in injector.load_data_stream(patient_id, stance_id=stance_id):
                count += 1
                print(f"   Streamed document {count}: {doc.metadata.get('record_type', 'unknown')}")
            print(f"✅ MongoDB streaming: {count} document(s)")
            injector.close()
        except Exception as e:
            print(f"❌ MongoDB streaming error: {e}")


def list_sample_patients():
    """List sample patients from MongoDB to help with testing."""
    print("=" * 80)
    print("Listing Sample Patients")
    print("=" * 80)
    print()
    
    try:
        injector = MongoReportsInjector()
        
        # First, diagnose the database structure
        print("🔍 Diagnosing database structure...")
        from pymongo import MongoClient
        import os
        from pathlib import Path
        from dotenv import load_dotenv
        
        # Try backend/.env first, then root .env as fallback
        backend_env = Path(__file__).parent.parent / ".env"
        root_env = Path(__file__).parent.parent.parent / ".env"
        if backend_env.exists():
            load_dotenv(backend_env)
            print(f"✅ Loaded .env from: {backend_env}")
        elif root_env.exists():
            load_dotenv(root_env)
            print(f"✅ Loaded .env from: {root_env}")
        else:
            load_dotenv()
            print("⚠️  Using system environment variables (no .env file found)")
        
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        db_name = os.getenv("MONGO_DB", "stance-dashboard")
        
        client = MongoClient(
            mongo_uri,
            tlsAllowInvalidCertificates=True,
            tlsAllowInvalidHostnames=True
        )
        db = client[db_name]
        
        # List all collections
        collections = db.list_collection_names()
        print(f"📊 Available collections in '{db_name}': {collections}")
        print()
        
        # Check structured-user-reports collection/view
        collection_name = 'structured-user-reports'
        if collection_name in collections:
            collection = db[collection_name]
            total_docs = collection.count_documents({})
            print(f"📋 Collection '{collection_name}': {total_docs} document(s)")
            
            if total_docs > 0:
                # Get a sample document
                sample = collection.find_one()
                if sample:
                    print(f"   Sample document keys: {list(sample.keys())}")
                    print(f"   Sample patient_id: {sample.get('patient_id')}")
                    print(f"   Sample patient_name: {sample.get('patient_name')}")
                    print()
        else:
            print(f"⚠️  Collection '{collection_name}' not found!")
            print(f"   Available collections: {collections}")
            print()
        
        client.close()
        
        # Now try to list patients using the loader
        print("📋 Attempting to list patients using MongoReportsLoader...")
        patients = injector.loader.list_patients(limit=10)
        
        if patients:
            print(f"✅ Found {len(patients)} patient(s):")
            print()
            for i, patient in enumerate(patients, 1):
                print(f"{i}. Patient: {patient.get('patient_name', 'Unknown')}")
                print(f"   ID: {patient.get('_id')}")
                print(f"   Seq No: {patient.get('patient_seq_no', 'N/A')}")
                print(f"   Reports: {patient.get('report_count', 0)}")
                print()
            
            if patients:
                print("💡 Use one of these IDs for testing:")
                print(f"   python test_injectors.py --mongo {patients[0].get('_id')}")
        else:
            print("⚠️  No patients found using list_patients() method.")
            print("   This might mean:")
            print("   - The collection/view is empty")
            print("   - The collection name is different")
            print("   - The query structure doesn't match the data")
            print()
            print("💡 Try running --diagnose-vald to see what collections have data")
        
        injector.close()
    except Exception as e:
        print(f"❌ Error listing patients: {e}")
        import traceback
        traceback.print_exc()


def diagnose_vald_collection():
    """Diagnose the VALD matches collection to understand its structure."""
    print("=" * 80)
    print("Diagnosing VALD Matches Collection")
    print("=" * 80)
    print()
    
    try:
        from pymongo import MongoClient
        import os
        from pathlib import Path
        from dotenv import load_dotenv
        
        # Load environment - try backend/.env first, then root .env
        backend_env = Path(__file__).parent.parent / ".env"
        root_env = Path(__file__).parent.parent.parent / ".env"
        if backend_env.exists():
            load_dotenv(backend_env)
            print(f"✅ Loaded .env from: {backend_env}")
        elif root_env.exists():
            load_dotenv(root_env)
            print(f"✅ Loaded .env from: {root_env}")
        else:
            load_dotenv()
            print("⚠️  Using system environment variables (no .env file found)")
        
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        db_name = os.getenv("MONGO_DB", "stance-dashboard")
        
        client = MongoClient(
            mongo_uri,
            tlsAllowInvalidCertificates=True,
            tlsAllowInvalidHostnames=True
        )
        db = client[db_name]
        collection = db['matches']
        
        # Get sample documents
        print("📊 Sample documents from 'matches' collection:")
        print()
        sample_docs = list(collection.find().limit(3))
        
        if not sample_docs:
            print("⚠️  No documents found in 'matches' collection")
            client.close()
            return
        
        for i, doc in enumerate(sample_docs, 1):
            print(f"--- Sample Document {i} ---")
            # Show all keys
            print(f"Keys: {list(doc.keys())}")
            
            # Check for stance ID fields
            stance_fields = [k for k in doc.keys() if 'stance' in k.lower() or 'id' in k.lower()]
            print(f"Potential ID fields: {stance_fields}")
            
            # Show values for potential stance ID fields
            for field in stance_fields:
                value = doc.get(field)
                if value:
                    print(f"  {field}: {value} (type: {type(value).__name__})")
            
            print()
        
        # Count total documents
        total_count = collection.count_documents({})
        print(f"Total documents in 'matches' collection: {total_count}")
        
        # Try to find unique stance ID values
        print("\n🔍 Checking for stance ID field variations...")
        
        # Try common field names
        field_variations = ['stanceId', 'stance_id', 'stanceID', 'StanceId', 'user_id', 'userId']
        for field in field_variations:
            distinct_values = collection.distinct(field)
            if distinct_values:
                print(f"✅ Found field '{field}' with {len(distinct_values)} unique values")
                print(f"   Sample values: {distinct_values[:5]}")
            else:
                print(f"❌ Field '{field}' not found or empty")
        
        client.close()
        print("\n💡 Use one of the stance ID values above for testing:")
        print("   python test_injectors.py --vald <stance_id>")
        
    except Exception as e:
        print(f"❌ Error diagnosing collection: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main test function."""
    print("\n" + "=" * 80)
    print("Data Injectors Test Suite")
    print("=" * 80)
    print()
    
    # Parse arguments
    args = sys.argv[1:]
    
    if not args or '--help' in args or '-h' in args:
        print("Usage:")
        print("  python test_injectors.py --list                    # List available patients")
        print("  python test_injectors.py --diagnose-vald           # Diagnose VALD collection structure")
        print("  python test_injectors.py --vald <stance_id>        # Test VALD injector")
        print("  python test_injectors.py --mongo <patient_id> [stance_id]  # Test MongoDB injector")
        print("  python test_injectors.py --all <patient_id> <stance_id>  # Test both")
        print()
        print("Examples:")
        print("  python test_injectors.py --list")
        print("  python test_injectors.py --diagnose-vald")
        print("  python test_injectors.py --mongo 507f1f77bcf86cd799439011")
        print("  python test_injectors.py --vald stance_12345")
        print("  python test_injectors.py --all 507f1f77bcf86cd799439011 stance_12345")
        print()
        return
    
    if '--list' in args:
        list_sample_patients()
        return
    
    if '--diagnose-vald' in args:
        diagnose_vald_collection()
        return
    
    # Extract IDs from arguments
    stance_id = None
    patient_id = None
    
    if '--vald' in args:
        idx = args.index('--vald')
        if idx + 1 < len(args):
            stance_id = args[idx + 1]
    
    if '--mongo' in args:
        idx = args.index('--mongo')
        if idx + 1 < len(args):
            patient_id = args[idx + 1]
        if idx + 2 < len(args):
            stance_id = args[idx + 2]
    
    if '--all' in args:
        idx = args.index('--all')
        if idx + 1 < len(args):
            patient_id = args[idx + 1]
        if idx + 2 < len(args):
            stance_id = args[idx + 2]
    
    # Run tests
    results = []
    
    if stance_id:
        results.append(("VALD", test_vald_injector(stance_id)))
    
    if patient_id:
        results.append(("MongoDB", test_mongo_injector(patient_id, stance_id)))
    
    # Test streaming if we have IDs
    if stance_id or patient_id:
        print()
        # Get stance_id from args if not already set
        test_stance_id = stance_id
        if not test_stance_id and patient_id:
            # Try using patient_id as stance_id
            test_stance_id = patient_id
        test_streaming(test_stance_id, patient_id)
    
    # Summary
    print()
    print("=" * 80)
    print("Test Summary")
    print("=" * 80)
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{name}: {status}")
    
    if not results:
        print("⚠️  No tests run. Use --help for usage information.")


if __name__ == "__main__":
    main()
