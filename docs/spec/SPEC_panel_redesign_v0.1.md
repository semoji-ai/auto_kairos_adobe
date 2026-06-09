# SPEC — AE 패널 재설계: 스토리보드 중심 통합 작업대 + 실행형 제작 비서 (v0.1)

> 작성일 2026-06-09. 대상: `auto_kairos_adobe` CEP 패널 + stdlib 백엔드.
> 결정 출처: 사용자 브레인스토밍 Q&A(아래 §1) + v3/kairos_ai 스토리보드 레퍼런스 조사.

## 0. 목표 / 비전

AE 안에서 **콘텐츠 제작 비서(실행형 챗봇)** 와 함께 기획 → 리서치 → 원고 → 에셋 이미지 → 장면 → (후속) 비디오 → AE 조립까지 진행하는 통합 작업대. 중심 화면은 **스토리보드 프로덕션 시트**(씬 단위 분할/통합·나레이션·장면 이미지 관리).

## 1. 확정 결정 (브레인스토밍)

| 항목 | 결정 |
|---|---|
| 챗봇 역할 | **하이브리드** — 단계 버튼/시트=제어, 채팅=질문·미세조정 |
| 챗봇 능력 | **실행형** — 대화로 실제 액션 호출 |
| 실행 범위 | **태스크 체크리스트 자율주행 + 체크포인트**(어디까지 이어갈지 확인) |
| 실행 방식 | **A. 구조화 의도 루프** — codex `--output-schema` `{reply, action, next}` → 백엔드가 기존 액션 실행 |
| 설계 범위 | 전체(셸+스토리보드+챗봇) 한 번에 설계, 구현은 P1~P5 단계 |
| 창 형태 | 독립 플로팅·리사이즈 창 + 반응형(좁으면 카드, 넓으면 테이블) |
| 중심 레이아웃 | **스토리보드 프로덕션 시트** (씬당 1행) |

## 2. 네비게이션 — 2뷰 모델

- **목록 뷰**: 새 프로젝트 폼 + 프로젝트 카드(제목·스타일·분량·상태). 카드 클릭 → 입장.
- **상세 뷰**: 프로젝트 전용 작업대. 상단 `← 목록` 으로 퇴장.
- 상태: `CURRENT_PROJECT`. 뷰 전환은 show/hide(빌드 불필요). 단일 `index.html`, 섹션 토글.

## 3. 상세 뷰 = 스토리보드 중심 작업대

반응형 3영역(넓은 창 기준):

```
┌─ {제목}  {스타일·분량}                       [← 목록] ─┐
│ 태스크: ✅기획 ✅리서치 ✅원고 ✅씬분해 ⏳캐릭터 ⬜씬이미지 ⬜레이어 ⬜AE │
├───────────────────────────────────┬──────────┤
│ 스토리보드 프로덕션 시트 (중심)          │ 💬 제작 비서  │
│  씬# | 미디어 | 나레이션(편집) | 캐릭터    │ (대화 로그)   │
│  [선택 액션바: 컷나누기·병합·삭제·         │ [입력][전송] │
│   씬이미지 생성·TTS]                    │ ── 미디어 ── │
│                                      │ 에셋 갤러리   │
└───────────────────────────────────┴──────────┘
```

- 좁은 창: 시트=씬 카드 세로 스택, 비서·미디어=접이식 탭.
- **태스크 바**: 파이프라인 단계 상태(§5).

### 3.1 스토리보드 프로덕션 시트 (씬당 1행)

컬럼: `씬# | 미디어(이미지/비디오) | 나레이션(인라인 편집) | 캐릭터/에셋 | (후속: TTS)`

씬 행/구조 작업:
- **컷 나누기(split)**: 한 씬을 두 나레이션으로 분할.
- **병합(merge)**: 선택 2+ 씬 결합.
- **추가/삭제/순서**: 씬 추가(앞/뒤), 삭제, 재정렬.
- **나레이션**: 인라인 편집 + 비서로 생성/수정. 저장 시 `narration_dirty`.
- **씬 이미지**: 행에서 생성/재생성 — **검증된 방식 사용**: 캐릭터 시트 + `semoji_base.jpg` 첨부, 콘티/비율 텍스트 미사용, 캐릭터 유무 분기([[scene-image]]/[[character-sheet]] 규칙).
- **미디어 패널**: 생성 에셋 갤러리(드래그→행 교체).

