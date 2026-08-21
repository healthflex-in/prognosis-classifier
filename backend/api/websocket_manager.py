"""
WebSocket manager for real-time communication with frontend.
Handles query processing, agent streaming, and widget updates.
"""

import asyncio
import json
import logging
from typing import Dict, Set, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from pathlib import Path
import sys

# Ensure backend root is on sys.path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_tasks: Dict[str, Set[asyncio.Task]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_tasks[client_id] = set()
        logger.info(f"🔌 WebSocket connected: {client_id}")
    
    def disconnect(self, client_id: str):
        """Remove a WebSocket connection and cancel its tasks."""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        
        # Cancel all tasks for this connection
        if client_id in self.connection_tasks:
            for task in self.connection_tasks[client_id]:
                if not task.done():
                    task.cancel()
            del self.connection_tasks[client_id]
        
        logger.info(f"🔌 WebSocket disconnected: {client_id}")
    
    async def send_message(self, client_id: str, message: Dict[str, Any]):
        """Send a message to a specific client."""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"❌ Failed to send message to {client_id}: {e}")
                self.disconnect(client_id)
    
    async def send_error(self, client_id: str, error: str, request_id: Optional[str] = None):
        """Send an error message to a client."""
        await self.send_message(client_id, {
            "type": "error",
            "request_id": request_id,
            "error": error
        })
    
    async def send_progress(self, client_id: str, step: str, details: str, request_id: Optional[str] = None):
        """Send a progress update to a client."""
        await self.send_message(client_id, {
            "type": "progress",
            "request_id": request_id,
            "step": step,
            "details": details
        })
    
    async def send_widget_result(self, client_id: str, widgets: list, analysis: dict, request_id: Optional[str] = None):
        """Send the final widget result to a client."""
        await self.send_message(client_id, {
            "type": "widget_result",
            "request_id": request_id,
            "widgets": widgets,
            "analysis": analysis
        })
    
    def add_task(self, client_id: str, task: asyncio.Task):
        """Add a task to track for a client connection."""
        if client_id in self.connection_tasks:
            self.connection_tasks[client_id].add(task)


# Global connection manager instance
manager = ConnectionManager()


