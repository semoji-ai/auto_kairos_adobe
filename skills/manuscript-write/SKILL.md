---
name: manuscript-write
description: 초안(draft.md)과 타겟 리서치(targeted_claims.json)를 바탕으로 최종 원고(final_manuscript)를 한 호흡 prose로 작성
---

# Manuscript Write

## 역할

이 스킬의 단 하나의 임무: **시청자가 끝까지 보고 싶게 만드는 최종 원고 prose를 작성하는 것**.

다른 모든 결정(layout, motion, mood, imageAsset, headline, items 등)은 이 스킬의 책임이 **아닙니다**.

---

## 입력

- `draft.md` (필수) — 초안. `[[Q:qXXX]]` 마킹이 포함될 수 있음
- `targeted_claims.json` (필수) — 타겟 리서처가 답변한 WHY/HOW 질문들 (answer, evidence, confidence 포함)
- `editorial_brief.json` (있으면) — 편집 방향, 주제, DNA 레버

---

## 해야 할 일

1. **입력 파악**:
   - `draft.md` — 초안 흐름 + `[[Q:qXXX]]` 마킹 위치 파악
   - `targeted_claims.json` — 각 질문의 answer, evidence, confidence 확인
   - `editorial_brief.json` — 편집 방향과 핵심 주제 파악

2. **targeted_claims.json으로 `[[Q:qXXX]]` 해소**:
   - draft.md의 각 `[[Q:qXXX]]` 마킹을 찾아 targeted_claims.json에서 해당 내용의 답변을 확인합니다.
   - `confidence: "high"` 또는 `"medium"`: 그 answer/evidence를 prose에 자연스럽게 통합하세요.
   - `confidence: "low"` 또는 `answer: null`: 그 부분은 단정 표현 없이 우회하거나 제거하세요. 확인 못 한 사실을 창작하지 마세요.
   - 최종 원고에는 `[[Q:qXXX]]` 마킹을 남기지 마세요.

3. **draft.md는 뼈대, 최종 원고는 살붙이기**:
   - draft.md의 사실 흐름과 순서를 존중하되, prose를 완전히 재작성해 매력적으로 만드세요.
   - 타겟 리서치의 구체적 수치/인용/에피소드를 직접 박아 넣으세요.
   - `[[Q:qXXX]]`가 있던 자리에 실제 답변이 들어가면서 prose가 더 풍부해져야 합니다.

4. **이전 원고(직전 버전)가 있으면**:
   - 이전 원고의 좋은 점을 유지하면서 REVISE 지시를 반드시 반영하세요.
   - REVISE 지시는 단순한 참고가 아니라 **강제 반영 항목**입니다.

5. **분량**: 주제와 editorial_brief의 duration_minutes 기준, 분당 약 200~250자 (한국어)

---

## 글쓰기 원칙

- **도입 후킹**: 첫 문장에서 시청자를 붙잡아야 합니다. 질문, 반전, 충격적 사실로 시작.
- **한 호흡 prose**: 씬 구분 없이 자연스럽게 흘러가는 단일 본문.
- **구체성**: 추상적 서술 대신 수치, 날짜, 인물명, 에피소드를 직접 박아넣으세요.
- **속도감**: 짧은 문장과 긴 문장을 리드미컬하게 교차하세요.
- **환각 금지**: targeted_claims에 없는 사실을 창작하지 마세요. confidence:low는 우회.

---

## 출력 규칙

- **마크다운 본문만 출력** — JSON 없음, 스키마 없음.
- `---`와 `# Ch N.` 마커는 사용하지 않습니다. 이 스킬은 순수 prose만 작성합니다.
- 씬 분할 마커(`---`), 챕터 마커(`# Ch N.`), 캐릭터 마커(`<!-- chars: -->`) 불필요.
- `[[Q:qXXX]]` 마킹을 최종 원고에 남기지 마세요.

---

## 절대 금지

- 확인되지 않은 사실 창작 (타겟 리서치에 없는 수치/인용/에피소드)
- JSON 출력 (이 스킬은 마크다운만)
- `[[Q:qXXX]]` 마킹 잔존
- layout/motion/mood/imageAsset 결정
- headline/items/values 같은 구조화 데이터 출력

---

## 출력 형식 예시

```markdown
인류 문명의 순서가 틀렸습니다. 우리는 농사 다음에 배를 만들었다고 생각하죠. 그런데 1955년, 네덜란드의 한 고속도로 공사장에서 크레인이 진흙 속에서 통나무 하나를 건져 올렸습니다. 길이 3미터, 약 1만 년 전의 카누였습니다.

농사보다 2,500년 먼저였습니다.

(... 이런 식으로 자연스럽게 이어지는 한 호흡 prose ...)
```

작업이 끝나면 **최종 원고 마크다운 본문만** 출력하고 종료하세요.
