---
name: scene-decompose
description: final_manuscript.md를 의미·길이·인물 기준으로 씬으로 분해해 scenes.json 생성. narration은 원문 substring 불변.
---

# scene-decompose

원고를 씬 단위로 분해한다. narration은 원고에서 **그대로** 가져온다(재작성·요약 금지).

## Reads
- `final_manuscript.md` (필수)
- `plan.md` (선택 — 제목/톤/섹션)

## Writes
- `scenes.json` (스키마: `scenes.schema.json`)

## 그룹핑 기준 (우선순위)
1. 섹션/문단 경계
2. 의미 전환(도입/전개/전환/마무리)
3. 길이 예산: 씬당 한국어 약 100~250자(상한 ~40초 분량)
4. 핵심 인물(주어) 변화 시 씬 경계

## 씬 필드
- title: 2~6글자 핵심 키워드
- narration: 해당 씬 원고 텍스트(원문 substring, 공백 1칸 join)
- characters: 등장 인물(없으면 빈 배열)
- visual_summary: 한 줄 화면 설명
- image_prompt: 생성/검색용 시각 단서(한국어, 아트스타일 키워드 제외)
- duration_estimate_sec: 한국어 글자수 ÷ 6 추정

## 출력
- `scenes.json` 만 출력. JSON 외 텍스트 금지(--output-schema 강제).

## 금지
- narration 변경(요약/오탈자 수정 포함)
- 연출/레이아웃/이미지 생성 결정(후속 단계)

## 한국어 작성 규칙
- 가타카나/히라가나/한자 금지
