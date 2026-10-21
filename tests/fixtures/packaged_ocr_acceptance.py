"""Check the frozen desktop bridge includes its optional OCR image decoder."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

binary=Path(sys.argv[1]).resolve()
request=json.dumps({"id":1,"method":"adapter.status","params":{}})+"\n"
completed=subprocess.run([str(binary)],input=request,capture_output=True,text=True,timeout=45,check=False)
if completed.returncode:
    raise SystemExit(f"Frozen bridge exited {completed.returncode}: {completed.stderr[-1000:]}")
responses=[json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
if len(responses)!=1 or responses[0].get("id")!=1:
    raise SystemExit(f"Unexpected frozen bridge response: {completed.stdout[-1000:]}")
ocr=responses[0].get("result",{}).get("ocr",{})
if ocr.get("imageDecoder")!="Pillow" or not ocr.get("imageDecoderVersion"):
    raise SystemExit(f"Frozen bridge lacks the OCR image decoder: {ocr!r}")
print(f"Frozen OCR preflight available with Pillow {ocr['imageDecoderVersion']}; Tesseract available={ocr['available']}")
