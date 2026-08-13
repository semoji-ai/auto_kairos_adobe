"""레이어 분석 — 연출 의도 기반 판단(프롬프트 조립·스키마·사이드카)."""
import json
from pathlib import Path

from backend import imagegen, motion

SCHEMA = Path(__file__).resolve().parents[1] / "backend" / "schemas" / "layer_elements.schema.json"


def test_motion_vocabulary_is_public():
    """분석과 모션 플랜이 같은 어휘 목록을 써야 한다 — 출처는 motion 한 곳."""
    assert isinstance(motion.PRESET_GUIDE, str)
    for name in ("slide_in", "fade_in", "pop", "drift", "bob", "shake",
                 "zoom_emphasis", "exit_fade"):
        assert name in motion.PRESET_GUIDE, name
    for cam in ("slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right"):
        assert cam in motion.CAMERA_GUIDE, cam
    assert motion._PRESET_GUIDE is motion.PRESET_GUIDE      # 기존 사용처 보존


def test_schema_requires_intent_and_english_name():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    item = schema["properties"]["elements"]["items"]
    assert set(item["required"]) == {"name", "name_en", "location", "kind", "reason", "intent"}
    assert item["properties"]["name_en"]["type"] == "string"
    assert item["properties"]["intent"]["type"] == "string"
    assert item["additionalProperties"] is False
