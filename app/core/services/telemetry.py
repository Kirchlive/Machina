"""
Telemetry Service Implementation

Provides observability and tracing capabilities, with optional Langfuse integration.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import logging
from dataclasses import dataclass
from collections import deque
import asyncio
from app.core.di.interfaces import ITelemetry

@dataclass
class Trace:
    """Represents a telemetry trace"""
    trace_id: str
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    result: Any = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None

class TelemetryService(ITelemetry):
    """
    Concrete implementation of ITelemetry
    
    Provides tracing and metrics collection with:
    - In-memory trace storage
    - Metric aggregation
    - Optional external service integration
    """
    
    def __init__(self,
                 max_traces: int = 1000,
                 langfuse_client: Optional[Any] = None,
                 enable_metrics: bool = True):
        """
        Initialize telemetry service
        
        Args:
            max_traces: Maximum number of traces to keep in memory
            langfuse_client: Optional Langfuse client for external tracing
            enable_metrics: Whether to collect metrics
        """
        self._traces: deque = deque(maxlen=max_traces)
        self._active_traces: Dict[str, Trace] = {}
        self._metrics: Dict[str, List[float]] = {}
        self._langfuse = langfuse_client
        self._enable_metrics = enable_metrics
        self._logger = logging.getLogger(__name__)
        self._lock = asyncio.Lock()
    
    async def trace_start(self, trace_name: str, metadata: Dict[str, Any]) -> str:
        """Start a new trace and return trace ID"""
        trace_id = str(uuid.uuid4())
        
        trace = Trace(
            trace_id=trace_id,
            name=trace_name,
            start_time=datetime.utcnow(),
            metadata=metadata or {}
        )
        
        async with self._lock:
            self._active_traces[trace_id] = trace
        
        # Log to Langfuse if available
        if self._langfuse:
            try:
                self._langfuse.trace(
                    id=trace_id,
                    name=trace_name,
                    metadata=metadata
                )
            except Exception as e:
                self._logger.error(f"Failed to start Langfuse trace: {e}")
        
        self._logger.debug(f"Started trace '{trace_name}' with ID: {trace_id}")
        return trace_id
    
    async def trace_end(self, trace_id: str, result: Any = None, error: Optional[str] = None) -> None:
        """End a trace with result or error"""
        async with self._lock:
            trace = self._active_traces.get(trace_id)
            if not trace:
                self._logger.warning(f"Attempted to end unknown trace: {trace_id}")
                return
            
            # Complete the trace
            trace.end_time = datetime.utcnow()
            trace.result = result
            trace.error = error
            
            # Calculate duration
            duration = (trace.end_time - trace.start_time).total_seconds() * 1000
            trace.duration_ms = duration
            
            # Move to completed traces
            self._traces.append(trace)
            del self._active_traces[trace_id]
            
            # Record metric
            if self._enable_metrics:
                await self.log_metric(
                    f"trace.{trace.name}.duration",
                    duration,
                    {"status": "error" if error else "success"}
                )
        
        # Log to Langfuse if available
        if self._langfuse:
            try:
                self._langfuse.trace(
                    id=trace_id,
                    output=result,
                    error=error
                )
            except Exception as e:
                self._logger.error(f"Failed to end Langfuse trace: {e}")
        
        status = "error" if error else "success"
        self._logger.debug(
            f"Ended trace '{trace.name}' ({trace_id}): "
            f"status={status}, duration={trace.duration_ms:.2f}ms"
        )
    
    async def log_metric(self, metric_name: str, value: float, tags: Dict[str, str]) -> None:
        """Log a metric with tags"""
        # Create full metric name with tags
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        full_name = f"{metric_name}{{{tag_str}}}" if tags else metric_name
        
        async with self._lock:
            if full_name not in self._metrics:
                self._metrics[full_name] = []
            self._metrics[full_name].append(value)
        
        # Log to Langfuse if available
        if self._langfuse:
            try:
                self._langfuse.score(
                    name=metric_name,
                    value=value,
                    comment=str(tags)
                )
            except Exception as e:
                self._logger.error(f"Failed to log Langfuse metric: {e}")
    
    async def get_traces(self, 
                        trace_name: Optional[str] = None,
                        limit: int = 100) -> List[Trace]:
        """Get completed traces with optional filtering"""
        async with self._lock:
            if trace_name:
                filtered = [t for t in self._traces if t.name == trace_name]
                return list(filtered)[-limit:]
            else:
                return list(self._traces)[-limit:]
    
    async def get_metrics_summary(self) -> Dict[str, Dict[str, float]]:
        """Get summary statistics for all metrics"""
        async with self._lock:
            summary = {}
            
            for metric_name, values in self._metrics.items():
                if values:
                    summary[metric_name] = {
                        'count': len(values),
                        'sum': sum(values),
                        'avg': sum(values) / len(values),
                        'min': min(values),
                        'max': max(values),
                        'last': values[-1]
                    }
            
            return summary
    
    async def clear_metrics(self) -> None:
        """Clear all metrics data"""
        async with self._lock:
            self._metrics.clear()
            self._logger.info("Metrics cleared")
    
    async def create_span(self, 
                         parent_trace_id: str,
                         span_name: str,
                         metadata: Dict[str, Any]) -> str:
        """Create a span within an existing trace"""
        span_id = str(uuid.uuid4())
        
        # Add span info to metadata
        span_metadata = {
            **metadata,
            'parent_trace_id': parent_trace_id,
            'span_id': span_id
        }
        
        # Start new trace for the span
        return await self.trace_start(f"{span_name} (span)", span_metadata)

class NoOpTelemetryService(ITelemetry):
    """
    No-operation telemetry service for when telemetry is disabled
    """
    
    async def trace_start(self, trace_name: str, metadata: Dict[str, Any]) -> str:
        """No-op trace start"""
        return str(uuid.uuid4())
    
    async def trace_end(self, trace_id: str, result: Any = None, error: Optional[str] = None) -> None:
        """No-op trace end"""
        pass
    
    async def log_metric(self, metric_name: str, value: float, tags: Dict[str, str]) -> None:
        """No-op metric logging"""
        pass