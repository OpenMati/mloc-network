from __future__ import annotations

"""Pydantic model definitions for normalizing and validating task YAML structure."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


def _to_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


class MetadataModel(BaseModel):
    """Task metadata, allowing extra fields (annotations, labels, etc.)."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Task name, serves as unique identifier prefix.")
    owner: Optional[str] = Field(default=None, description="Task owner, optional.")
    annotations: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary key-value annotations.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        value = _to_str(value)
        if not value:
            raise ValueError("metadata.name must not be empty")
        return value

    @field_validator("owner")
    @classmethod
    def _trim_owner(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = _to_str(value)
        return trimmed or None


class GPUConfig(BaseModel):
    """GPU resource configuration. When defined, count must be provided."""

    model_config = ConfigDict(extra="allow")

    count: int = Field(..., ge=0, description="Number of GPUs, must be non-negative integer.")
    type: Optional[str] = Field(default=None, description="GPU model, optional.")

    @field_validator("type")
    @classmethod
    def _trim_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = _to_str(value)
        return trimmed or None


class HardwareConfig(BaseModel):
    """Hardware resource requirements."""

    model_config = ConfigDict(extra="allow")

    cpu: str = Field(..., description="CPU quota, e.g., '8' or '8c'.")
    memory: str = Field(..., description="Memory quota, e.g., '32Gi'.")
    gpu: Optional[GPUConfig] = Field(default=None, description="Optional GPU configuration.")

    @field_validator("cpu", "memory")
    @classmethod
    def _ensure_non_empty(cls, value: str, field) -> str:  # type: ignore[override]
        trimmed = _to_str(value)
        if not trimmed:
            raise ValueError(f"spec.resources.hardware.{field.field_name} must not be empty")
        return trimmed


class ResourceConfig(BaseModel):
    """Task resource configuration."""

    model_config = ConfigDict(extra="allow")

    replicas: int = Field(default=1, ge=1, description="Number of scheduling replicas, default 1.")
    hardware: HardwareConfig = Field(..., description="Hardware configuration.")


class ParallelConfig(BaseModel):
    """Parallel strategy configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False, description="Whether to enable data parallelism.")
    max_shards: Optional[int] = Field(default=None, ge=1, description="Maximum number of shards.")
    strategy: Optional[str] = Field(default=None, description="Custom strategy name.")


class OutputDestination(BaseModel):
    """Output destination configuration, supports local and http."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(default="local", description="Output type: local or http.")
    path: Optional[str] = Field(default=None, description="Directory or relative path in local mode.")
    url: Optional[str] = Field(default=None, description="Upload target URL in http mode.")
    method: Optional[str] = Field(default="POST", description="HTTP method, default POST.")
    headers: Dict[str, Any] = Field(default_factory=dict, description="HTTP headers configuration.")
    timeoutSec: Optional[float] = Field(default=None, ge=0, description="HTTP request timeout in seconds.")

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        value = _to_str(value)
        return value.lower() or "local"

    @field_validator("method")
    @classmethod
    def _normalize_method(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = _to_str(value)
        return trimmed.upper() or None

    @model_validator(mode="after")
    def _http_constraints(self) -> "OutputDestination":
        if self.type == "http":
            if not self.url:
                raise ValueError("spec.output.destination.url is required when destination.type == 'http'")
        return self


class OutputConfig(BaseModel):
    """Output configuration, including destination and artifact whitelist."""

    model_config = ConfigDict(extra="allow")

    destination: OutputDestination = Field(default_factory=OutputDestination)
    artifacts: List[str] = Field(default_factory=list, description="List of expected output artifact names.")

    @field_validator("artifacts", mode="before")
    @classmethod
    def _coerce_artifacts(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (tuple, set)):
            iterable = list(value)
        else:
            iterable = value
        if not isinstance(iterable, list):
            raise ValueError("spec.output.artifacts must be a list of strings")
        result: List[str] = []
        for item in iterable:
            item_str = _to_str(item)
            if item_str:
                result.append(item_str)
        return result


class TaskSpecModel(BaseModel):
    """Core task specification."""

    model_config = ConfigDict(extra="allow")

    taskType: str = Field(..., description="Task type, e.g., inference, rag, sft.")
    resources: ResourceConfig = Field(..., description="Resource and hardware configuration.")
    output: OutputConfig = Field(default_factory=OutputConfig, description="Output configuration.")
    parallel: ParallelConfig = Field(default_factory=ParallelConfig, description="Parallel configuration.")
    dependsOn: List[str] = Field(default_factory=list, description="List of upstream task IDs.")
    sloSeconds: Optional[float] = Field(default=None, gt=0, description="Target latency (seconds), optional.")
    stages: Optional[List[Dict[str, Any]]] = Field(default=None, description="Linear stage definitions.")
    graph: Optional[Dict[str, Any]] = Field(default=None, description="DAG graph definition.")

    @field_validator("taskType")
    @classmethod
    def _normalize_task_type(cls, value: str) -> str:
        value = _to_str(value)
        if not value:
            raise ValueError("spec.taskType must be a non-empty string")
        return value

    @field_validator("dependsOn", mode="before")
    @classmethod
    def _coerce_depends(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (tuple, set)):
            value = list(value)
        if not isinstance(value, list):
            raise ValueError("spec.dependsOn must be a list")
        result: List[str] = []
        for item in value:
            candidate = _to_str(item)
            if candidate:
                result.append(candidate)
        return result


class TaskDocumentModel(BaseModel):
    """Complete task YAML document model."""

    model_config = ConfigDict(extra="allow")

    apiVersion: str = Field(..., description="API version, e.g., mloc/v1.")
    kind: str = Field(..., description="Task kind.")
    metadata: MetadataModel = Field(..., description="Task metadata.")
    spec: TaskSpecModel = Field(..., description="Task specification.")

    @field_validator("apiVersion", "kind")
    @classmethod
    def _trim_non_empty(cls, value: str, field) -> str:  # type: ignore[override]
        trimmed = _to_str(value)
        if not trimmed:
            raise ValueError(f"{field.field_name} must not be empty")
        return trimmed


def format_validation_error(exc: ValidationError) -> str:
    """Convert Pydantic ValidationError to readable error message."""

    def _format_loc(parts: List[Any]) -> str:
        formatted: List[str] = []
        for part in parts:
            if isinstance(part, int):
                formatted.append(f"[{part}]")
            else:
                formatted.append(str(part))
        loc = ".".join(formatted)
        return loc.replace(".[", "[")

    messages: List[str] = []
    for err in exc.errors():
        loc = _format_loc(list(err.get("loc", ())))
        msg = err.get("msg", "invalid value")
        if loc:
            messages.append(f"{loc}: {msg}")
        else:
            messages.append(msg)
    return "; ".join(messages)