class StreamingReActAgent:
    """ReAct agent that streams progress updates via WebSocket."""
    
    def __init__(self, client_id: str, request_id: str):
        self.client_id = client_id
        self.request_id = request_id
        
        # Import the ReAct agent
        from LLM.query.proper_react_agent import ProperReActQueryAgent
        self.agent = ProperReActQueryAgent()
        
        # Import direct data access functions to avoid HTTP deadlock
        from api.data_loader import get_all_patients
        self.get_patients = get_all_patients
    
    def _check_patient_count_direct(self, filters: Dict[str, str]) -> str:
        """Check patient count using direct database access instead of HTTP."""
        try:
            patients = self.get_patients()
            
            # Apply filters directly
            filtered_patients = []
            for patient in patients:
                match = True
                
                for key, value in filters.items():
                    if key == "canonical_diagnosis":
                        # Handle comma-separated diagnoses with OR logic
                        diagnoses = [d.strip().lower() for d in value.split(",")]
                        patient_diagnosis = (patient.get("canonicalDiagnosis") or "").lower()
                        if not any(diag in patient_diagnosis for diag in diagnoses):
                            match = False
                            break
                    elif key == "clinical_stage":
                        # Handle comma-separated stages with OR logic
                        stages = [s.strip() for s in value.split(",")]
                        patient_stage = patient.get("clinicalStage") or ""
                        if patient_stage not in stages:
                            match = False
                            break
                    elif key == "primary_joint":
                        patient_joint = patient.get("primaryJoint") or ""
                        if patient_joint.lower() != value.lower():
                            match = False
                            break
                    elif key == "functional_region":
                        patient_region = patient.get("functionalRegion") or ""
                        if patient_region.lower() != value.lower():
                            match = False
                            break
                
                if match:
                    filtered_patients.append(patient)
            
            return f"Found {len(filtered_patients)} patients matching criteria: {filters}"
            
        except Exception as e:
            return f"Error checking patient count: {str(e)}"
    
    def _test_endpoint_direct(self, endpoint: str, params: Dict[str, str]) -> str:
        """Test endpoint logic using direct data access instead of HTTP."""
        try:
            if endpoint == "/api/stats/diagnosis":
                # Get diagnosis distribution
                patients = self.get_patients()
                
                # Apply filters
                filtered_patients = []
                for patient in patients:
                    match = True
                    
                    for key, value in params.items():
                        if key == "canonical_diagnosis":
                            diagnoses = [d.strip().lower() for d in value.split(",")]
                            patient_diagnosis = (patient.get("canonicalDiagnosis") or "").lower()
                            if not any(diag in patient_diagnosis for diag in diagnoses):
                                match = False
                                break
                        elif key == "clinical_stage":
                            stages = [s.strip() for s in value.split(",")]
                            patient_stage = patient.get("clinicalStage") or ""
                            if patient_stage not in stages:
                                match = False
                                break
                    
                    if match:
                        filtered_patients.append(patient)
                
                # Count by diagnosis
                diagnosis_counts = {}
                for patient in filtered_patients:
                    diagnosis = patient.get("canonicalDiagnosis") or "Unknown"
                    diagnosis_counts[diagnosis] = diagnosis_counts.get(diagnosis, 0) + 1
                
                return f"Diagnosis distribution: {diagnosis_counts} (total: {len(filtered_patients)} patients)"
            
            return f"Direct endpoint test not implemented for {endpoint}"
            
        except Exception as e:
            return f"Error testing endpoint: {str(e)}"
    async def process_query_streaming(self, query: str):
        """Process a query with streaming progress updates."""
        try:
            await manager.send_progress(
                self.client_id, 
                "initializing", 
                "Starting ReAct reasoning agent...",
                self.request_id
            )
            
            # Step 1: Initial reasoning
            await manager.send_progress(
                self.client_id,
                "reasoning",
                f"Analyzing query: '{query}'",
                self.request_id
            )
            
            # Extract basic intent and entities
            query_lower = query.lower()
            
            # Determine intent
            if any(chart in query_lower for chart in ["chart", "graph", "pie", "bar", "distribution", "breakdown"]):
                intent = "show_distribution"
                chart_type = "pie" if "pie" in query_lower else "bar"
                await manager.send_progress(
                    self.client_id,
                    "intent_detected",
                    f"Intent: {intent} with {chart_type} chart",
                    self.request_id
                )
            else:
                intent = "show_patients"
                chart_type = "table"
                await manager.send_progress(
                    self.client_id,
                    "intent_detected", 
                    f"Intent: {intent} with patient table",
                    self.request_id
                )
            
            # Step 2: Extract filters
            await manager.send_progress(
                self.client_id,
                "extracting_filters",
                "Extracting conditions and filters from query...",
                self.request_id
            )
            
            entities = []
            filters = {}
            
            # Extract diagnoses
            if any(pain in query_lower for pain in ["knee pain", "shoulder pain", "hip pain"]):
                entities.append("diagnosis")
                diagnoses = []
                if "knee pain" in query_lower or "knee" in query_lower:
                    diagnoses.append("knee pain")
                if "shoulder pain" in query_lower or "shoulder" in query_lower:
                    diagnoses.append("shoulder pain")
                if "hip pain" in query_lower or "hip" in query_lower:
                    diagnoses.append("hip pain")
                if diagnoses:
                    filters["canonical_diagnosis"] = ",".join(diagnoses)
                    await manager.send_progress(
                        self.client_id,
                        "filters_extracted",
                        f"Found diagnoses: {', '.join(diagnoses)}",
                        self.request_id
                    )
            
            # Extract clinical stages
            if any(stage in query_lower for stage in ["acute", "subacute", "chronic"]):
                entities.append("clinical_stage")
                stages = []
                if "acute" in query_lower and "subacute" not in query_lower:
                    stages.append("Acute")
                if "subacute" in query_lower:
                    stages.append("Subacute")
                if "chronic" in query_lower:
                    stages.append("Chronic")
                if stages:
                    filters["clinical_stage"] = ",".join(stages)
                    await manager.send_progress(
                        self.client_id,
                        "filters_extracted",
                        f"Found clinical stages: {', '.join(stages)}",
                        self.request_id
                    )
            
            # Step 3: Validate with direct database calls (no HTTP)
            if filters:
                await manager.send_progress(
                    self.client_id,
                    "validating_data",
                    "Checking patient count with database...",
                    self.request_id
                )
                
                try:
                    patient_count = self._check_patient_count_direct(filters)
                    await manager.send_progress(
                        self.client_id,
                        "data_validated",
                        patient_count,
                        self.request_id
                    )
                except Exception as e:
                    await manager.send_progress(
                        self.client_id,
                        "validation_warning",
                        f"Could not validate patient count: {str(e)}",
                        self.request_id
                    )
            
            # Step 4: Test endpoint logic directly (no HTTP)
            if intent == "show_distribution" and filters:
                await manager.send_progress(
                    self.client_id,
                    "testing_endpoint",
                    "Testing data availability with database...",
                    self.request_id
                )
                
                try:
                    endpoint_test = self._test_endpoint_direct("/api/stats/diagnosis", filters)
                    await manager.send_progress(
                        self.client_id,
                        "endpoint_tested",
                        endpoint_test,
                        self.request_id
                    )
                except Exception as e:
                    await manager.send_progress(
                        self.client_id,
                        "endpoint_warning",
                        f"Endpoint test failed: {str(e)}",
                        self.request_id
                    )
            
            # Step 5: Generate widget
            await manager.send_progress(
                self.client_id,
                "generating_widget",
                "Creating widget specification...",
                self.request_id
            )
            
            # Create widget specification directly instead of using full agent
            from LLM.query.proper_react_agent import QueryAnalysis, WidgetSpec, ReActQueryResponse
            
            analysis = QueryAnalysis(
                intent=intent,
                entities=entities or ["unknown"],
                filters=filters,
                chart_type=chart_type,
                reasoning=f"WebSocket ReAct reasoning: {intent} intent detected with entities {entities} and filters {filters}"
            )
            
            # Generate widget based on analysis
            if intent == "show_patients":
                widget = WidgetSpec(
                    id="widget-ws-001",
                    type="patient-table",
                    title="Filtered Patients",
                    endpoint="/api/patients",
                    filters=filters,
                    refresh_interval=60,
                    minW=4,
                    minH=4
                )
            else:
                # Choose best endpoint for distribution
                if "clinical_stage" in filters and "canonical_diagnosis" in filters:
                    endpoint = "/api/stats/diagnosis"
                    title = f"Diagnosis Distribution"
                    if "clinical_stage" in filters:
                        stages = filters["clinical_stage"].replace(",", " & ")
                        title += f" ({stages} Patients)"
                elif "clinical_stage" in filters:
                    endpoint = "/api/stats/clinical-stage"
                    title = "Clinical Stage Distribution"
                else:
                    endpoint = "/api/stats/diagnosis"
                    title = "Diagnosis Distribution"
                
                widget = WidgetSpec(
                    id="widget-ws-001",
                    type=chart_type,
                    title=title,
                    endpoint=endpoint,
                    filters=filters,
                    refresh_interval=60,
                    minW=5 if chart_type == "pie" else 4,
                    minH=5 if chart_type == "pie" else 4
                )
            
            response = ReActQueryResponse(
                analysis=analysis,
                widgets=[widget]
            )
            
            await manager.send_progress(
                self.client_id,
                "widget_generated",
                f"Generated {len(response.widgets)} widget(s)",
                self.request_id
            )
            
            # Send final result
            await manager.send_widget_result(
                self.client_id,
                [w.model_dump() for w in response.widgets],
                response.analysis.model_dump(),
                self.request_id
            )
            
        except Exception as e:
            logger.error(f"❌ Streaming agent error: {e}")
            await manager.send_error(
                self.client_id,
                f"Failed to process query: {str(e)}",
                self.request_id
            )


