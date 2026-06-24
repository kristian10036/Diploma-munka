from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    question: str


class MlClassifyRequest(BaseModel):
    frames: list[dict[str, Any]]


class RagDocumentRequest(BaseModel):
    title: str
    content: str
    source: str | None = None
    document_type: str = "text"
    metadata: dict[str, Any] | None = None


class RagRetrieveRequest(BaseModel):
    query: str
    top_k: int | None = None


class RfAgentControlRequest(BaseModel):
    payload: dict[str, Any] | None = None


class RecordingStartRequest(BaseModel):
    recording_id: str | None = None
    session_id: str | None = None
    description: str | None = None


class ReplayStartRequest(BaseModel):
    recording: str
    speed: float = 1.0
    loop: bool = False


class ReplaySeekRequest(BaseModel):
    frame_index: int


class SdrangelTuneRequest(BaseModel):
    center_frequency_hz: int = Field(ge=1, le=100_000_000_000)
    device_set_index: int = Field(default=0, ge=0, le=63)


class SdrangelDeviceSetRequest(BaseModel):
    hardware_type: str = Field(min_length=1, max_length=64)


class SdrangelDemodRequest(BaseModel):
    demodulator: str
    device_set_index: int = Field(default=0, ge=0, le=63)
    channel_index: int | None = Field(default=None, ge=0, le=255)
    offset_hz: int = Field(default=0, ge=-1_000_000_000, le=1_000_000_000)
    audio_sample_rate: int | None = Field(default=None, ge=8_000, le=384_000)
    bandwidth_hz: int | None = Field(default=None, ge=100, le=20_000_000)
    squelch_db: float | None = Field(default=None, ge=-150, le=20)
    audio_device: str | None = Field(default="default", max_length=128)
    volume: float = Field(default=1.0, ge=0.0, le=10.0)


class ViewportRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    mode: Literal["fixed", "sweep"]
    center_frequency_hz: int = Field(gt=0)
    span_hz: int = Field(gt=0)
    maximum_points: int = Field(ge=2)
    desired_rbw_hz: float | None = None


class SdrangelDemodUpdateRequest(BaseModel):
    device_set_index: int = Field(default=0, ge=0, le=63)
    channel_index: int = Field(ge=0, le=255)
    demodulator: str
    frequency_hz: int | None = Field(default=None, ge=1, le=100_000_000_000)
    bandwidth_hz: int | None = Field(default=None, ge=100, le=20_000_000)
    squelch_db: float | None = Field(default=None, ge=-150, le=20)
    volume: float | None = Field(default=None, ge=0.0, le=10.0)
    input_frequency_offset_hz: int | None = Field(default=None, ge=-1_000_000_000, le=1_000_000_000)
    retune_device_center_hz: int | None = Field(default=None, ge=1, le=100_000_000_000)


class SpectrumPoint(BaseModel):
    frequency_mhz: float | None = None
    frequency_hz: int | None = None
    power_dbm: float


class SpectrumMarkerRequest(BaseModel):
    location_id: str | None = None
    measurement_session_id: str | None = None
    recording_id: str | None = None
    frequency_hz: int
    power_dbm: float | None = None
    label: str
    notes: str | None = None
    category: str | None = None
    color: str | None = None
    metadata: dict[str, Any] | None = None


class SpectrumMarkerUpdate(BaseModel):
    location_id: str | None = None
    measurement_session_id: str | None = None
    recording_id: str | None = None
    frequency_hz: int | None = None
    power_dbm: float | None = None
    label: str | None = None
    notes: str | None = None
    category: str | None = None
    color: str | None = None
    metadata: dict[str, Any] | None = None


class KnownSignalRequest(BaseModel):
    location_id: str | None = None
    measurement_session_id: str | None = None
    center_frequency_hz: int
    frequency_tolerance_hz: int
    bandwidth_hz: int | None = None
    expected_power_min_dbm: float | None = None
    expected_power_max_dbm: float | None = None
    modulation: str | None = None
    protocol: str | None = None
    source_type: str | None = None
    label: str
    notes: str | None = None
    status: str = "active"
    suppress_alerts: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] | None = None


class KnownSignalUpdate(BaseModel):
    frequency_tolerance_hz: int | None = None
    bandwidth_hz: int | None = None
    expected_power_min_dbm: float | None = None
    expected_power_max_dbm: float | None = None
    modulation: str | None = None
    protocol: str | None = None
    source_type: str | None = None
    label: str | None = None
    notes: str | None = None
    status: str | None = None
    suppress_alerts: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] | None = None


class KnownSignalMatchRequest(BaseModel):
    center_frequency_hz: int
    bandwidth_hz: int | None = None
    power_dbm: float | None = None
    modulation: str | None = None
    protocol: str | None = None
    source_type: str | None = None
    location_id: str | None = None


class ReferenceCaptureRequest(BaseModel):
    reference_id: str
    location_name: str
    device_name: str | None = None
    source_file: str | None = "live_spectrum_capture"
    rbw_hz: int | None = None
    vbw_hz: int | None = None
    antenna: str | None = None
    downconverter_profile: str | None = None
    points: list[SpectrumPoint]


class ReferenceSetSpectrumPoint(BaseModel):
    frequency_hz: int = Field(ge=1)
    power_dbm: float


class ReferenceSetCaptureRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    reference_key: str = Field(min_length=1, max_length=128)
    location_name: str = Field(min_length=1, max_length=200)
    measurement_session_id: str | None = None
    operator_name: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    spectrum_reference_kind: str = "snapshot"
    spectrum_points: list[ReferenceSetSpectrumPoint]
    spectrum_metadata: dict[str, Any] | None = None
    include_wifi: bool = False
    include_bluetooth: bool = False
    activate: bool = True


class PeakSaveRequest(BaseModel):
    location_name: str
    peak_type: str = "realtime"
    frequency_mhz: float | None = None
    frequency_hz: int | None = None
    power_dbm: float
    session_title: str | None = None
    metadata: dict[str, Any] | None = None


class SessionStartRequest(BaseModel):
    location_name: str
    operator_name: str | None = None
    notes: str | None = None
    environment_description: str | None = None


class MeasurementSourceRequest(BaseModel):
    source_type: str
    source_name: str
    device_name: str | None = None
    adapter_name: str | None = None
    status: str = "configured"
    config: dict[str, Any] | None = None


class DetectionReviewRequest(BaseModel):
    disposition: str
    review_notes: str | None = None
    known_signal_id: str | None = None
    reviewed_by: str | None = None
    include_in_training: bool | None = None


class AlertAcknowledgeRequest(BaseModel):
    operator: str
    note: str | None = None


class AlertResolveRequest(BaseModel):
    operator: str
    note: str | None = None


class DeviceBaselineSaveRequest(BaseModel):
    protocol: str
    location_name: str
    measurement_session_id: str | None = None
    operator: str | None = None
    notes: str | None = None


class DeviceBaselineDeactivateRequest(BaseModel):
    protocol: str
    location_name: str
