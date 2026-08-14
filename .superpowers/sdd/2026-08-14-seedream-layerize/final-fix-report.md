# 최종 검토 수정 보고서 — 레이어 분리/manifest

## 발견1 (Critical) — 실패한 재분리가 기존 레이어를 지움

파일: `backend/imagegen.py`

- `split_scene_to_elements`: `_archive_prev_layers(out_base, sid)` 호출을 `fal_api.layerize(...)` 성공 이후,
  첫 `write_bytes` 이전으로 옮겼다. 또한 `names`(선택된 요소의 `name_en`)가 비어 있으면 layerize 호출 전에
  `fal_api.FalError("분리할 요소 이름 없음 — name_en이 비어 있습니다")`를 먼저 던지도록 했다. 두 변경 모두
  아카이브가 일어나기 전에 실패가 표면화되게 해, 실패한 재분리가 디스크의 기존 레이어를 지우지 못하게 한다.
- `_specs_from_filenames`: 파일명에서 복원한 `name`(언더스코어→공백, `_char` 접미사 제거)을 그대로
  `name_en`에도 채워 넣었다. 사이드카 없는 옛(legacy) 프로젝트도 `regenerate_layer`가 빈 이름 없이
  layerize를 호출할 수 있게 됐다.
- `split_scene_to_elements`: `kinds` 딕셔너리가 비어 있으면(`if kinds:`) `{sid}__kinds.json` 쓰기를
  건너뛰도록 했다 — 매칭이 하나도 안 된 재분리가 기존 kinds.json(자동 bob의 근거)을 `{}`로 덮어쓰지 않는다.

라우팅 경로(`backend/router.py`의 `_do_bg`, split job)는 이 함수를 그대로 통과하므로 별도 수정 없이 함께 고쳐졌다.

### 추가 테스트 (`tests/test_imagegen.py`)
- `test_split_scene_failed_relayerize_preserves_existing_layers` — layerize를 `FalError`로 실패시키고,
  기존 레이어 파일이 그대로 남아 있고 `_prev/`가 생성되지 않았음을 확인.
- `test_regenerate_layer_legacy_sidecar_less_gets_name_en` — 사이드카 없이 PNG 파일명만 있는 프로젝트에서
  `regenerate_layer`가 layerize를 실제로 호출하고(빈 이름 예외 없이) 성공함을 확인.
- `test_kinds_json_not_overwritten_with_empty` — 매칭이 전혀 안 돼 새 `kinds`가 빈 채로 계산될 때
  기존 `kinds.json` 내용이 보존됨을 확인.

## 발견2 (Important) — bbox 좌표계가 씬 이미지 픽셀 좌표계라는 가정

파일: `backend/manifest.py`

- `_scene_layers(proj_dir, layer_rels, sid="", comp_width=None)`에 `comp_width` 매개변수를 추가했다.
  배경(z_index 0) PNG의 실제 폭(`_img_size`)을 읽어 `comp_width`와 다르면
  `scale_factor = comp_width / plate_width`를 계산해 모든 bbox 값(l, t, r, b)에 곱한다.
- `build_manifest`에서 이미 계산돼 있는 `sw`(컴프 폭)를 `_scene_layers` 호출부에 그대로 전달하도록 바꿨다
  (함수 내부에서 재계산하지 않음).

### 추가/수정 테스트 (`tests/test_manifest.py`)
- `test_layer_placement_from_bbox`(기존): 배경판 폭과 컴프 폭이 같은 시나리오로 조정
  (씬에 `imageRef`를 추가해 컴프 폭을 배경판 폭 1536과 일치시킴) — 스케일 보정이 회귀를 일으키지 않도록.
- `test_layer_bbox_scaled_when_plate_smaller_than_comp`(신규) — 배경판 폭 1000, 컴프 폭 2000 시나리오에서
  bbox 좌표가 정확히 2배로 보정됨을 실측값으로 확인.

## 발견3 (Important) — missing/unexpected가 사용자에게 도달하지 않음

파일: `backend/router.py`, `cep/com.autokairos.pd/js/storyboard.js`