### 3.2 씬 데이터 모델 (`scenes.json`, 플랫 스키마)

기존 adobe `scenes.json`(scene-decompose 산출물) 확장. 씬당 필드:
- `sceneNumber` (int), `sceneId` (안정 UUID — split/merge 시 에셋 보존), `title`
- `narration` (편집 대상), `narration_dirty` (bool)
- `image_prompt` (장면 묘사), `imageAsset`(source/prompt/placement 등)
- `characters` ([name]) — 행의 character_ref 결정
- `media_kind`: `image` | `video` | `none`
- (후속) `audioPath`, `durationFrames`

> scene-specs 규칙 준수: 플랫 스키마, 이미지 파일 삭제 금지(버전 생성·selected 전환).

## 4. 제작 비서 (실행형, 방식 A)

우측 채팅. 스토리보드/파이프라인을 운전.

### 4.1 구조화 의도 루프

```
사용자 메시지 → POST /api/chat {project_id, message, session_id?}
  백엔드 컨텍스트 구성: 프로젝트 상태 + 태스크목록 + 액션 카탈로그 + codex 세션(멀티턴 resume)
  codex --output-schema → { reply: str,
                            action: {name: str, args: object} | null,
                            next: "continue" | "checkpoint" | "done" }
  action 있으면 → actions.dispatch(name, args)  # 화이트리스트 검증 후 기존 함수 실행
                → 결과·태스크 상태 갱신 → 결과를 컨텍스트에 추가
  next == "continue" 그리고 체크포인트 아님 → 다시 codex 루프(다음 액션)
  next == "checkpoint" → 정지, reply로 확인 요청
  next == "done" → 종료
  진행/결과 → 패널에 스트리밍(기존 job 로그·폴링 재사용)
```

### 4.2 액션 카탈로그 (화이트리스트)

기존 엔드포인트 기반 함수: `run_skill`(plan/deep-research/draft-write/target-research/finalize-manuscript/review-refine/reference-list), `decompose`(scene-decompose), `generate_character`, `generate_references`(레퍼런스 이미지), `generate_scene_images`(씬별 이미지 — 기존 `/api/storyboard` 엔드포인트의 레거시 명칭; **이 패널의 "스토리보드 시트"와는 다른 개념**), `generate_layers`, **시트 편집**(`update_narration`, `split_scene`, `merge_scenes`, `add_scene`, `delete_scene`, `regen_scene_image`).

> 용어 주의: 이 패널의 **"스토리보드"** = 씬 관리 프로덕션 시트(§3.1). 기존 코드의 `/api/storyboard`·`storyboard/` 폴더 = 씬별 이미지(레거시 명칭). 콘티(Seedance용 흑백 스케치)는 또 다른 개념([[scene-image]] 규칙). 구현 시 명칭 혼선 주의 — 가능하면 씬 이미지 엔드포인트를 `/api/scene-images`로 정리.

### 4.3 안전장치

- **화이트리스트만** 실행(미정의 action → 거부 + reply로 설명).
- **파괴 액션 없음**: 이미지/파일 삭제 액션 미포함(이미지 삭제 금지 규칙). 씬 삭제는 `sceneId` 보존·아카이브 방식(하드 삭제 아님).
- **체크포인트 게이트**: 단계 경계마다 정지 가능. 사용자가 "여기까지" 지정.
- **세션 격리**: codex `CLAUDECODE` pop, workspace-write 한정.

## 5. 태스크 체크리스트

- 태스크 = 파이프라인 단계: 기획 → 리서치 → 원고 → 씬분해 → 캐릭터 → 씬이미지 → 레이어 → AE 조립.
- 상태(done/running/pending)는 **산출물 존재로 자동 판정**(plan.md/research/draft/final_manuscript/scenes.json/characters/images/layers) + 명시 오버라이드.
- 비서가 진행하며 체크. 체크포인트 = 단계 경계.

