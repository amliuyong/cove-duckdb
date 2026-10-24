# Colvenna Isle promotional video source

Seven editable HTML scenes cover the API, durable storage, pipelines, Query Editor and Admin Console. The scenes, narration and shared palette accompany the delivered GIF and MP4. The product screens are illustrative mock-ups; speech is AI-generated.

This is the original product video's scene design updated for Issue #19. The Colvenna C mark replaces every previous brand mark, and the name, visible copy, narration and subtitles use the independent product brand. Promotion contains no third-party engine name.

The root [brand generator](../../../scripts/render_brand.py) owns the SVG mark geometry. When changing the mark, synchronize these scenes with its generated icon.

## Regenerate outside the checkout

Use the installed [html-to-explainer-video workflow](https://github.com/amliuyong/html-to-explainer-video) with its Python, Node.js, Chromium and ffmpeg dependencies. Keep credentials, audio caches and intermediate frames outside the checkout. The workflow's render-channel confirmation must be completed before rendering.

Copy this directory into a fresh external project directory, then run:

```bash
python3 <skill>/scripts/tts_build.py --project <project>
python3 <skill>/scripts/timeline_build.py --project <project>
python3 <skill>/scripts/subs.py --project <project>
python3 <skill>/scripts/check_beats_refs.py --project <project>
python3 <skill>/scripts/lint_frames.py --project <project>
node <skill>/scripts/check_layout.mjs <project>
node <skill>/scripts/render_video.mjs <project> --png-fast --quality 1080p \
  --fps 30 --shutter 0 --workers 4 --audio <project>/audio/narration-full.mp3
python3 <skill>/scripts/qc_check.py --project <project>
```

The selected voice is the original English `Andy_v3.1` voice through the workflow's configured provider. Credential access belongs to the provider helper; credentials are never stored here.

After inspecting the rendered contact sheet, copy the MP4 to `docs/assets/promo.mp4` and generate its silent GIF:

```bash
ffmpeg -i <project>/out/colvenna-isle-promo.mp4 \
  -vf "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" \
  -loop 0 docs/assets/promo.gif
```

Scene source uses the project Apache-2.0 license. The bundled GSAP 3.13.0 retains its copyright and [standard license](https://gsap.com/standard-license); see [third-party notices](../../../THIRD_PARTY_NOTICES.md).