- `router.py`의 split-layers job(`_do`): "완료된 레이어" 판정에서 배경(`name == "배경"`)을 제외하도록
  바꿨다. 배경이 아닌 요소가 하나도 완료되지 않았고 `res.get("missing")`이 비어 있지 않으면
  못 만든 요소 이름을 나열한 `RuntimeError`를 던진다. 그 외 전체 실패 경로(첫 에러 메시지 등)는 유지.
- `storyboard.js`의 `splitLayers` 완료 핸들러: `res.missing`/`res.unexpected` 개수를 상태 텍스트에
  이어 붙인다 — `" (못 만든 요소 N개: a, b)"`, `" (요청 외 N개)"`. ES5 스타일(`var`, 화살표 함수/템플릿
  리터럴 없음) 유지.

## 발견4 (Minor) — PIL이 PNG를 못 읽을 때 위치/스케일 누락

파일: `backend/manifest.py`

- `_scene_layers`를 재구성해 `_img_size`가 `None`을 반환하는 경우(placed=False로 남음) `_alpha_foot` 폴백
  경로로 떨어지도록 통일했다. bbox가 있어도 PNG를 못 읽으면 최소한 발밑 피벗은 살아남는다.

## 발견5 (Minor) — 폭이 0 이하인 degenerate bbox

파일: `backend/manifest.py`

- 스케일 보정 후 `(rr - l) <= 0`이면 배치를 건너뛰고(placed=False) `_alpha_foot` 폴백으로 넘어가도록 했다
  (scale: 0 인 투명 레이어를 만들지 않음).

## 발견6 (Minor) — 비수치 bbox가 전체 manifest 빌드를 막음

파일: `backend/manifest.py`

- `l, t, rr, b = [float(v) * scale_factor for v in bbox]`를 `try/except (TypeError, ValueError)`로 감쌌다.
  실패하면 bbox가 없는 것처럼(placed=False → `_alpha_foot` 폴백) 처리한다.

### 추가 테스트 (`tests/test_manifest.py`)
- `test_bbox_non_numeric_degrades_to_no_placement` — bbox에 `"bad"`/`None`/`"x"`/`"y"` 같은 비수치 값을
  넣어도 예외 없이 `position`/`scale`이 빠지고 `_alpha_foot` 값으로 `foot`만 채워짐을 확인.

## 발견7 (Minor) — 삭제된 코드가 남긴 잔여물

파일: `backend/router.py`, `cep/com.autokairos.pd/js/storyboard.js`, `backend/fal_api.py`

- `router.py`의 split-layers job: `AK_LAYER_CONCURRENCY` env 읽기와 그 위의 낡은 주석("충돌 관측됨...")을
  제거했다. `split_scene_to_elements`에 `concurrency` 인자를 더 이상 넘기지 않는다(파라미터 자체가
  함수 내부에서 쓰이지 않음이 docstring에 명시돼 있음). 이미지 생성용 다른 두 endpoint의
  `AK_LAYER_CONCURRENCY` 사용(`/api/generate`류)은 이번 발견의 범위(split job)가 아니라 그대로 뒀다.
- `router.py`의 `_do_bg`: 쓰이지 않는 `names = res.get("remaining_names") or []` 줄과 그에 딸린
  `names=names` 클로저 인자를 제거했다.
- `storyboard.js`의 `regenLayer` 주석을 "그 요소(또는 배경)만 다시. 나머지 레이어는 건드리지 않는다."에서
  실제 동작(씬 전체 재분리)을 정확히 설명하도록 다시 썼다. 순수 한국어(가타카나/히라가나/한자 없음).
- `fal_api.py`의 `ENDPOINT` 위에 `edit_image`가 현재 레이어 경로에서 호출되지 않고 향후 용도로
  남아 있다는 한 줄 주석을 추가했다. `edit_image`/`ENDPOINT`/`MAX_INPUT_IMAGES`와 그 테스트는 삭제하지 않았다.

## 검증

```
python3 -m pytest tests/ -q \
  --ignore=tests/test_research_web_smoke.py \
  --ignore=tests/test_research_web_agent.py \
  --ignore=tests/test_research_news.py \
  --ignore=tests/test_research_lanes_basic.py
```
결과: `674 passed in 116.16s (0:01:56)`

```
node --check cep/com.autokairos.pd/js/storyboard.js
```
결과: 통과(출력 없음, exit 0)

baseline 669 + 신규 테스트 5개(imagegen 3개 + manifest 2개) = 674, 일치.
