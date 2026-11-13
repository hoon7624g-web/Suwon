"""화제 영상 목록(yt_channels.json의 popular_video_ids) — 군산각 규칙(2026-11-10)을 그대로.

    python <kit>/scripts/yt_popular.py data/<지역> <지역 한글 이름>  > data/<지역>/yt_channels.json

이 사이트의 videos.json에 실린 한국어 영상(lang == 'ko', exclude 없음) 가운데 조회수 10만 회 이상을 조회수 순으로
최대 70편, 10만 회가 20편보다 적으면 많이 본 20편. 조회수는 view_text('조회수 1,234회')의 정수(자료를 실은 때의 값).
channels는 빈 목록(채널 큐레이션은 아직 없음 — 화면의 '인기 채널' 칸은 비면 나오지 않아야 한다)."""
import json, re, sys
data_dir, name = sys.argv[1].rstrip('/'), sys.argv[2]
v = json.load(open(f'{data_dir}/videos.json', encoding='utf-8'))
def vc(x):
    m = re.search(r"(\d[\d,]*)\s*회", str(x.get("view_text") or "")); return int(m.group(1).replace(",", "")) if m else 0
ko = sorted([x for x in v if x.get('youtube_id') and not x.get('exclude') and x.get('lang') == 'ko' and vc(x) > 0], key=lambda x: -vc(x))
pick = [x for x in ko if vc(x) >= 100_000][:70] or []
if len(pick) < 20: pick = ko[:20]
print(json.dumps({"description": f"{name} 여행·맛집·로컬 문화를 다룬 화제 영상 큐레이션 — 이 사이트에 실린 한국어 영상 가운데 조회수 10만 회 이상(최대 70편, 10만 회가 20편보다 적으면 많이 본 20편)을 조회수 순으로(군산각 2026-11-10 규칙). 채널 큐레이션은 아직 없음.",
                  "checked_at": max((x.get('checked_at') or '') for x in pick) if pick else "",
                  "popular_video_ids": [x['youtube_id'] for x in pick], "channels": []}, ensure_ascii=False, indent=2))
print(f"# {len(pick)} videos" + (f", min views {vc(pick[-1]):,}" if pick else ""), file=sys.stderr)
