# 한 장 제주 공개 웹 배포

2026-11-21 Vercel 402로 중단된 공개 웹을 Render Free로 이전했다.

- 이용 주소: https://hanjang-jeju.onrender.com
- 상태: https://hanjang-jeju.onrender.com/api/web/health
- 모델 상태: https://hanjang-jeju.onrender.com/api/web/capabilities
- 서비스: srv-dc0p4lks728c73av4vc0 / Singapore / Free / 단일 인스턴스
- 운영 배포: dep-dc0p4m4s728c73av50jg / 애플리케이션 커밋 1e17f11b6e9267f61a7c578589714a02232a4fdd

## 배포와 검증

`deploy/render-free-web` 브랜치의 `deploy/public-web`을 Docker 빌드 문맥으로 사용한다. 최상위 render.yaml에 설정을 남겼다. 자동 배포는 껐으며 검증한 커밋만 수동 배포한다. 설치형 릴리스와 공개 main의 소스 동기화는 별개다.

기존 공개 웹 사본 312개 파일의 SHA256을 web-release-manifest.json에 보존했다. CSV 원본, .env와 모델 가중치는 사본과 이미지에 없다. 공개 전용 API가 업로드를 요청 중에 처리하며 DB나 영구 업로드 저장소는 없다. Cloudflare 인증값은 Render 서버 환경변수에만 설정했다.

Render HTTPS 주소에서 가상 CSV 96행/48개월의 합계 48개가 별도 합산과 일치했다. understand 0.58초, 3개월 예측 포함 analyze 11.51초였으며 예측 구간과 execution.verified=true를 확인했다. 실제 Cloudflare plan 5.72초 후 사용자 확인에 해당하는 요청으로 Agent analyze 1.07초를 실행해 mode=agent, verified=true와 같은 합계를 확인했다. fallback은 없었다. PC 전용 /api/workspace와 /api/datasets는 404였다.

공개 HTML/JS/CSS/예시 목록 해시가 기존 사본과 일치하고 예시 9개가 제공된다. 로컬 Linux 컨테이너에서도 512MB 제한으로 같은 계산과 AI 경로를 통과했다. 분석 후 메모리는 약 173MiB였다. 이는 Render의 실제 최대 메모리 측정값이 아니다. 새 배포의 모바일/인쇄 브라우저 회귀 전체는 다시 실행하지 않았다.

## 기존 도메인 연결 대기

`hanjang-jeju.hyunolike.dev`는 Render에 등록했지만 unverified다. Vercel DNS 생성은 연결 도구와 같은 팀 CLI 모두에서 402 `Your Team exceeded our fair use limits and has been blocked`로 거부됐다. DNS 변경은 적용하지 않았다. 원래 hyunolike.dev의 `*` ALIAS는 `cname.vercel-dns-017.com.`이며 hanjang-jeju 전용 레코드는 없었다.

Vercel 팀 제한 해제 후 `hanjang-jeju`의 CNAME 하나를 `hanjang-jeju.onrender.com.`으로 추가한다(TTL 60). 다른 서비스의 와일드카드 DNS는 수정하지 않는다. Render 도메인 검증/TLS 발급과 사용자 도메인의 HTTPS 메인/실제 분석을 검사한 뒤 대표 주소로 사용한다. 현재 이용 주소는 Render 기본 주소다.

## 무료 운영과 다음 배포

15분 동안 요청이 없으면 절전하며 다음 접속 때 기동 대기가 생길 수 있다. 월 750 무료 실행 시간은 같은 워크스페이스의 다른 무료 서비스와 공유한다. 무료 트래픽/빌드 한도도 적용된다. 주기적인 깨우기나 유료 디스크는 추가하지 않았다.

소스가 바뀌면 유지보수 원본의 허용 목록 절차로 새 공개 웹 사본을 만들고 원본/비밀값 제외와 API 검증 후 이 브랜치를 갱신한다. 설치형 릴리스만 갱신해도 이 고정 웹 사본이 자동으로 바뀌지는 않는다.

```bash
render deploys create srv-dc0p4lks728c73av4vc0 --commit <검증한_커밋_SHA> --wait
```
