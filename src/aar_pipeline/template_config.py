"""Parse AAR template structure and formatting from .docx files."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile

import xml.etree.ElementTree as ET


NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

_MEMO_RE = re.compile(r"^(TO|FROM|SUBJECT|REF):\s*(.*)", re.IGNORECASE)
_SECTION_RE = re.compile(r"^(\d+)\.\s+(.+)")


@dataclass
class FormatSpec:
    """Paragraph + run formatting extracted from a docx paragraph."""

    font_name: str | None = None
    font_size_pt: float | None = None
    bold: bool = False
    italic: bool = False
    alignment: str = "left"  # "center", "left", "right"
    space_before_twips: int = 0
    space_after_twips: int = 0
    line_spacing_twips: int = 0
    left_indent_twips: int = 0
    first_line_indent_twips: int = 0


@dataclass
class SectionDef:
    """A numbered section from the template."""

    number: int
    title: str
    description: str = ""


@dataclass
class TemplateConfig:
    """Complete template configuration parsed from a .docx file."""

    # Structure
    unit_name: str = ""
    unit_subline: str = ""
    to_field: str = ""
    from_field: str = ""
    subject_field: str = ""
    ref_field: str = ""
    sections: list[SectionDef] = field(default_factory=list)
    signature_lines: list[str] = field(default_factory=list)

    # Formatting
    page_margins: dict = field(default_factory=dict)
    title_format: FormatSpec = field(default_factory=FormatSpec)
    subtitle_format: FormatSpec = field(default_factory=FormatSpec)
    op_line_format: FormatSpec = field(default_factory=FormatSpec)
    memo_format: FormatSpec = field(default_factory=FormatSpec)
    section_header_format: FormatSpec = field(default_factory=FormatSpec)
    body_format: FormatSpec = field(default_factory=FormatSpec)
    default_font: str = "Times New Roman"
    default_size_pt: float = 12.0
    default_space_before: int = 40
    default_space_after: int = 280

    # Assets
    banner_image: bytes | None = None
    banner_width_emu: int = 0
    banner_height_emu: int = 0

    # Hashing
    content_hash: str = ""

    def _compute_hash(self) -> None:
        data = self.unit_name + "|" + "|".join(s.title for s in self.sections)
        self.content_hash = hashlib.sha256(data.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Factory: parse from .docx
    # ------------------------------------------------------------------

    @classmethod
    def from_docx(cls, path: Path) -> TemplateConfig:
        """Parse a template .docx file to extract structure, formatting, and assets."""
        cfg = cls()
        with ZipFile(path) as z:
            cfg._parse_defaults(z)
            cfg._parse_margins(z)
            cfg._parse_content(z)
            cfg._parse_banner(z)
        cfg._compute_hash()
        return cfg

    def _parse_defaults(self, z: ZipFile) -> None:
        """Extract docDefaults: default font, size, spacing."""
        with z.open("word/styles.xml") as f:
            root = ET.parse(f).getroot()

        dd = root.find(f".//{NS_W}docDefaults")
        if dd is None:
            return

        # Default run props (font, size)
        rPr = dd.find(f".//{NS_W}rPr")
        if rPr is not None:
            fonts = rPr.find(f"{NS_W}rFonts")
            if fonts is not None:
                self.default_font = (
                    fonts.get(f"{NS_W}ascii")
                    or fonts.get(f"{NS_W}hAnsi")
                    or self.default_font
                )
            sz = rPr.find(f"{NS_W}sz")
            if sz is not None:
                self.default_size_pt = int(sz.get(f"{NS_W}val", "24")) / 2

        # Default paragraph props (spacing)
        pPr = dd.find(f".//{NS_W}pPrDefault/{NS_W}pPr")
        if pPr is not None:
            sp = pPr.find(f"{NS_W}spacing")
            if sp is not None:
                b = sp.get(f"{NS_W}before")
                if b:
                    self.default_space_before = int(b)
                a = sp.get(f"{NS_W}after")
                if a:
                    self.default_space_after = int(a)

    def _parse_margins(self, z: ZipFile) -> None:
        """Extract page margins from sectPr."""
        with z.open("word/document.xml") as f:
            root = ET.parse(f).getroot()

        sectPr = root.find(f".//{NS_W}sectPr")
        if sectPr is None:
            return
        pgMar = sectPr.find(f"{NS_W}pgMar")
        if pgMar is None:
            return
        for attr in ("top", "bottom", "left", "right", "header", "footer"):
            val = pgMar.get(f"{NS_W}{attr}")
            if val:
                self.page_margins[attr] = int(val)

    def _parse_content(self, z: ZipFile) -> None:
        """Parse paragraphs for structure and formatting."""
        with z.open("word/document.xml") as f:
            root = ET.parse(f).getroot()

        body = root.find(f"{NS_W}body")
        if body is None:
            return

        paragraphs = body.findall(f"{NS_W}p")
        title_lines_found = 0
        in_memo = False
        current_section: SectionDef | None = None
        section_counter = 0

        for p in paragraphs:
            text = _para_text(p).strip()
            fmt = _extract_format(p)
            has_numPr = _has_numbering(p)

            if not text:
                continue

            # Title block: first 2 bold centered lines
            if title_lines_found < 2 and fmt.alignment == "center" and fmt.bold:
                if title_lines_found == 0:
                    self.unit_name = text
                    self.title_format = fmt
                else:
                    self.unit_subline = text
                    self.subtitle_format = fmt
                title_lines_found += 1
                continue

            # OPERATION line
            if (
                title_lines_found == 2
                and fmt.alignment == "center"
                and "OPERATION" in text.upper()
            ):
                self.op_line_format = fmt
                title_lines_found += 1
                continue

            # Location / Date lines (short bracket placeholders before MEMORANDUM)
            if (
                title_lines_found >= 2
                and not in_memo
                and current_section is None
                and text.startswith("[")
                and fmt.alignment in ("center", "right")
                and len(text) < 40
            ):
                title_lines_found += 1
                continue

            # MEMORANDUM FOR
            if text.upper() == "MEMORANDUM FOR":
                self.memo_format = fmt
                in_memo = True
                continue

            # Memo fields (handle both "TO: value" and "TO:value" with no space)
            memo_match = _MEMO_RE.match(text)
            if memo_match and in_memo:
                label = memo_match.group(1).upper()
                value = memo_match.group(2).strip()
                if label == "TO":
                    self.to_field = value
                elif label == "FROM":
                    self.from_field = value
                elif label == "SUBJECT":
                    self.subject_field = value
                elif label == "REF":
                    self.ref_field = value
                    in_memo = False
                continue

            # Section headers: either "N. TITLE" or numbered-list paragraph
            sec_match = _SECTION_RE.match(text)
            is_section_header = False
            sec_num = 0
            sec_title = ""

            if sec_match:
                # Explicit "1. GENERAL INFORMATION..." format
                is_section_header = True
                sec_num = int(sec_match.group(1))
                sec_title = sec_match.group(2).strip()
            elif has_numPr and text.isupper() and len(text) > 3:
                # Word numbered list with all-caps title (e.g., "GENERAL INFORMATION / INTRODUCTION")
                section_counter += 1
                is_section_header = True
                sec_num = section_counter
                sec_title = text

            if is_section_header:
                if current_section is not None:
                    self.sections.append(current_section)
                current_section = SectionDef(number=sec_num, title=sec_title)
                if not self.section_header_format.bold:
                    self.section_header_format = fmt
                continue

            # Section description text
            if current_section is not None:
                if current_section.description:
                    current_section.description += "\n" + text
                else:
                    current_section.description = text
                    if not self.body_format.font_name and fmt.font_size_pt:
                        self.body_format = fmt

        # Flush last section
        if current_section is not None:
            self.sections.append(current_section)

        # Extract signature from the last section's trailing description
        # Look for lines with brackets like "[Place digital signature block]"
        if self.sections:
            last = self.sections[-1]
            desc_lines = last.description.split("\n") if last.description else []
            sig_start = None
            for idx, line in enumerate(desc_lines):
                if "[" in line and "]" in line and any(
                    kw in line.lower()
                    for kw in ("signature", "name", "rank", "title", "caps")
                ):
                    sig_start = idx
                    break
            if sig_start is not None:
                sig_text = "\n".join(desc_lines[sig_start:])
                last.description = "\n".join(desc_lines[:sig_start]).strip()
                # Parse compound "[X][Y][Z]" into separate lines
                for part in sig_text.replace("][", "]\n[").split("\n"):
                    part = part.strip()
                    if part:
                        self.signature_lines.append(part)

        # Set signature defaults if none found
        if not self.signature_lines:
            self.signature_lines = [
                "[NAME IN ALL CAPS]",
                "[Rank, Title]",
            ]

    def _parse_banner(self, z: ZipFile) -> None:
        """Extract header banner image and dimensions.

        Prefers the image actually referenced in header1.xml via its
        relationship file.  Falls back to the first .png/.jpg in word/media/
        so that templates that embed images in the body still work.
        """
        NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
        IMG_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"

        # --- Step 1: find the image target via header1.xml.rels ---
        image_zip_path: str | None = None
        try:
            with z.open("word/_rels/header1.xml.rels") as f:
                rels = ET.parse(f).getroot()
            for rel in rels:
                if rel.get("Type") == IMG_TYPE:
                    target = rel.get("Target", "")
                    # Target is relative to word/, e.g. "../media/image1.png"
                    # Normalise to a zip path like "word/media/image1.png"
                    candidate = "word/" + target.lstrip("./")
                    candidate = candidate.replace("word/word/", "word/")
                    # Verify it actually exists in the archive
                    if candidate in z.namelist():
                        image_zip_path = candidate
                        break
        except KeyError:
            pass  # No header1.xml.rels — fall through to scan

        # --- Step 2: fall back to first image in word/media/ ---
        if image_zip_path is None:
            for name in z.namelist():
                if "media/" in name and name.lower().endswith((".png", ".jpg", ".jpeg")):
                    image_zip_path = name
                    break

        # --- Step 3: read the image bytes ---
        if image_zip_path is not None:
            data = z.read(image_zip_path)
            if data:  # guard against zero-length / corrupt file
                self.banner_image = data

        # --- Step 4: get dimensions from header1.xml ---
        try:
            with z.open("word/header1.xml") as f:
                hdr = ET.parse(f).getroot()
            for elem in hdr.iter():
                if elem.tag.endswith("}extent"):
                    cx = elem.get("cx")
                    cy = elem.get("cy")
                    if cx and cy:
                        w = int(cx)
                        h = int(cy)
                        if w > 0 and h > 0:
                            self.banner_width_emu = w
                            self.banner_height_emu = h
                        break
        except KeyError:
            pass

    # ------------------------------------------------------------------
    # Factory: programmatic default (TF405, backward compat)
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> TemplateConfig:
        """Construct the TF405 default config programmatically."""
        cfg = cls(
            unit_name="TASK FORCE 405",
            unit_subline="TASK FORCE 405 - SWTG - F SQUADRON",
            to_field="CENTCOM",
            from_field="OIC, F SQUADRON",
            subject_field="After Action Report [Operation Name]",
            ref_field="NIL",
            sections=[
                SectionDef(1, "GENERAL INFORMATION / INTRODUCTION",
                           "Describe the commander's mission and intent."),
                SectionDef(2, "SUMMARY",
                           "The following is information regarding the contingency itself:\n"
                           "* Deployed Location\n* Deployed Personnel\n* Duration of Deployment\n"
                           "* Contingency Purpose\n* Scope of Operation"),
                SectionDef(3, "NARRATIVE SUMMARY OF EXECUTION",
                           "Chronological timeline of all key actions from mission start to end. "
                           "Include insertion, movement, enemy contact, and extraction. "
                           "Reference grid coordinates and terrain conditions."),
                SectionDef(4, "FRIENDLY FORCES ASSESSMENT",
                           "PERSONNEL: List all friendly casualties (KIA, WIA, MIA).\n"
                           "EQUIPMENT: Status of mission-critical equipment.\n"
                           "LOGISTICS: Ammunition and key supplies expended."),
                SectionDef(5, "ENEMY FORCES ASSESSMENT",
                           "COMPOSITION: Identify enemy forces encountered.\n"
                           "STRENGTH: Estimated number of enemy combatants.\n"
                           "EQUIPMENT: Observed enemy weaponry, vehicles, equipment.\n"
                           "CASUALTIES: Confirmed enemy KIA."),
                SectionDef(6, "INTELLIGENCE ASSESSMENT",
                           "Accuracy of Pre-Mission Intelligence.\n"
                           "New Intelligence Gathered During The Operation."),
                SectionDef(7, "ANALYSIS AND RECOMMENDATIONS",
                           "SUSTAINMENT: Successful tactics, techniques, and procedures.\n"
                           "IMPROVEMENT: Challenges and actionable recommendations."),
                SectionDef(8, "CONCLUSION",
                           "Mission outcome summary."),
            ],
            signature_lines=["[NAME IN ALL CAPS]", "[Rank, Title]"],
            page_margins={
                "top": 1440, "bottom": 1440, "left": 1440, "right": 1440,
                "header": 720, "footer": 720,
            },
            title_format=FormatSpec(
                font_name=None, font_size_pt=18, bold=True, alignment="center",
                space_before_twips=0, space_after_twips=0, line_spacing_twips=276,
            ),
            subtitle_format=FormatSpec(
                font_name=None, font_size_pt=14, bold=True, alignment="center",
                space_before_twips=0, space_after_twips=0, line_spacing_twips=276,
            ),
            op_line_format=FormatSpec(
                font_name=None, font_size_pt=12, bold=True, alignment="center",
                space_before_twips=0, space_after_twips=0, line_spacing_twips=276,
            ),
            memo_format=FormatSpec(
                font_name=None, font_size_pt=18, bold=True, alignment="left",
                space_before_twips=400, space_after_twips=120, line_spacing_twips=240,
            ),
            section_header_format=FormatSpec(
                font_name=None, font_size_pt=12, bold=True, alignment="left",
                space_before_twips=0, space_after_twips=360, line_spacing_twips=240,
                left_indent_twips=720, first_line_indent_twips=-360,
            ),
            body_format=FormatSpec(
                font_name=None, font_size_pt=11, alignment="left",
                line_spacing_twips=259,
            ),
            default_font="Times New Roman",
            default_size_pt=12.0,
            default_space_before=40,
            default_space_after=280,
        )
        # Load banner from AAR_Template/ if available
        banner_path = Path(__file__).parent.parent.parent / "AAR_Template" / "header_banner.png"
        if banner_path.exists():
            cfg.banner_image = banner_path.read_bytes()
            cfg.banner_width_emu = 5731200
            cfg.banner_height_emu = 736600
        cfg._compute_hash()
        return cfg


# ------------------------------------------------------------------
# XML helpers
# ------------------------------------------------------------------

def _has_numbering(p: ET.Element) -> bool:
    """Check if a paragraph has Word numbering (numPr element)."""
    pPr = p.find(f"{NS_W}pPr")
    if pPr is None:
        return False
    return pPr.find(f"{NS_W}numPr") is not None


def _para_text(p: ET.Element) -> str:
    """Extract concatenated text from a paragraph element."""
    return "".join(t.text for t in p.iter(f"{NS_W}t") if t.text)


def _extract_format(p: ET.Element) -> FormatSpec:
    """Extract FormatSpec from a paragraph's XML properties."""
    fmt = FormatSpec()
    pPr = p.find(f"{NS_W}pPr")
    if pPr is not None:
        jc = pPr.find(f"{NS_W}jc")
        if jc is not None:
            fmt.alignment = jc.get(f"{NS_W}val", "left")

        sp = pPr.find(f"{NS_W}spacing")
        if sp is not None:
            b = sp.get(f"{NS_W}before")
            if b:
                fmt.space_before_twips = int(b)
            a = sp.get(f"{NS_W}after")
            if a:
                fmt.space_after_twips = int(a)
            ln = sp.get(f"{NS_W}line")
            if ln:
                fmt.line_spacing_twips = int(ln)

        ind = pPr.find(f"{NS_W}ind")
        if ind is not None:
            left = ind.get(f"{NS_W}left")
            if left:
                fmt.left_indent_twips = int(left)
            fl = ind.get(f"{NS_W}firstLine")
            if fl:
                fmt.first_line_indent_twips = int(fl)
            hang = ind.get(f"{NS_W}hanging")
            if hang:
                fmt.first_line_indent_twips = -int(hang)

    # Run properties from first run
    runs = p.findall(f"{NS_W}r")
    if runs:
        rPr = runs[0].find(f"{NS_W}rPr")
        if rPr is not None:
            sz = rPr.find(f"{NS_W}sz")
            if sz is not None:
                fmt.font_size_pt = int(sz.get(f"{NS_W}val", "24")) / 2

            if rPr.find(f"{NS_W}b") is not None:
                fmt.bold = True
            if rPr.find(f"{NS_W}i") is not None:
                fmt.italic = True

            fonts = rPr.find(f"{NS_W}rFonts")
            if fonts is not None:
                fmt.font_name = fonts.get(f"{NS_W}ascii") or fonts.get(f"{NS_W}hAnsi")

    return fmt
