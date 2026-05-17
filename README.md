# Lecture Companion Agent

영어 강의 PDF를 페이지별 한국어 학습 노트와 주석 PDF로 만들어 주는 로컬 CLI 도구입니다.

원본 PDF를 수정하지 않고, 왼쪽에는 원본 슬라이드 이미지를 두고 오른쪽에는 한국어 설명을 붙인 PDF를 생성합니다. 중간 결과는 Markdown 파일로 저장되기 때문에 학생이 AI가 만든 설명을 직접 고치거나, 처음부터 수동 설명을 작성한 뒤 PDF로 렌더링할 수 있습니다.

## 지원 기능

- `input/lectures/`에 넣은 강의 PDF 일괄 처리
- 페이지별 슬라이드 이미지 생성
- PDF 텍스트 추출
- 선택 사항: `input/references/`에 넣은 교재/참고 PDF 기반 설명 보강
- 선택 사항: `input/explanations/`에 직접 작성한 Markdown 설명 반영
- OpenAI API를 이용한 한국어 학습 노트 생성
- `output/{강의파일명}/final/annotated_explanation.pdf` 생성

현재 검색 방식은 키워드 기반 참고자료 매칭입니다. 벡터 DB 기반 RAG는 아직 구현되어 있지 않습니다.

## 빠른 시작

### 1. 프로젝트 받기

```powershell
git clone <repository-url>
cd pdf_explainer_agent
```

이미 저장소를 받은 상태라면 프로젝트 폴더로 이동합니다.

```powershell
cd pdf_explainer_agent
```

### 2. Python 가상환경 만들기

Python 3.9 이상이 필요합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS/Linux에서는 다음처럼 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. OpenAI API 키 설정

AI로 노트를 생성하려면 API 키가 필요합니다.

PowerShell:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

macOS/Linux:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

API 키는 README, 코드, GitHub에 올리지 마세요.

### 4. 강의 PDF 넣기

강의 PDF를 아래 폴더에 넣습니다.

```text
input/lectures/
```

예시:

```text
input/lectures/week01_logic_gate.pdf
input/lectures/week02_combinational_logic.pdf
```

교재나 참고자료 PDF가 있으면 아래 폴더에 넣습니다.

```text
input/references/
```

참고자료 없이 실행해도 됩니다.

### 5. 실행하기

모든 강의 PDF를 처리합니다.

```powershell
python main.py --all
```

특정 PDF 하나만 처리합니다.

```powershell
python main.py --lecture input/lectures/week01_logic_gate.pdf
```

결과는 다음 위치에 생성됩니다.

```text
output/week01_logic_gate/
|-- pages/
|   |-- page_001.png
|   `-- page_002.png
|-- notes/
|   |-- page_001.md
|   `-- page_002.md
`-- final/
    `-- annotated_explanation.pdf
```

## API 키 없이 테스트하기

API 키 없이도 렌더링 흐름만 확인할 수 있습니다.

```powershell
python main.py --test-sample --render-only
```

이 명령은 샘플 PDF를 만들고, 페이지 이미지를 만든 뒤, 노트가 없는 페이지에는 기본 안내 문구를 넣어 최종 PDF를 렌더링합니다. AI 노트 생성은 하지 않습니다.

AI 노트 생성까지 확인하려면 API 키를 설정한 뒤 실행합니다.

```powershell
python main.py --test-sample
```

## 자주 쓰는 명령어

| 목적 | 명령어 |
| --- | --- |
| 모든 PDF 처리 | `python main.py --all` |
| 특정 PDF만 처리 | `python main.py --lecture input/lectures/file.pdf` |
| 기존 노트를 덮어쓰기 | `python main.py --all --overwrite-notes` |
| 페이지 이미지를 다시 만들기 | `python main.py --all --force-images` |
| 노트만 생성하고 PDF는 만들지 않기 | `python main.py --all --notes-only` |
| 기존 노트로 PDF만 다시 만들기 | `python main.py --all --render-only` |
| 수동 설명 템플릿 만들기 | `python main.py --setup-explanations` |
| 수동 설명을 페이지별 노트로 분리 | `python main.py --split-explanations` |

## 수동 설명 Markdown 작성법

AI가 자동 생성한 설명 대신 학생이나 조교가 직접 설명을 작성할 수 있습니다. 이때 가장 권장하는 방식은 강의 PDF마다 `explanation.md` 파일 하나를 두고, 슬라이드 번호별 heading으로 나누는 방식입니다.

### 1. 템플릿 생성

먼저 강의 PDF를 `input/lectures/`에 넣은 뒤 실행합니다.

```powershell
python main.py --setup-explanations
```

그러면 아래처럼 파일이 생성됩니다.

```text
input/explanations/week01_logic_gate/explanation.md
```

### 2. Markdown 형식

슬라이드별로 반드시 다음 heading 중 하나를 사용합니다.

```markdown
# Slide 1

1번 슬라이드 설명을 작성합니다.

# Slide 2

2번 슬라이드 설명을 작성합니다.
```

아래 형식도 인식합니다.

```markdown
## slide 1
## Page 1
# 페이지 1
# 슬라이드 1
```

권장 형식은 `# Slide 1`, `# Slide 2`입니다. 번호는 PDF 페이지 순서와 맞아야 합니다.

### 3. 설명 내용 작성 예시

