# Robot Data Studio

Robot Data Studio는 Lance 기반 로봇 데이터셋 큐레이션 툴입니다. 수집된 LeRobot/Lance
데이터셋을 브라우저에서 열어 episode를 검수하고, skill 단위로 clip을 잘라
학습용으로 export하는 단계를 담당합니다. 단순히 데이터를 미리 보는 것이 아니라
VLA·policy 학습에 쓸 고품질 데이터셋을 만들기 위한 도구입니다.

이 repo는 `rllab_robot_stack`의 submodule (`repos/robo_dataview/`)로 편입되어
있으며, 일반적으로는 상위 stack에서 같이 설치/실행하는 것을 권장합니다.

## 주요 기능

- **Web GUI**: 데이터셋 탐색, episode 리뷰, skill clip annotation, 검수 큐, export 관리.
- **Rerun Web Viewer 연동**: episode 리플레이, 멀티 카메라 보기, state/action 타임라인.
- **Lance / LanceDB**: 원본 데이터/annotation/임베딩의 source of truth.
- **LeRobot 호환**: LeRobot v3 import/export, 공식 loader 검증 (옵션).
- **Python Worker**: VLM 자동 라벨링, 임베딩 생성, 키프레임/Rerun 캐시, export 작업.

## 기술 스택

- Frontend: Next.js 15, React 19, TypeScript
- Backend: FastAPI, Pydantic
- Data: Lance / LanceDB
- Viewer: Rerun Web Viewer
- Workers: Python (RQ 또는 inline)
- Interop: LeRobotDataset, Hugging Face datasets

## 디렉토리 구조

```text
apps/
  api/        FastAPI 백엔드
  web/        Next.js 프론트엔드
docs/         아키텍처/스키마/API/UI/배포 문서
workers/      Python worker 함수 (VLM, embedding, export)
packages/     공용 schema, prompt template
data/         로컬 Lance 데이터, 캐시, export 결과
```

## 설치

### 권장: 상위 stack에서 한 번에 설치

`rllab_robot_stack`을 clone한 뒤 stack root에서 아래만 실행하면 됩니다.

```bash
cd /path/to/rllab_robot_stack
./scripts/setup_all.sh
```

