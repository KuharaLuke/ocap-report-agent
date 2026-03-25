---
name: generate-aar
description: Generates an After Action Report (.md + .docx) from an OCAP2 mission replay. Fetches the most recent .json.gz from the Discord channel automatically — no file attachment required.

---

# Generate AAR

Generates a formatted After Action Report (.md + .docx) from an OCAP2 Arma 3 mission replay file.

## Prerequisites

Resolve `AAR_PIPELINE_PATH` from the environment before doing anything else. If it is not set, stop and tell the user to set it to the absolute path of the cloned `ocap-report-agent` repository.

## Step 0 — Resolve the Replay File

**If the user attached a `.json.gz` file:** use its local path directly as `<file_path>`.

**Otherwise:** fetch the most recent `.json.gz` attachment from the Discord channel.
- Use `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` from the environment.
- Call `GET /channels/{channel_id}/messages?limit=100` on the Discord API v10, with `Authorization: Bot <token>`.
- Iterate messages newest-first; find the first attachment whose filename ends in `.json.gz`.
- Download that attachment URL (no auth needed — CDN URLs are public) and save it to `$AAR_PIPELINE_PATH/test_output/<filename>`. Use that path as `<file_path>`.
- If neither env var is set, or no `.json.gz` is found in the last 100 messages, stop and ask the user to attach the file directly.

## Steps

1. **Generate the briefing data:**
   ```bash
   cd "$AAR_PIPELINE_PATH" && .venv/Scripts/python.exe -m aar_pipeline.cli <file_path> --briefing-only
   ```
   On Linux/macOS use `.venv/bin/python`. Output: `$AAR_PIPELINE_PATH/test_output/briefing.txt`.

2. **Read the briefing:** Read `$AAR_PIPELINE_PATH/test_output/briefing.txt`.

3. **Write the AAR** from the briefing data:
   - Header block: unit name, operation name, location, date, MEMORANDUM FOR, TO/FROM/SUBJECT/REF
   - 8 numbered sections: General Info, Summary, Narrative, Friendly Assessment, Enemy Assessment, Intel Assessment, Analysis, Conclusion
   - Signature block — formal military prose, third person, military time, under 1000 words

4. **Save the report:** Write to `$AAR_PIPELINE_PATH/test_output/combat_report.md`.

5. **Generate the .docx:**
   ```bash
   cd "$AAR_PIPELINE_PATH" && .venv/Scripts/python.exe -m aar_pipeline.cli --convert-only
   ```

6. **Show results:** Report the `.docx` path to the user: `$AAR_PIPELINE_PATH/test_output/combat_report.docx`.

## Gotchas

- **`.venv` missing:** Run `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"` from `$AAR_PIPELINE_PATH`.
- **Discord CDN 403:** CDN URLs expire. If the download fails, ask the user to re-share the file.
- **Always `cd "$AAR_PIPELINE_PATH"`** before running CLI commands so output lands in the right place.