```markdown
# Slide 1

## 핵심 개념

- Multiplexer는 여러 입력 중 하나를 선택해서 하나의 출력으로 보내는 회로입니다.
- 선택 신호(select signal)가 어떤 입력을 통과시킬지 결정합니다.

## 쉽게 이해하기

여러 개의 도로 중 하나만 열어서 차가 지나가게 하는 교통 통제 장치처럼 생각할 수 있습니다.

## 주의할 점

MUX는 값을 계산하는 회로라기보다, 입력 중 하나를 고르는 선택 회로입니다.

# Slide 2

## 핵심 개념

Full adder는 A, B, carry-in 세 비트 값을 더해서 sum과 carry-out을 만듭니다.
```

### 4. 페이지별 노트로 분리

수동 설명을 작성한 뒤 다음 명령을 실행합니다.

```powershell
python main.py --split-explanations
```

그러면 아래 파일들이 생성됩니다.

```text
output/week01_logic_gate/notes/page_001.md
output/week01_logic_gate/notes/page_002.md
```

이후 PDF만 렌더링합니다.

```powershell
python main.py --all --render-only
```

## 페이지별 노트 Markdown 형식

`output/{강의파일명}/notes/page_001.md` 같은 파일은 직접 수정할 수 있습니다. 렌더러는 복잡한 Markdown 전체를 지원하지 않고, 아래 정도의 기본 문법을 안정적으로 처리합니다.

지원:

- `# 제목`
- `## 제목`
- `- 목록`
- 일반 문단
- 빈 줄

권장 예시:

```markdown
## 원문 해석

이 슬라이드는 2-to-1 multiplexer의 동작을 설명합니다.

## 교재 참고 설명

첨부된 교재 참고 내용이 없습니다.

## 아주 쉬운 설명

- 입력이 여러 개 있습니다.
- select 값이 어떤 입력을 고를지 정합니다.
- 선택된 입력만 output으로 전달됩니다.

## 자세한 설명

MUX는 여러 신호가 하나의 경로를 공유해야 할 때 사용됩니다.
```

표, 이미지, HTML, LaTeX 수식은 Markdown 파일에 남아 있을 수 있지만, 최종 PDF 렌더러에서 원래 모양 그대로 보장되지는 않습니다. 최종 PDF에 안정적으로 보이게 하려면 짧은 제목, 문단, bullet 위주로 작성하세요.

## 설정 파일

기본 설정은 `config.yaml`에 있습니다.

```yaml
input:
  lectures_dir: "input/lectures"
  references_dir: "input/references"
  explanations_dir: "input/explanations"

output:
  root_dir: "output"

generation:
  use_references: true
  use_explanations: true
  overwrite_existing_notes: false

model:
  provider: "openai"
  model_name: "gpt-4.1-mini"
```

참고자료를 사용하지 않으려면 다음처럼 바꿀 수 있습니다.

```yaml
generation:
  use_references: false
  use_explanations: true
  overwrite_existing_notes: false
```

## 폴더 구조

```text
.
|-- main.py
|-- config.yaml
|-- requirements.txt
|-- scripts/
|   `-- create_sample_pdf.py
|-- src/
|-- input/
|   |-- lectures/
|   |-- references/
|   `-- explanations/
`-- output/
```

`input/`에는 개인 강의자료가 들어가고, `output/`에는 생성물이 들어갑니다. 이 두 종류의 실제 파일은 `.gitignore`로 제외되어야 합니다.

## 문제 해결

### `OPENAI_API_KEY is not set`

AI 노트 생성을 하려면 API 키가 필요합니다. 키 없이 PDF 렌더링만 확인하려면 `--render-only`를 사용하세요.

```powershell
python main.py --test-sample --render-only
```

### 한글이 PDF에서 깨져 보임

Windows에서는 보통 `malgun.ttf`를 자동으로 찾습니다. 다른 환경에서 한글 폰트가 없으면 `KOREAN_FONT_PATH`를 지정하세요.

PowerShell:

```powershell
$env:KOREAN_FONT_PATH="C:\Windows\Fonts\malgun.ttf"
```

macOS/Linux:

```bash
export KOREAN_FONT_PATH="/path/to/korean-font.ttf"
```

### 새로 수정한 노트가 PDF에 반영되지 않음

노트를 수정한 뒤 렌더링만 다시 실행합니다.

```powershell
python main.py --all --render-only
```

### 기존 AI 노트를 다시 만들고 싶음

```powershell
python main.py --all --overwrite-notes
```

## 배포 전 체크리스트

- 실제 강의 PDF, 교재 PDF, 생성된 `output/` 파일을 커밋하지 않았는지 확인
- `.env`나 API 키를 커밋하지 않았는지 확인
- `input/lectures/.gitkeep`, `input/references/.gitkeep`, `input/explanations/.gitkeep`는 유지
- 새 컴퓨터에서 `pip install -r requirements.txt` 후 `python main.py --test-sample --render-only`가 되는지 확인

## 보안 및 저작권 주의

- API 키는 절대 GitHub에 올리지 마세요.
- 수업 자료와 교재 PDF는 저작권이 있을 수 있으므로 공개 저장소에 올리지 마세요.
- 생성된 설명도 원본 자료 내용을 포함할 수 있으므로 공개 범위를 확인하세요.
