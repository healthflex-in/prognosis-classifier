#!/usr/bin/env python3
"""
Database Schema Discovery Script
Dynamically discovers database schema, field values, and categories for the query agent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import Counter

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.data_loader import get_all_patients_master_view
from api.models import PatientMasterView


class DatabaseSchemaDiscovery:
    """Discovers database schema and field values dynamically."""
    
    def __init__(self):
        self.patients = get_all_patients_master_view()
        self.schema = {}
        
    def discover_schema(self) -> Dict[str, Any]:
        """Discover the complete database schema and field values."""
        
        if not self.patients:
            return {"error": "No patients found in database"}
        
        schema = {
            "total_patients": len(self.patients),
            "fields": {},
            "available_endpoints": [
                "/api/patients",
                "/api/stats/diagnosis", 
                "/api/stats/clinical-stage",
                "/api/stats/pain-interference",
                "/api/stats/activity-profile",
                "/api/stats/occupation",
                "/api/stats/nprs-distribution",
                "/api/stats/intent",
                "/api/stats/joint-region",
                "/api/matrix/pain-nprs"
            ],
            "filter_parameters": {}
        }
        
        # Analyze each field
        if not self.patients:
            return schema
            
        sample_patient = self.patients[0]
        
        for field_name in sample_patient.model_fields.keys():
            field_info = self._analyze_field(field_name)
            if field_info:
                schema["fields"][field_name] = field_info
                
                # Add to filter parameters if it's a filterable field
                if field_info["is_filterable"]:
                    schema["filter_parameters"][field_name] = {
                        "type": field_info["type"],
                        "values": field_info["unique_values"],
                        "description": field_info["description"]
                    }
        
        return schema
    
    def _analyze_field(self, field_name: str) -> Dict[str, Any]:
        """Analyze a specific field to understand its type and values."""
        
        values = []
        non_null_values = []
        
        for patient in self.patients:
            value = getattr(patient, field_name, None)
            values.append(value)
            
            if value is not None:
                # Handle enum values
                if hasattr(value, 'value'):
                    non_null_values.append(value.value)
                else:
                    non_null_values.append(value)
        
        if not non_null_values:
            return None
            
        # Determine field type and characteristics
        field_info = {
            "total_values": len(values),
            "non_null_count": len(non_null_values),
            "null_count": len(values) - len(non_null_values),
            "null_percentage": round(((len(values) - len(non_null_values)) / len(values)) * 100, 2)
        }
        
        # Analyze value types
        sample_value = non_null_values[0]
        
        if isinstance(sample_value, bool):
            field_info.update({
                "type": "boolean",
                "is_filterable": True,
                "unique_values": list(set(non_null_values)),
                "description": f"Boolean field with {field_info['non_null_count']} non-null values"
            })
            
        elif isinstance(sample_value, (int, float)):
            field_info.update({
                "type": "numeric",
                "is_filterable": False,  # Numeric fields typically not used for exact filtering
                "min_value": min(non_null_values),
                "max_value": max(non_null_values),
                "avg_value": round(sum(non_null_values) / len(non_null_values), 2),
                "description": f"Numeric field ranging from {min(non_null_values)} to {max(non_null_values)}"
            })
            
        elif isinstance(sample_value, str):
            unique_values = list(set(non_null_values))
            value_counts = Counter(non_null_values)
            
            field_info.update({
                "type": "categorical" if len(unique_values) <= 20 else "text",
                "is_filterable": len(unique_values) <= 50,  # Only filterable if not too many unique values
                "unique_count": len(unique_values),
                "unique_values": unique_values,
                "value_distribution": dict(value_counts.most_common(10)),  # Top 10 most common values
                "description": f"Categorical field with {len(unique_values)} unique values"
            })
            
        else:
            field_info.update({
                "type": "unknown",
                "is_filterable": False,
                "description": f"Unknown field type: {type(sample_value)}"
            })
        
        return field_info
    
    def get_field_mappings(self) -> Dict[str, Dict[str, str]]:
        """Get user-friendly mappings for field values."""
        
        mappings = {}
        
        # Key fields that users commonly query
        key_fields = [
            "painInterference",
            "functionalRegion", 
            "occupationCategory",
            "activityProfile",
            "clinicalStage",
            "intentCategory"
        ]
        
        for field_name in key_fields:
            if self.patients and hasattr(self.patients[0], field_name):
                field_info = self._analyze_field(field_name)
                if field_info and field_info["is_filterable"]:
                    mappings[field_name] = {
                        "field_name": field_name,
                        "user_friendly_name": self._get_user_friendly_name(field_name),
                        "values": field_info["unique_values"],
                        "common_aliases": self._get_common_aliases(field_name, field_info["unique_values"])
                    }
        
        return mappings
    
    def _get_user_friendly_name(self, field_name: str) -> str:
        """Convert field name to user-friendly name."""
        
        name_mappings = {
            "painInterference": "Pain Interference",
            "functionalRegion": "Functional Region",
            "occupationCategory": "Occupation Category", 
            "activityProfile": "Activity Profile",
            "clinicalStage": "Clinical Stage",
            "intentCategory": "Intent Category",
            "canonicalDiagnosis": "Diagnosis",
            "primaryJoint": "Primary Joint"
        }
        
        return name_mappings.get(field_name, field_name.replace("_", " ").title())
    
    def _get_common_aliases(self, field_name: str, values: List[str]) -> Dict[str, str]:
        """Get common user aliases for field values."""
        
        aliases = {}
        
        if field_name == "painInterference":
            for value in values:
                if "minimal" in value.lower() or "no" in value.lower():
                    aliases["no interference"] = value
                    aliases["minimal interference"] = value
                elif "activity" in value.lower():
                    aliases["activity interference"] = value
                    aliases["activity only"] = value
                elif "work" in value.lower():
                    aliases["work interference"] = value
                elif "multi" in value.lower():
                    aliases["multiple interference"] = value
                    aliases["multi-domain"] = value
                elif "forced" in value.lower():
                    aliases["forced entry"] = value
                    aliases["surgery"] = value
                    aliases["trauma"] = value
        
        elif field_name == "functionalRegion":
            for value in values:
                if "upper" in value.lower():
                    aliases["upper limb"] = value
                    aliases["arm"] = value
                elif "lower" in value.lower():
                    aliases["lower limb"] = value
                    aliases["leg"] = value
                elif "spine" in value.lower():
                    aliases["back"] = value
                    aliases["spine"] = value
        
        # Add more alias mappings as needed
        
        return aliases


def get_database_schema() -> Dict[str, Any]:
    """Get the current database schema and field mappings."""
    
    try:
        discovery = DatabaseSchemaDiscovery()
        schema = discovery.discover_schema()
        mappings = discovery.get_field_mappings()
        
        return {
            "schema": schema,
            "field_mappings": mappings,
            "timestamp": "2024-02-05",  # Current date
            "status": "success"
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "status": "error"
        }


if __name__ == "__main__":
    # Test the schema discovery
    result = get_database_schema()
    
    if result["status"] == "success":
        print("✅ Database Schema Discovery Complete")
        print(f"📊 Total patients: {result['schema'].get('total_patients', 0)}")
        print(f"🔍 Filterable fields: {len(result['schema'].get('filter_parameters', {}))}")
        
        print("\n🏷️ Available filter parameters:")
        for field, info in result['schema'].get('filter_parameters', {}).items():
            print(f"  - {field}: {info['type']} ({len(info.get('values', []))} values)")
            if info['type'] == 'categorical' and len(info.get('values', [])) <= 10:
                print(f"    Values: {info['values']}")
        
        print("\n🗺️ Field mappings:")
        for field, mapping in result.get('field_mappings', {}).items():
            print(f"  - {mapping['user_friendly_name']}: {len(mapping.get('values', []))} values")
            if mapping.get('common_aliases'):
                print(f"    Aliases: {list(mapping['common_aliases'].keys())}")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")