이 스크립트는 [`uv`](https://docs.astral.sh/uv/)로 `repos/robo_dataview/.venv`
(Python 3.11)를 만들고 viewer에서 쓰는 extra (`dev,lance,rerun,video,storage`)와
`lerobot2lance` converter까지 같이 설치합니다. Web 워크스페이스는 `bun`(없으면 `npm`)으로
설치합니다.

### 단독 설치

이 repo만 단독으로 쓸 때도 `uv` 사용을 권장합니다.

```bash
cd repos/robo_dataview
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -e ".[dev,lance,rerun,video,storage]"
bun install        # 또는 npm install
cp .env.example .env
```

필요에 따라 추가 extra를 골라 설치합니다.

```bash
uv pip install --python .venv/bin/python -e ".[lerobot]"   # 공식 LeRobot loader 검증
uv pip install --python .venv/bin/python -e ".[export]"    # LeRobot Parquet/MP4 export
uv pip install --python .venv/bin/python -e ".[queue]"     # Redis/RQ 백그라운드 큐
uv pip install --python .venv/bin/python -e ".[ml]"        # Transformers CLIP/SigLIP
uv pip install --python .venv/bin/python -e ".[convert]"   # lerobot2lance 변환 API
```

## 실행

### 권장: 상위 stack의 view 스크립트

```bash
./scripts/view.sh latest                           # 가장 최근 수집 session
./scripts/view.sh latest_export                    # 가장 최근 curated export
./scripts/view.sh session_YYYYMMDD_HHMMSS_grasp    # 특정 session
```

기본 포트:

```text
Web (Next.js)   http://127.0.0.1:3000
API (FastAPI)   http://127.0.0.1:8000
```

### 단독 실행

repo 루트에서 API와 web을 함께 띄웁니다.

```bash
bun run dev    # 또는 npm run dev
```

`API_HOST`, `API_PORT`, `WEB_HOST`, `WEB_PORT`는 `.env`에서 바꿀 수 있습니다.

### 백그라운드 작업 모드 (옵션)

기본은 inline 실행이라 별도 worker 없이도 동작합니다. RQ 큐를 쓰려면:

```bash
export ROBOT_DATA_STUDIO_JOB_QUEUE=rq
export ROBOT_DATA_STUDIO_REDIS_URL=redis://127.0.0.1:6379/0
rq worker robot-data-studio --url "$ROBOT_DATA_STUDIO_REDIS_URL"
```

### 인증 (옵션)

`ROBOT_DATA_STUDIO_API_KEY`를 설정하면 `/api/*` 요청에
`X-Robot-Data-Studio-API-Key` 헤더가 필요합니다. 검수 actor는
`X-Robot-Data-Studio-User`로 기록됩니다.

## 사용 흐름

상위 stack의 `view.sh`로 데이터셋을 열면 두 개의 탭이 보입니다.

- **Browse**: 수집된 episode를 빠르게 훑어보고 삭제/플래그(soft) 처리.
- **Annotate**: episode 안에서 skill 단위 clip의 시작/끝을 잘라 라벨을 붙이고 accept.

검수가 끝나면 Annotate 탭에서 **Lance Training Bundle**을 export 합니다.
export 결과는 stack의 `data/exports/<version>/`에 들어가고, 이후 학습은
상위 stack에서 `./scripts/train_policy.sh latest_export`로 바로 이어집니다.

### 키맵 요약

Browse 탭:

```text
Space        재생/일시정지
←/→          이전/다음 frame
↑/↓          이전/다음 episode
X            episode 삭제 (soft, 다시 누르면 undo)
F            episode 플래그 + 메모
K            disposition 초기화 (delete/flag undo)
Enter        선택 episode를 Annotate 탭에서 열기
```

Annotate 탭:

```text
I            clip 시작 frame 지정
O            clip 끝 frame 지정
1-9          skill 선택 + 현재 I→O clip을 한 번에 create + accept
0            현재 draft clip 취소
Backspace    선택한 clip 삭제
M / B        bad-frame / bad-range (cheatsheet에서 opt-in)
?            cheatsheet 열기
Esc          모달 닫기
```

## 데이터 계약

### annotation은 raw 데이터셋을 건드리지 않습니다

검수/annotation은 항상 별도 테이블에만 기록됩니다.

```text
annotations_current.lance   # 현재 active view
annotation_events.lance     # create/update/delete 감사 로그
annotations.jsonl           # restart/디버그용 사본 (soft-delete tombstone 포함)
```

학습에 반영하려면 Data Studio에서 Lance Training Bundle을 export 하세요.
raw `episodes.lance`는 절대 수정하지 않습니다.

### Skill 어휘 contract

DataView의 skill label은 stack 전체에서 같은 문자열이 됩니다.

```text
DataView label_value
  = train_skill_clips.lance skill_name
  = Skill Registry key
  = Robot CLI command
  = checkpoint 디렉토리 이름
```

기본 어휘는 10개로 고정되어 있습니다 (`approach, grasp_part, grasp_bolt,
insert_bolt, place, push_button, grasp_drill, drill_trigger, bimanual_grasp,
insert_tire`). export 시 이 vocabulary에 없는 라벨은 거부됩니다. 사용자 정의
"custom skills"는 탐색용으로 브라우저 localStorage에만 보관되며, 안정화되면
canonical vocabulary에 정식 추가하는 절차로 승격합니다.

### Curated export 레이아웃

`data/exports/<version>/lance_subset/` 아래 다음 테이블이 만들어집니다.

```text
manifest.json + metadata.json + validation.json
episodes.lance              # 메타데이터 only
frames.lance                # frame-level QA / 캐시
media.lance                 # canonical media 인덱스
skills.lance                # skill vocabulary
skill_segments.lance        # accept된 skill 경계
frame_skill_labels.lance    # accept된 frame 단위 라벨
train_skill_clips.lance     # 학습 primary table (skill clip 단위)
train_episodes.lance        # episode-level fallback
annotations_current.lance
annotation_events.lance
```

`train_skill_clips.lance`에서 `episode_index`는 clip row 인덱스이고,
`source_episode_index`가 원본 trajectory를 가리킵니다. `video_frame_offset`은
clip 내부의 local frame `t`를 원본 video frame `video_frame_offset + t`로
매핑합니다.

## 문서

- 아키텍처/스키마/API/UI/배포 상세: `docs/`
- 라이브 todo / 마일스톤: `docs/plan.md`
- 배포 노트: `docs/deployment.md`
- 실데이터 호환성 smoke check: `docs/real_dataset_compatibility.md`

```bash
.venv/bin/python scripts/check_dataset_compat.py /path/to/dataset
```
