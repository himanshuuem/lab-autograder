# Walkthrough video

`lab-grader-walkthrough.mp4` (6 min 22 s): every screen and button of the dashboard,
recorded on the demo classroom (fictional students), with narration, captions and
background music.

To record it again after the UI changes:

1. Start a separate demo stack on port 8001, so your real data stays out of the video:
   ```bash
   CLASSROOM_MODE=demo APP_PORT=8001 GOOGLE_CLIENT_ID= ADMIN_PASSWORD=demo1234 \
     SECRETS_DIR=/tmp/empty docker compose -p lgdemo up -d --no-build db sandbox mcp app
   ```
2. `npm i playwright && npx playwright install chromium`
3. Narration: `scenes.js` holds the text. Make one `audio/<id>.wav` per scene with
   macOS `say -v Aman -r 172`, and write their lengths to `durations.json`.
4. `node record.js` records the walkthrough. A small grey square in the bottom-right
   corner encodes the scene number, so each narration clip can be placed at the
   frame where its scene really starts (Playwright's video drifts from wall time).
5. `python3 music.py 383` writes `music.wav`. Mix it under the voice with ffmpeg's
   `sidechaincompress` so it drops while the narrator speaks.
6. `docker compose -p lgdemo down -v`
7. Rebuild `preview.gif`, the 17-second loop at the top of the main README (title, grading,
   automatic code repair, similarity check). Adjust the `trim` times if the scenes move:
   ```bash
   ffmpeg -i lab-grader-walkthrough.mp4 -filter_complex \
     "[0:v]trim=0.6:3.6,setpts=PTS-STARTPTS[a];[0:v]trim=181:186.5,setpts=PTS-STARTPTS[b];\
   [0:v]trim=283:287.5,setpts=PTS-STARTPTS[c];[0:v]trim=300:304.5,setpts=PTS-STARTPTS[d];\
   [a][b][c][d]concat=n=4:v=1:a=0,fps=10,scale=880:-1:flags=lanczos,split[x][y];\
   [x]palettegen=max_colors=128:stats_mode=diff[p];[y][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
     -loop 0 preview.gif
   ```
