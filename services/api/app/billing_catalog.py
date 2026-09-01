from __future__ import annotations

from dataclasses import dataclass

from .config import Settings, get_settings


METER_DOCUMENTS = "documents_active"
METER_STORAGE = "storage_bytes"
METER_DETECTION = "ai_detection_runs"
METER_REWRITE = "ai_rewrite_runs"
METER_LABELS = {
    METER_DOCUMENTS: "在用文稿",
    METER_STORAGE: "文稿存储",
    METER_DETECTION: "AI 风险检测",
    METER_REWRITE: "Agent 改写",
}


@dataclass(frozen=True)
class PlanDefinition:
    key: str
    name: str
    description: str
    entitlements: dict[str, bool]
    quotas: dict[str, int]


def plan_catalog(settings: Settings | None = None) -> dict[str, PlanDefinition]:
    config = settings or get_settings()
    shared = {
        "core_workspace": True,
        "docx_import_export": True,
        "ai_detection": True,
        "agent_rewrite": True,
    }
    return {
        "free": PlanDefinition(
            key="free",
            name="Free",
            description="完整体验写作风险检测、可审阅改写、版本和 DOCX 核心闭环。",
            entitlements={**shared},
            quotas={
                METER_DOCUMENTS: config.billing_free_documents,
                METER_STORAGE: config.billing_free_storage_bytes,
                METER_DETECTION: config.billing_free_detection_runs,
                METER_REWRITE: config.billing_free_rewrite_runs,
            },
        ),
        "pro": PlanDefinition(
            key="pro",
            name="Pro",
            description="为高频写作提供更高文稿、存储、检测和改写额度。",
            entitlements={**shared},
            quotas={
                METER_DOCUMENTS: config.billing_pro_documents,
                METER_STORAGE: config.billing_pro_storage_bytes,
                METER_DETECTION: config.billing_pro_detection_runs,
                METER_REWRITE: config.billing_pro_rewrite_runs,
            },
        ),
    }


def get_plan(plan_key: str, settings: Settings | None = None) -> PlanDefinition:
    return plan_catalog(settings).get(plan_key) or plan_catalog(settings)["free"]
