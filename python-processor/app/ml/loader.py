from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .classifier import RuleBasedRfClassifier

if TYPE_CHECKING:
    from app.config import MlSettings

logger = logging.getLogger(__name__)


class MlUnavailableError(RuntimeError):
    """Raised by classify() when the configured model cannot run inference.

    Callers must surface this as a clear error, not retry with a different
    model - there is no implicit fallback chain between model types.
    """


class _UnavailableClassifier:
    """Placeholder for a configured model branch that cannot run inference yet.

    Mirrors the RuleBasedRfClassifier interface (status/classify) so routers
    can treat every model_type uniformly regardless of which one is active.
    """

    def __init__(
        self, *, model_type: str | None, model_version: str | None, status: str, reason: str
    ) -> None:
        self.model_type = model_type
        self.model_version = model_version
        self._status = status
        self._reason = reason

    def status(self) -> dict[str, Any]:
        return {
            "available": False,
            "status": self._status,
            "model_version": self.model_version,
            "model_type": self.model_type,
            "reason": self._reason,
        }

    def classify(self, frames: list[dict[str, Any]]) -> dict[str, Any]:
        raise MlUnavailableError(
            f"model_type={self.model_type!r} status={self._status!r}: {self._reason}"
        )


def _build_rule() -> RuleBasedRfClassifier:
    return RuleBasedRfClassifier()


def _build_classical() -> _UnavailableClassifier:
    return _UnavailableClassifier(
        model_type="classical_ml",
        model_version="rf_nearest_centroid_v1",
        status="not_trained",
        reason=(
            "no recording-level-separated labeled dataset has been trained for this "
            "model; train with ml/train_classical.py and wire the artifact explicitly"
        ),
    )


def _build_cnn() -> _UnavailableClassifier:
    return _UnavailableClassifier(
        model_type="cnn",
        model_version="rf_small_cnn_v1",
        status="not_trained",
        reason=(
            "no trained CNN checkpoint is bundled with this package; training is "
            "never run automatically (see ml/train_cnn.py)"
        ),
    )


def _build_onnx() -> _UnavailableClassifier:
    return _UnavailableClassifier(
        model_type="onnx",
        model_version="rf_onnx_v1",
        status="model_not_found",
        reason="no ONNX model file or runtime loader is configured for this package",
    )


_MODEL_BUILDERS = {
    "rule": _build_rule,
    "classical": _build_classical,
    "cnn": _build_cnn,
    "onnx": _build_onnx,
}


def describe_all_models() -> list[dict[str, Any]]:
    """Status of every known model_type, independent of which one is active."""
    return [_MODEL_BUILDERS[name]().status() for name in ("rule", "classical", "cnn", "onnx")]


def build_ml_classifier(settings: "MlSettings") -> Any:
    """Select the active classifier from ML_ENABLED/ML_MODEL_TYPE.

    Never silently substitutes a different model on failure: a disabled or
    not-yet-runnable branch reports its own clear status/log instead of
    falling back to the rule baseline.
    """
    if not settings.enabled:
        logger.warning(
            "ml_classifier_disabled",
            extra={"structured": {"configured_model_type": settings.model_type}},
        )
        return _UnavailableClassifier(
            model_type=settings.model_type,
            model_version=None,
            status="disabled",
            reason="ML_ENABLED is false",
        )

    classifier = _MODEL_BUILDERS[settings.model_type]()
    status = classifier.status()
    if status["available"]:
        logger.info(
            "ml_classifier_loaded",
            extra={"structured": {"model_type": settings.model_type}},
        )
    else:
        logger.warning(
            "ml_classifier_unavailable",
            extra={
                "structured": {
                    "model_type": settings.model_type,
                    "status": status["status"],
                }
            },
        )
    return classifier
