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
    workspace = (ROOT / "apps/web/components/Workspace.tsx").read_text(encoding="utf-8")
    assert "AI 写作风险检测" in inspector
    assert "AI 生成风险" in inspector
    assert "AI 辅助风险" in inspector
    assert "人工写作比例" in inspector
    assert "风险合计" in inspector
    assert "修改前后风险变化" in inspector
    assert "检测时间" in inspector
    assert "真实 Pangram 检测按量计费" in inspector
    assert "编辑和保存不会自动复检" in inspector
    assert "一键降低" in inspector
    assert "不承诺具体分数" in inspector
    assert "保存为可恢复的新版本" in inspector
    assert "Mock 演示模式只生成预览" in inspector
    assert "本轮检测首次修改" in inspector
    assert "一次处理全部带风险标记的段落" in inspector
    assert '!document.patches.some((patch) => patch.status === "accepted")' not in workspace
    for removed in ("融合风险比例", "Provider 原始范围", "两家一致", "单家命中", "检测结果不一致"):
        assert removed not in inspector
