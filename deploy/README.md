# 한 장 제주 공개 웹 배포

2026-11-21 Vercel 402로 중단된 공개 웹을 Render Free로 이전했다.

- 이용 주소: https://hanjang-jeju.hyunolike.dev
- 보조 주소: https://hanjang-jeju.onrender.com
- 상태: https://hanjang-jeju.hyunolike.dev/api/web/health
- 모델 상태: https://hanjang-jeju.hyunolike.dev/api/web/capabilities
- 서비스: srv-dc0p4lks728c73av4vc0 / Singapore / Free / 단일 인스턴스
- 운영 배포: dep-dc0p4m4s728c73av50jg / 애플리케이션 커밋 1e17f11b6e9267f61a7c578589714a02232a4fdd

## 배포와 검증

`deploy/render-free-web` 브랜치의 `deploy/public-web`을 Docker 빌드 문맥으로 사용한다. 최상위 render.yaml에 설정을 남겼다. 자동 배포는 껐으며 검증한 커밋만 수동 배포한다. 설치형 릴리스와 공개 main의 소스 동기화는 별개다.

기존 공개 웹 사본 312개 파일의 SHA256을 web-release-manifest.json에 보존했다. CSV 원본, .env와 모델 가중치는 사본과 이미지에 없다. 공개 전용 API가 업로드를 요청 중에 처리하며 DB나 영구 업로드 저장소는 없다. Cloudflare 인증값은 Render 서버 환경변수에만 설정했다.

Render HTTPS 주소에서 가상 CSV 96행/48개월의 합계 48개가 별도 합산과 일치했다. understand 0.58초, 3개월 예측 포함 analyze 11.51초였으며 예측 구간과 execution.verified=true를 확인했다. 실제 Cloudflare plan 5.72초 후 사용자 확인에 해당하는 요청으로 Agent analyze 1.07초를 실행해 mode=agent, verified=true와 같은 합계를 확인했다. fallback은 없었다. PC 전용 /api/workspace와 /api/datasets는 404였다.

공개 HTML/JS/CSS/예시 목록 해시가 기존 사본과 일치하고 예시 9개가 제공된다. 로컬 Linux 컨테이너에서도 512MB 제한으로 같은 계산과 AI 경로를 통과했다. 분석 후 메모리는 약 173MiB였다. 이는 Render의 실제 최대 메모리 측정값이 아니다. 새 배포의 모바일/인쇄 브라우저 회귀 전체는 다시 실행하지 않았다.

## 기존 도메인 연결

Vercel 팀 차단 원인은 `edgeConfigRead`의 무료 한도 초과였다. 공식 지원 화면에서 일회 무료 유예를 적용했고, 팀 API의 `softBlock=null`, `blocked=null`, `billing.plan=hobby`를 확인했다. 유료 전환 없이 한도가 30일간 3배로 늘어난 조치다. 한도를 초과한 실제 Reader Project는 아직 확인하지 못했다.

`hanjang-jeju`의 CNAME 하나를 `hanjang-jeju.onrender.com.`으로 추가했다(TTL 60, 레코드 `rec_d34c9949a72ba8768a329130`). 기존 5개 DNS 레코드는 보존했다. Render 사용자 도메인 `cdm-dc0p8o4s728c73avggk0`은 verified이며 TLS 발급도 완료됐다. 권한 DNS와 Google Public DNS에서 새 CNAME을 확인했다. 일부 시스템 DNS에는 기존 Vercel 주소가 캐시되어 있어 전파 중에는 이전 Vercel 화면에 도달할 수 있다. 일반 접속도 차단 해제 후 HTTPS 200을 반환했다.

Render IP를 지정한 검사에서도 Host/SNI와 인증서 검증은 사용자 도메인으로 유지했다(TLS 검증 결과 0, HTTP 200, `x-render-origin-server: uvicorn`). 이 경로에서 가상 96행/48개월 합계와 3개월 예측 및 검증을 통과했다. understand 0.91초, analyze 10.37초, 실제 Cloudflare plan 2.65초, 확인 후 Agent analyze 1.31초였다. PC 전용 API는 404이며 HTML/JS/CSS와 공개 예시 목록 해시 및 예시 9개도 일치했다.

## 무료 운영과 다음 배포

15분 동안 요청이 없으면 절전하며 다음 접속 때 기동 대기가 생길 수 있다. 월 750 무료 실행 시간은 같은 워크스페이스의 다른 무료 서비스와 공유한다. 무료 트래픽/빌드 한도도 적용된다. 주기적인 깨우기나 유료 디스크는 추가하지 않았다.

소스가 바뀌면 유지보수 원본의 허용 목록 절차로 새 공개 웹 사본을 만들고 원본/비밀값 제외와 API 검증 후 이 브랜치를 갱신한다. 설치형 릴리스만 갱신해도 이 고정 웹 사본이 자동으로 바뀌지는 않는다.

```bash
render deploys create srv-dc0p4lks728c73av4vc0 --commit <검증한_커밋_SHA> --wait
```
