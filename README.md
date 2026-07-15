# auto_kairos Adobe PD Assistant

After Effects(1차)/Premiere(2차) 내 영상 제작 보조 패널 + 로컬 백엔드.
**기획→리서치→원고→씬분석→에셋 생성→AE 조립**을 한 파이프라인으로 수행한다.

- **콘텐츠 파이프라인**: 자체 내장(브리프 래칫·리서치·원고·씬분석·엔티티·시트·씬렌더). **auto_kairos_v3/v4 런타임 의존 없음.**
- **이미지 생성**: codex 내장 `$imagegen`(codex-fleet 병렬, OpenAI API 미사용). semoji 아트스타일.
- **LLM 추론**: claude CLI(기본) 또는 codex.
- **음성**: ElevenLabs(글자별 타임스탬프로 연출 타이밍 동기) / 키 없으면 macOS `say` 폴백.
- **실사 자료**: Serper 이미지 검색 + 멀티모달 적합성 검사.

스펙: `docs/spec/SPEC_v0.2.md`

## 설치

```bash
git clone <repo> auto_kairos_adobe && cd auto_kairos_adobe
./install.sh            # venv + pip + .env + 헬스체크 (외부 CLI는 체크·안내)
./install.sh --cep      # (macOS) CEP 패널을 AE 확장 폴더에 링크
```

`install.sh`가 자동으로 하는 것: `.venv` 생성 + `requirements.txt` 설치, `.env` 생성(.env.example 복사), 모듈·데이터 자산 헬스체크. codex/claude CLI는 인증이 필요해 **설치 여부만 확인하고 안내**한다.

### 별도 준비물(외부 — 자동설치 안 함)
| 항목 | 용도 | 필수 |
|---|---|---|
| **codex CLI**(로그인) | 이미지 생성·비전 | 이미지 생성 시 필수 |
| **claude CLI** | LLM 추론(기본 오케스트레이터) | 원고·씬분석 등 필수 |
| **API 키**(`.env`) | ElevenLabs(TTS)·Serper(검색) | 선택(없으면 해당 기능만 비활성) |
| **After Effects 2026** | 최종 조립·렌더 | 제작 단계 |

## 실행

```bash
./.venv/bin/python backend/app.py     # 로컬 백엔드(기본 :8765)
# After Effects 실행 → Window > Extensions > auto_kairos PD
```

## 설정(.env)
`.env.example` 참고. 모든 키는 선택이며, `AUTO_KAIROS_ENV`로 .env 위치를 지정할 수 있다.
(키가 os.environ에 있으면 그게 우선.)
