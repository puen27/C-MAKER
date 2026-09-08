# Git 명령어 정리

---

## 기본 설정

처음 Git을 설치하면 사용자 정보를 등록해야 해요. 커밋할 때 누가 작업했는지 기록됩니다.

```bash
git config --global user.name "이름"       # 사용자 이름 설정
git config --global user.email "이메일"    # 이메일 설정
git config --list                           # 현재 설정 전체 확인
```

---

## 저장소 시작

```bash
git init                          # 현재 폴더를 Git 저장소로 초기화
git clone <URL>                   # 원격 저장소를 로컬로 통째로 복사
git remote add origin <URL>       # 로컬 저장소에 원격 저장소 주소 등록
git remote -v                     # 등록된 원격 저장소 주소 확인
```

> `origin`은 원격 저장소의 별칭이에요. 관례적으로 origin을 사용합니다.

---

## 작업 저장 (add → commit → push)

로컬에서 파일을 수정한 후 GitHub에 올리는 기본 흐름이에요.

```bash
git status                        # 수정/추가/삭제된 파일 목록 확인
git add .                         # 변경된 파일 전체를 스테이징(커밋 준비)
git add 파일명                    # 특정 파일만 스테이징
git commit -m "메시지"            # 스테이징된 파일을 커밋 (변경 이력 저장)
git push                          # 현재 브랜치를 원격 저장소에 업로드
git push -u origin 브랜치명      # 처음 push할 때 tracking 설정 포함
```

> `add`는 "이 파일을 커밋에 포함할게요" 라고 선택하는 단계,  
> `commit`은 "이 변경사항을 이력으로 저장할게요" 라는 확정 단계예요.

---

## 가져오기

팀원이 올린 최신 코드를 내 로컬에 반영할 때 사용해요.

```bash
git pull                          # 원격 변경사항을 가져와서 자동으로 merge
git fetch                         # 원격 변경사항을 가져오기만 함 (merge 안 함)
```

> `pull` = `fetch` + `merge`  
> 충돌이 걱정될 때는 `fetch`로 먼저 확인 후 `merge`하는 방식도 있어요.

---

## 브랜치

브랜치는 독립된 작업 공간이에요. 메인 코드에 영향 없이 기능 개발을 할 수 있어요.

```bash
git branch                        # 로컬 브랜치 목록 확인 (* 가 현재 브랜치)
git branch 브랜치명               # 새 브랜치 생성 (이동은 안 함)
git checkout 브랜치명             # 해당 브랜치로 이동
git checkout -b 브랜치명          # 브랜치 생성 + 이동 동시에
git branch -d 브랜치명            # 브랜치 삭제 (merge 완료 후)
git merge 브랜치명                # 현재 브랜치에 다른 브랜치 내용 합치기
```

> 브랜치 네이밍 관례:  
> `feature/기능명` — 새 기능 개발  
> `fix/버그명` — 버그 수정  
> `hotfix/이슈명` — 긴급 수정  

---

## 히스토리 확인

```bash
git log                           # 전체 커밋 히스토리 (상세)
git log --oneline                 # 커밋 히스토리 한 줄로 간략하게 보기
git log --oneline --graph         # 브랜치 분기 흐름까지 시각적으로 확인
git diff                          # 마지막 커밋 이후 변경된 내용 비교
git diff 브랜치A 브랜치B          # 두 브랜치 간 차이 비교
```

---

## 되돌리기

실수했을 때 이전 상태로 되돌리는 명령어예요.

```bash
git restore 파일명                # 수정 전으로 되돌리기 (커밋 전 상태)
git reset HEAD~1                  # 마지막 커밋 취소 (파일 변경사항은 유지)
git reset --hard HEAD~1           # 마지막 커밋 취소 + 파일 변경사항도 삭제 ⚠️
git stash                         # 현재 작업을 임시 저장 (브랜치 이동 시 유용)
git stash pop                     # 임시 저장한 작업 복원
```

> `--hard` 옵션은 복구가 어려우니 신중하게 사용하세요.

---

## 협업 기본 흐름

공동 프로젝트에서 매일 반복하는 작업 순서예요.

```bash
# 1. 작업 시작 전 최신 코드 받아오기
git pull

# 2. 내 브랜치로 이동
git checkout feature/내브랜치

# 3. 작업 후 저장
git add .
git commit -m "기능 설명"

# 4. GitHub에 올리기
git push

# 5. GitHub에서 Pull Request 생성 → 팀원 리뷰 → main에 merge
```

---

## 자주 쓰는 명령어 요약

| 명령어 | 설명 |
|--------|------|
| `git status` | 현재 변경 상태 확인 |
| `git add .` | 전체 파일 스테이징 |
| `git commit -m ""` | 커밋 |
| `git push` | 원격에 업로드 |
| `git pull` | 원격에서 가져오기 |
| `git checkout -b 브랜치명` | 브랜치 생성 + 이동 |
| `git log --oneline` | 커밋 히스토리 확인 |
| `git stash` | 작업 임시 저장 |