async def handle_websocket_message(client_id: str, message: Dict[str, Any]):
    """Handle incoming WebSocket messages."""
    try:
        message_type = message.get("type")
        request_id = message.get("request_id")
        
        if message_type == "query_widgets":
            query = message.get("query", "").strip()
            if not query:
                await manager.send_error(client_id, "Query cannot be empty", request_id)
                return
            
            # Create streaming agent and process query
            agent = StreamingReActAgent(client_id, request_id)
            
            # Run the query processing as a background task
            task = asyncio.create_task(agent.process_query_streaming(query))
            manager.add_task(client_id, task)
            
        elif message_type == "refresh_prognosis":
            patient_id = message.get("patient_id")
            if not patient_id:
                await manager.send_error(client_id, "patient_id is required", request_id)
                return

            from .queue_manager import PrognosisQueue
            queue = PrognosisQueue()
            await queue.add_task(patient_id, client_id, request_id)
            await manager.send_progress(client_id, "queued", f"Added patient {patient_id} to prognosis queue", request_id)

        elif message_type == "ping":
            await manager.send_message(client_id, {"type": "pong", "request_id": request_id})
            
        else:
            await manager.send_error(client_id, f"Unknown message type: {message_type}", request_id)
            
    except Exception as e:
        logger.error(f"❌ Error handling WebSocket message: {e}")
        await manager.send_error(client_id, f"Message handling error: {str(e)}")


async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """Main WebSocket endpoint handler."""
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                await handle_websocket_message(client_id, message)
            except json.JSONDecodeError:
                await manager.send_error(client_id, "Invalid JSON message")
            except Exception as e:
                logger.error(f"❌ Error processing message: {e}")
                await manager.send_error(client_id, f"Processing error: {str(e)}")
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"❌ WebSocket error for {client_id}: {e}")
        manager.disconnect(client_id)