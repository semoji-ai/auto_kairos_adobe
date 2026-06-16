# AE 모션그래픽 실전 기법 — 리서치 학습 노트

> 웹 리서치(Mt.Mograph, Motion Array, PremiumBeat, Adobe Help 등) 종합. 모션 라이브러리 정교화 근거.

## 1. 이징 (가장 큰 학습)

- **Easy Ease 기본 influence = 33.33%(대칭 S커브)** — gentle/ambient(부유·호흡)엔 OK, **snappy 등장/퇴장엔 부적합**(흐물거림).
- **비대칭 이징이 정석**: 한 방향만 — ease **out**(느린 시작→빠른 끝) 또는 ease **in**(빠른 시작→느린 끝). 둘 다 걸면 indecisive.
  → 우리 `easeKeys`는 등장에 **easeOut만 influence 75**로 적용 중 = 방향 맞음(33보다 강해 snappy).
- **오버슈트**: 베지어 핸들을 목표값 너머로(키프레임 추가 없이) **또는 3키(start→overshoot→settle)**. 3키가 weight/settle을 만듦 → 2키로는 안 됨.
  → 우리 `pop_bounce`가 3키(0→110→100) = 정석.
- **바운스**: 다중 오버슈트를 감쇠 진폭으로 반복(추가 키프레임). 복잡한 건 익스프레션/플러그인.
- **프리셋 라이브러리 권장 형태**: sharp ease-out / standard S-curve / overshoot+bounce / sharp snap.

## 2. 효과(폴리시) — 적정 파라미터

- **Drop Shadow**: 프리미엄 룩은 **Softness ↑(~120)** + 적당한 opacity. **2~3개 스택**(강한 것=ambient glow, 부드러운 것=smooth). 단일 하드 섀도는 싸 보임.
  → 우리 applyDetail softness 50 → **120**으로 상향.
- **Glow**: Threshold ~63%, Radius ~17, Intensity ~3.6, Color Looping "Sawtooth B>A". 고급은 Deep Glow/Optical Glow(플러그인).
- **Motion Blur**: 모든 이동 요소에 **필수** — 없으면 시청자가 "인위적"으로 인지. comp 토글 + 레이어 토글.
  → 우리는 이동 모션에 motionBlur=true 기본 ON. 맞음.
- **Grain**: "too clean 디지털 느낌" 제거용. **약하게**, shadows/midtones에 가중, Overlay/Soft Light 블렌드.
  → 우리 Add Grain intensity 0.4 = 약함. 맞음.

## 3. 트랜지션/타이포/셰이프 (P2 근거)

- **셰이프 빌드/드로잉**: Trim Paths End 0→100(선 그려짐) — 우리 mask_reveal가 이미 사용. 정석.
- **트랜지션**: 와이프(Linear Wipe)·줌·모핑(셰이프 패스 키프레임, 동일 정점수)·리퀴드(플러그인). AE 네이티브로 와이프/줌/패스모핑 자동화 가능.
- **파티클**: CC Particle World(내장) — 디졸브/흩어짐. jsx 이펙트 추가 가능.
- **키네틱 타이포**: Text Animator Range Selector(우리 type_on 기반) + per-character 스케일/회전/지터로 고급화.

## 4. 데이터 주도 원칙

- 프리셋은 **명명된 곡선 + 파라미터**(우리 구조와 일치). influence/타이밍을 수치로 고정해 일관성.
- "고정 수치보다 프로젝트별 조정" — 단 자동화에선 **검증된 기본값 + 오버라이드**가 현실적(우리 params 병합 방식).

## 적용 결정
1. `applyDetail` Drop Shadow softness 50 → **120**(프리미엄). ✓ 반영
2. easeKeys 비대칭(easeOut만) 유지 — 리서치가 정당화. ✓ 현상 유지
3. pop_bounce 3키 유지 — 정석. ✓
4. Glow 파라미터(threshold/radius/intensity)는 matchName 확인 필요 → P2에서 정밀 적용.
5. P2 고급효과(트랜지션/파티클/키네틱고급)는 위 §3 근거로 설계.

## Sources
- [Mt. Mograph — Graph Editor / 이징·오버슈트](https://mtmograph.com/blogs/tools/how-to-use-the-graph-editor-in-after-effects)
- [Motion Array — 애니메이션 개선](https://motionarray.com/learn/after-effects/how-to-easily-create-better-animations-in-adobe-after-effects/)
- [Adobe Help — Speed/이징](https://helpx.adobe.com/after-effects/using/speed.html)
- [PremiumBeat — Glow](https://www.premiumbeat.com/blog/advanced-glow-effect-after-effects/)
- [Motion Array — Glow](https://motionarray.com/learn/after-effects/glow-effects-after-effects/)
- [Adobe Help — Noise/Grain](https://helpx.adobe.com/after-effects/using/noise-grain-effects.html)
- [Evercast — Motion Blur](https://www.evercast.us/blog/after-effects-motion-blur)
