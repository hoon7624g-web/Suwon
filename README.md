# 군산각 원본 묶음 (2026-10-31) — 다른 ○○각으로 옮기기용

이 브랜치는 이 저장소의 코드와 섞이지 않는 독립 브랜치다(군산각 저장소 hoon7624g-web/gunsan을 세션에서 읽을 수 없을 때를 위해,
군산각 세션이 넣어 둠). 사이트 코드를 이 브랜치에 커밋하지 말 것.

- `port_2026-10-31.md`: 무엇을 옮기고 무엇을 옮기지 않는지(안내서). 그 안의 '군산 저장소를 받는다'는 이 묶음으로 대신한다.
- `gunsan/`: 2026-10-31 기준 군산각 pipeline·templates(그림 파일 제외)·chatbot·관련 tools·tests·CLAUDE.md.
- `gunsan_2026-10-31_code.diff`: 오늘 군산 코드 변경 전체(pipeline·templates·chatbot·tools·tests, 그림 제외).
- `gunsan_commits.txt`: 오늘 군산 커밋 목록.
쓰는 법: `git fetch origin port-kit-20261031 && git worktree add /tmp/kit origin/port-kit-20261031` 뒤 /tmp/kit 를 읽는다.
날씨 위젯: 군산 커밋 c54bdeb5f3(ui(weather))이 최종본이다 — gunsan/templates/assets/weather.js, _side.html.j2, css/80-side.css, assets/wx/(날씨각 아이콘), present.weather_vm, locales.SIDE_WORDS.
