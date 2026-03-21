---
name: generate-aar
description: Generates an After Action Report (.md + .docx) from an attached OCAP2 mission replay file. Must only be used when a user provides a .json.gz file.

---

# Generate AAR

Generates a formatted After Action Report (.md + .docx) from an OCAP2 Arma 3 mission replay file. You will use the Python pipeline to extract the data, then write the report yourself based on that data.

## Execution Rules (CRITICAL)

1. **Check for Attachment:** Before doing anything, check the user's message. Did they attach a file ending in `.json.gz`?
2. **Missing File:** If there is NO `.json.gz` file attached, DO NOT execute any commands. Reply: "Please attach the OCAP2 `.json.gz` replay file to your message so I can generate the report."
3. **Use Attachment Path:** If the file IS attached, use the local file path provided in the context as `<file_path>` for the pipeline.

## Prerequisites

Before running any commands, resolve the repository path:

1. Read the `AAR_PIPELINE_PATH` environment variable — this is the absolute path to the cloned `405missionreport` repository on disk.
2. If `AAR_PIPELINE_PATH` is **not set**, stop immediately and tell the user: "The `AAR_PIPELINE_PATH` environment variable is not set. Please set it to the absolute path of the cloned AAR pipeline repository (e.g. `export AAR_PIPELINE_PATH=/path/to/405missionreport`) and try again."
3. All subsequent paths and commands use `$AAR_PIPELINE_PATH` as their base.

## Steps

1. **Generate the briefing data:**
   Run the following command, replacing `<file_path>` with the path of the attached file:
   ```bash
   cd "$AAR_PIPELINE_PATH" && .venv/Scripts/python.exe -m aar_pipeline.cli <file_path> --briefing-only
   ```
   This parses the OCAP2 replay and produces `$AAR_PIPELINE_PATH/test_output/briefing.txt`.

2. **Read the briefing:**
   Read `$AAR_PIPELINE_PATH/test_output/briefing.txt` — this contains structured mission data (friendly forces, timeline, engagements, enemy composition, casualties).

3. **Write the AAR:**
   Using the briefing data, write a complete After Action Report following this format:
   - Header block: unit name, operation name, location, date, MEMORANDUM FOR, TO/FROM/SUBJECT/REF
   - 8 numbered sections: General Info, Summary, Narrative, Friendly Assessment, Enemy Assessment, Intel Assessment, Analysis, Conclusion
   - Signature block at the end
   - Formal military prose, third person, military time, grid references
   - Under 1000 words

4. **Save the report:**
   Write the AAR to `$AAR_PIPELINE_PATH/test_output/combat_report.md`.

5. **Generate the .docx:**
   Run:
   ```bash
   cd "$AAR_PIPELINE_PATH" && .venv/Scripts/python.exe -m aar_pipeline.cli --convert-only
   ```
   This converts the markdown report to a formatted Word document at `$AAR_PIPELINE_PATH/test_output/combat_report.docx`.

6. **Show results:**
   Tell the user the report is complete and provide the full path to the `.docx`: `$AAR_PIPELINE_PATH/test_output/combat_report.docx`.

## Gotchas

- **`AAR_PIPELINE_PATH` not set:** The skill will not work without this variable. See Prerequisites above.
- **`.venv` not present:** If the virtual environment is missing, run `python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"` from inside `$AAR_PIPELINE_PATH`.
- **Windows vs. Linux/macOS:** `.venv/Scripts/python.exe` is the Windows path. On Linux/macOS use `.venv/bin/python` instead.
- **`--convert-only` requires Step 4 to be done first:** This command reads `test_output/combat_report.md`. If Step 4 was skipped or the file wasn't saved to the correct path, it will fail.
- **Output path is relative to repo root:** The CLI writes output to `./test_output/` relative to CWD — always `cd "$AAR_PIPELINE_PATH"` before running commands so output lands in the right place.
