from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_and_active_configuration_have_no_removed_detector_dependency():
    files = [
        ROOT / "services/api/app/config.py",
        ROOT / "services/api/app/providers/detectors.py",
        ROOT / ".env.example",
        ROOT / "apps/web/components/Inspector.tsx",
        ROOT / "apps/web/lib/types.ts",
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in files).lower()
    assert "copyleaks" not in content
    assert "detector_mode=dual" not in content
    assert "fusionstatus" not in content
    assert "provider-agreement" not in content


def test_current_detection_copy_uses_single_provider_risk_language():
    inspector = (ROOT / "apps/web/components/Inspector.tsx").read_text(encoding="utf-8")
    assert "AI 写作风险检测" in inspector
    assert "AI 生成风险" in inspector
    assert "AI 辅助风险" in inspector
    assert "人工写作比例" in inspector
    assert "风险合计" in inspector
    assert "修改前后风险变化" in inspector
    for removed in ("融合风险比例", "Provider 原始范围", "两家一致", "单家命中", "检测结果不一致"):
        assert removed not in inspector