## 6. 백엔드 변경

- **`backend/actions.py`** (신규): router 액션 본문을 호출 가능한 순수 함수로 분리(`(proj_dir, args, ctx) -> result`). 엔드포인트와 비서가 공용. 화이트리스트 레지스트리.
- **`backend/scenes.py`** (신규): `scenes.json` CRUD — load/save, update_narration, split, merge, add, delete(sceneId 보존). 이미지 생성은 imagegen 재사용.
- **`backend/tasks.py`** (신규): 산출물 기반 태스크 상태 판정.
- **`backend/chat.py`** (신규): 구조화 의도 루프(codex --output-schema + actions.dispatch + 세션 resume + 체크포인트).
- **router**: `/api/chat`(POST), `/api/scenes`(GET/PATCH/split/merge/add/delete), `/api/tasks`(GET). 기존 이미지/캐릭터/스토리보드 엔드포인트는 `actions.py` 함수를 호출하도록 정리.
- **codex_runner**: `--output-schema` 지원 확인(이미 있음) — chat 루프가 사용.

## 7. 패널 변경

- `index.html`: 목록 뷰 / 상세 뷰 2섹션. 상세 = 태스크바 + 스토리보드 시트 + 비서 + 미디어 패널.
- 반응형 CSS(미디어 쿼리): 넓으면 2~3열, 좁으면 스택/탭.
- `js/`: 모듈 분리 — `nav.js`(뷰 전환), `storyboard.js`(시트 렌더·행 작업), `chat.js`(비서), `tasks.js`(체크리스트), `media.js`(에셋 패널). 기존 `main.js`의 액션 함수 재사용/이동.
- CEP manifest: 패널 리사이즈/플로팅 크기 범위 설정.

## 8. 구현 분해 (P1~P5)

- **P1**: 네비게이션 셸(목록↔상세) + 반응형 레이아웃 골격. 기존 기능 상세 뷰로 이전.
- **P2**: 스토리보드 프로덕션 시트(씬 행 조회·나레이션 인라인 편집·씬 이미지 생성/재생성·미디어 패널). `/api/scenes` GET/PATCH.
- **P3**: 씬 구조 편집(split/merge/add/delete, sceneId 보존) + 태스크 체크리스트(`/api/tasks`).
- **P4**: 액션 디스패치 리팩터(`actions.py`) — 엔드포인트/비서 공용 화이트리스트.
- **P5**: 제작 비서(`/api/chat` 구조화 루프 + 체크포인트 + 스토리보드 운전) + 채팅 UI.

각 Phase는 독립 테스트·커밋. P1~P4는 비서 없이도 동작(점진 출시).

## 9. 비목표 (이번 스펙 제외)

- TTS/오디오 파이프라인(컬럼 자리만, 활성은 후속).
- 비디오 생성(Seedance) 실제 연동 — 미디어 종류 토글까지만.
- 씬별 다중 캐릭터 roster 자동 매핑(현재 프로젝트당 기준 캐릭터 1명, 행에서 수동 지정).
- Remotion 이식(명시적 제외 — 비전 외).

## 10. 테스트

- 백엔드 stdlib + pytest(`/Users/jleavens_macmini/Projects/auto_kairos_v3/.venv/bin/python -m pytest`, repo 루트). `scenes.py`/`actions.py`/`tasks.py`/`chat.py` 순수 함수 단위 테스트(codex 호출은 monkeypatch). tmp_path 격리.
- 패널 JS: `node -e "new Function(...)"` 문법 체크. 라이브 codex 호출은 사용자 확인 후.

## 11. 미해결 → 결정

- 스트리밍 방식: 기존 job 로그 폴링 재사용(SSE는 후속). → 폴링.
- 씬 삭제: 하드 삭제 금지 → `_archived` 플래그 + sceneId 보존.
- 좁은 창 비서 위치: 하단 탭(시트와 토글). → 탭.
