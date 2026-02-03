#!/usr/bin/env python3
"""
Example usage of data injectors for LangChain-based systems.
Demonstrates how to load and combine VALD and MongoDB data for LLM input.
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


def load_patient_data(patient_id: str, stance_id: str = None):
    """
    Load all patient data using both injectors.
    
    Args:
        patient_id: Patient ID for MongoDB reports
        stance_id: Stance ID for VALD data (if different from patient_id)
    
    Returns:
        Combined list of Document objects
    """
    all_documents = []
    
    # Load VALD data
    if stance_id:
        print(f"📊 Loading VALD data for stance ID: {stance_id}")
        vald_injector = VALDDataInjector()
        try:
            vald_docs = vald_injector.load_data(stance_id)
            all_documents.extend(vald_docs)
            print(f"   ✅ Loaded {len(vald_docs)} VALD document(s)")
        except Exception as e:
            print(f"   ❌ Error loading VALD data: {e}")
        finally:
            vald_injector.close()
    else:
        print("⚠️  No stance_id provided, skipping VALD data")
    
    # Load MongoDB reports (FirstAssessment + matching VALD tests)
    print(f"📋 Loading MongoDB reports for patient ID: {patient_id}")
    mongo_injector = MongoReportsInjector()
    try:
        mongo_docs = mongo_injector.load_data(patient_id, stance_id=stance_id, max_days_range=7)
        all_documents.extend(mongo_docs)
        print(f"   ✅ Loaded {len(mongo_docs)} MongoDB document(s)")
        
        # Show document types
        for doc in mongo_docs:
            print(f"      - {doc.metadata.get('record_type')}")
    except Exception as e:
        print(f"   ❌ Error loading MongoDB data: {e}")
    finally:
        mongo_injector.close()
    
    return all_documents


def prepare_llm_context(documents):
    """
    Prepare documents for LLM input.
    
    Args:
        documents: List of Document objects
    
    Returns:
        Formatted context string
    """
    context_parts = []
    
    for i, doc in enumerate(documents):
        doc_type = doc.metadata.get('record_type', 'unknown')
        source = doc.metadata.get('source', 'unknown')
        
        context_parts.append(f"=== Document {i+1}: {doc_type} (from {source}) ===")
        context_parts.append(doc.page_content)
        context_parts.append("")  # Empty line between documents
    
    return "\n".join(context_parts)


def main():
    """Example main function."""
    if len(sys.argv) < 2:
        print("Usage: python example_usage.py <patient_id> [stance_id]")
        print("\nExample:")
        print("  python example_usage.py 507f1f77bcf86cd799439011 stance_12345")
        sys.exit(1)
    
    patient_id = sys.argv[1]
    stance_id = sys.argv[2] if len(sys.argv) > 2 else patient_id
    
    print("=" * 80)
    print("Data Injector Example")
    print("=" * 80)
    print()
    
    # Load all data
    documents = load_patient_data(patient_id, stance_id)
    
    if not documents:
        print("\n❌ No documents loaded. Check patient_id and stance_id.")
        return
    
    print(f"\n✅ Total documents loaded: {len(documents)}")
    print()
    
    # Prepare context for LLM
    context = prepare_llm_context(documents)
    
    # Show summary
    print("=" * 80)
    print("Document Summary")
    print("=" * 80)
    for i, doc in enumerate(documents):
        metadata = doc.metadata
        print(f"\nDocument {i+1}:")
        print(f"  Type: {metadata.get('record_type', 'N/A')}")
        print(f"  Source: {metadata.get('source', 'N/A')}")
        print(f"  Patient: {metadata.get('patient_name', metadata.get('name', 'N/A'))}")
        print(f"  Content length: {len(doc.page_content)} characters")
        print(f"  Preview: {doc.page_content[:150]}...")
    
    print("\n" + "=" * 80)
    print("Full Context (for LLM input):")
    print("=" * 80)
    print(context[:1000] + "..." if len(context) > 1000 else context)
    
    # Example: Save to file for inspection
    output_file = f"patient_data_{patient_id}.txt"
    with open(output_file, 'w') as f:
        f.write(context)
    print(f"\n💾 Full context saved to: {output_file}")


if __name__ == "__main__":
    main()
