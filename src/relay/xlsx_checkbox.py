"""Post-process an openpyxl-written .xlsx to turn boolean cells into native Excel
checkbox cells (the modern per-cell control, Excel 365 / 2024+).

openpyxl has no API for this and drops the parts on save, so we operate on the saved
zip directly. The exact XML was reverse-engineered from a checkbox file produced by
Excel itself (see docs/checkbox_format.md), so it matches what Excel emits byte for byte.

Wiring (all four must agree):
  cell        <c ... s="IDX" t="b"><v>0|1</v></c>       boolean value, checkbox style
  styles.xml  cellXfs xf[IDX] carries an <xfpb:xfComplement i="0"/> ext
  bag part    xl/featurePropertyBag/featurePropertyBag.xml   Checkbox control chain
  plumbing    [Content_Types].xml override + workbook.xml.rels relationship

Every boolean cell we write lives in a gate column (want_to_message, referral_cleared,
draft_created, responded, interested), so "every t=\"b\" cell becomes a checkbox" is
exactly the rule we want.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

_BAG_PART = "xl/featurePropertyBag/featurePropertyBag.xml"
_BAG_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<FeaturePropertyBags xmlns="http://schemas.microsoft.com/office/spreadsheetml/2022/featurepropertybag">'
    '<bag type="Checkbox"/>'
    '<bag type="XFControls"><bagId k="CellControl">0</bagId></bag>'
    '<bag type="XFComplement"><bagId k="XFControls">1</bagId></bag>'
    '<bag type="XFComplements" extRef="XFComplementsMapperExtRef">'
    '<a k="MappedFeaturePropertyBags"><bagId>2</bagId></a></bag>'
    '</FeaturePropertyBags>'
)

# The checkbox cell style — an xf that points at the feature property bag chain.
_CHECKBOX_XF = (
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0">'
    '<extLst><ext uri="{C7286773-470A-42A8-94C5-96B5CB345126}" '
    'xmlns:xfpb="http://schemas.microsoft.com/office/spreadsheetml/2022/featurepropertybag">'
    '<xfpb:xfComplement i="0"/></ext></extLst></xf>'
)

_CT_OVERRIDE = (
    '<Override PartName="/xl/featurePropertyBag/featurePropertyBag.xml" '
    'ContentType="application/vnd.ms-excel.featurepropertybag+xml"/>'
)
_REL_TYPE = "http://schemas.microsoft.com/office/2022/11/relationships/FeaturePropertyBag"


class CheckboxInjectionError(RuntimeError):
    """Raised when the workbook XML doesn't match what we expect to patch."""


def _add_checkbox_xf(styles_xml: str) -> tuple[str, int]:
    """Append the checkbox xf to cellXfs; return (new_xml, checkbox_xf_index)."""
    m = re.search(r'<cellXfs count="(\d+)">', styles_xml)
    if not m:
        raise CheckboxInjectionError("cellXfs block not found in styles.xml")
    count = int(m.group(1))
    styles_xml = styles_xml.replace(m.group(0), f'<cellXfs count="{count + 1}">', 1)
    styles_xml = styles_xml.replace("</cellXfs>", f"{_CHECKBOX_XF}</cellXfs>", 1)
    return styles_xml, count  # new xf sits at the old count index


def _style_boolean_cells(sheet_xml: str, xf_index: int) -> str:
    """Point every boolean cell (<c ... t="b">) at the checkbox style."""
    return re.sub(
        r'(<c [^>]*?)\bt="b">',
        lambda mm: f'{mm.group(1)}s="{xf_index}" t="b">',
        sheet_xml,
    )


def _add_content_type(ct_xml: str) -> str:
    if _BAG_PART in ct_xml:
        return ct_xml
    return ct_xml.replace("</Types>", f"{_CT_OVERRIDE}</Types>", 1)


def _add_workbook_rel(rels_xml: str) -> str:
    if _REL_TYPE in rels_xml:
        return rels_xml
    used = {int(n) for n in re.findall(r'Id="rId(\d+)"', rels_xml)}
    rid = f"rId{max(used) + 1 if used else 1}"
    rel = (
        f'<Relationship Id="{rid}" Type="{_REL_TYPE}" '
        f'Target="featurePropertyBag/featurePropertyBag.xml"/>'
    )
    return rels_xml.replace("</Relationships>", f"{rel}</Relationships>", 1)


def inject_checkboxes(path: str | Path) -> bool:
    """Rewrite `path` in place so its boolean cells render as Excel checkboxes.

    Returns True if checkboxes were injected, False if the workbook had no boolean
    cells (nothing to do). Raises CheckboxInjectionError if the XML is unexpectedly
    shaped, so callers can fall back to plain booleans rather than ship a broken file.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as zin:
        names = zin.namelist()
        data = {name: zin.read(name) for name in names}

    sheet_names = [n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
    if not any(b't="b"' in data[n] for n in sheet_names):
        return False  # no boolean cells -> nothing to convert

    styles_name = "xl/styles.xml"
    if styles_name not in data:
        raise CheckboxInjectionError("styles.xml missing from workbook")
    styles_xml, xf_index = _add_checkbox_xf(data[styles_name].decode("utf-8"))
    data[styles_name] = styles_xml.encode("utf-8")

    for name in sheet_names:
        data[name] = _style_boolean_cells(data[name].decode("utf-8"), xf_index).encode("utf-8")

    data[_BAG_PART] = _BAG_XML.encode("utf-8")
    data["[Content_Types].xml"] = _add_content_type(
        data["[Content_Types].xml"].decode("utf-8")).encode("utf-8")
    data["xl/_rels/workbook.xml.rels"] = _add_workbook_rel(
        data["xl/_rels/workbook.xml.rels"].decode("utf-8")).encode("utf-8")

    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        # Keep original part order, then append the new bag part.
        for name in names:
            zout.writestr(name, data[name])
        zout.writestr(_BAG_PART, data[_BAG_PART])
    shutil.move(str(tmp), str(path))
    return True
