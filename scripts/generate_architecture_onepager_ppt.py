from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


SLIDE_CX = 12192000
SLIDE_CY = 6858000
EMU_PER_INCH = 914400


def emu(value: float) -> int:
    return int(value * EMU_PER_INCH)


def xml_text(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def paragraph_xml(
    text: str,
    *,
    font_size: int = 1800,
    color: str = "FFFFFF",
    bold: bool = False,
    align: str = "l",
) -> str:
    bold_attr = ' b="1"' if bold else ""
    safe = xml_text(text)
    return (
        f'<a:p>'
        f'<a:pPr algn="{align}" marL="0" indent="0"/>'
        f'<a:r>'
        f'<a:rPr lang="zh-CN" sz="{font_size}"{bold_attr}>'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:latin typeface="Aptos"/>'
        f'<a:ea typeface="Microsoft YaHei"/>'
        f'<a:cs typeface="Arial"/>'
        f'</a:rPr>'
        f'<a:t>{safe}</a:t>'
        f'</a:r>'
        f'<a:endParaRPr lang="zh-CN" sz="{font_size}"/>'
        f'</a:p>'
    )


def shape_xml(
    shape_id: int,
    name: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str | None,
    line: str | None,
    line_width: int = 12700,
    round_rect: bool = False,
    paragraphs: list[dict] | None = None,
    is_textbox: bool = False,
    inset_left: int = 152400,
    inset_top: int = 91440,
    inset_right: int = 152400,
    inset_bottom: int = 91440,
    anchor: str = "ctr",
) -> str:
    geom = "roundRect" if round_rect else "rect"
    txbox_attr = ' txBox="1"' if is_textbox else ""
    x_emu = emu(x)
    y_emu = emu(y)
    w_emu = emu(w)
    h_emu = emu(h)

    if fill:
        fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
    else:
        fill_xml = "<a:noFill/>"

    if line:
        line_xml = (
            f'<a:ln w="{line_width}">'
            f'<a:solidFill><a:srgbClr val="{line}"/></a:solidFill>'
            f'</a:ln>'
        )
    else:
        line_xml = '<a:ln><a:noFill/></a:ln>'

    if paragraphs:
        body = "".join(
            paragraph_xml(
                item["text"],
                font_size=item.get("font_size", 1800),
                color=item.get("color", "FFFFFF"),
                bold=item.get("bold", False),
                align=item.get("align", "l"),
            )
            for item in paragraphs
        )
    else:
        body = "<a:p/>"

    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="{xml_text(name)}"/>
        <p:cNvSpPr{txbox_attr}/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm>
          <a:off x="{x_emu}" y="{y_emu}"/>
          <a:ext cx="{w_emu}" cy="{h_emu}"/>
        </a:xfrm>
        <a:prstGeom prst="{geom}"><a:avLst/></a:prstGeom>
        {fill_xml}
        {line_xml}
      </p:spPr>
      <p:txBody>
        <a:bodyPr wrap="square" lIns="{inset_left}" tIns="{inset_top}" rIns="{inset_right}" bIns="{inset_bottom}" anchor="{anchor}"/>
        <a:lstStyle/>
        {body}
      </p:txBody>
    </p:sp>
    """.strip()


def build_slide_xml() -> str:
    shapes: list[str] = []
    shape_id = 2

    def add(**kwargs):
        nonlocal shape_id
        shapes.append(shape_xml(shape_id, **kwargs))
        shape_id += 1

    # Background
    add(name="Background", x=0.0, y=0.0, w=13.333, h=7.5, fill="0F1720", line=None, paragraphs=None)

    # Title and subtitle
    add(
        name="Title",
        x=0.62,
        y=0.42,
        w=8.6,
        h=0.48,
        fill=None,
        line=None,
        is_textbox=True,
        anchor="ctr",
        inset_left=0,
        inset_top=0,
        inset_right=0,
        inset_bottom=0,
        paragraphs=[
            {"text": "TDA-TDP Agent Architecture / 当前版分层方案", "font_size": 2800, "color": "FFFFFF", "bold": True},
        ],
    )
    add(
        name="Subtitle",
        x=0.64,
        y=0.92,
        w=10.2,
        h=0.34,
        fill=None,
        line=None,
        is_textbox=True,
        anchor="ctr",
        inset_left=0,
        inset_top=0,
        inset_right=0,
        inset_bottom=0,
        paragraphs=[
            {
                "text": "Semantic-first · LLM Understanding · Planner / Executor / Reviewer Orchestration",
                "font_size": 1250,
                "color": "C7D2DB",
                "bold": False,
            }
        ],
    )
    add(name="AccentLine", x=0.64, y=1.28, w=1.45, h=0.06, fill="F4A261", line=None, paragraphs=None)

    # Panels
    add(name="LeftPanel", x=0.56, y=1.5, w=5.48, h=5.36, fill="162635", line="294255", line_width=19050, round_rect=True, paragraphs=None)
    add(name="RightPanel", x=6.25, y=1.5, w=6.52, h=5.36, fill="162635", line="294255", line_width=19050, round_rect=True, paragraphs=None)

    # Panel headers
    add(
        name="LeftHeader",
        x=0.84,
        y=1.72,
        w=3.5,
        h=0.32,
        fill=None,
        line=None,
        is_textbox=True,
        inset_left=0,
        inset_top=0,
        inset_right=0,
        inset_bottom=0,
        paragraphs=[{"text": "Layered Architecture / 分层结构", "font_size": 1650, "color": "F9FAFB", "bold": True}],
    )
    add(
        name="RightHeader",
        x=6.54,
        y=1.72,
        w=3.8,
        h=0.32,
        fill=None,
        line=None,
        is_textbox=True,
        inset_left=0,
        inset_top=0,
        inset_right=0,
        inset_bottom=0,
        paragraphs=[{"text": "Run Flow / Agent 运行流程", "font_size": 1650, "color": "F9FAFB", "bold": True}],
    )

    # Left cards
    cards = [
        (
            2.08,
            "243E5A",
            "7FA8D6",
            "Interface & Orchestration / 接入与编排",
            "ChatView · WebSocket · chat_v3 · MultiAgentOrchestrator",
        ),
        (
            3.18,
            "175965",
            "67C5C5",
            "Understanding & Planning / 智能理解与规划",
            "Semantic Grounding · Understanding Agent · Runtime Context · Planner",
        ),
        (
            4.28,
            "6C4322",
            "F3A261",
            "Execution & Review / 执行与审查",
            "Executor · semantic_query first · SQL fallback · Reviewer · Replan",
        ),
        (
            5.38,
            "2A3948",
            "A6B3C2",
            "Semantic Model & Data Assets / 语义模型与数据资产",
            "YAML semantics · metrics / dimensions · metadata · 28 tables · tools",
        ),
    ]
    for y, fill, line, title, body in cards:
        add(
            name=title,
            x=0.84,
            y=y,
            w=4.92,
            h=0.84,
            fill=fill,
            line=line,
            line_width=12700,
            round_rect=True,
            paragraphs=[
                {"text": title, "font_size": 1500, "color": "FFFFFF", "bold": True},
                {"text": body, "font_size": 1040, "color": "DCE5EC", "bold": False},
            ],
            anchor="ctr",
        )

    # Right flow nodes
    flow_nodes = [
        ("1 Semantic Asset Retrieval / 召回候选语义资产", "203544", "7FA8D6"),
        ("2 Understanding Layer / 结构化业务意图", "174A58", "67C5C5"),
        ("3 Runtime Context / 约束与校验", "1E3B46", "8FC3B2"),
        ("4 Planner / 生成带 semantic binding 的计划", "4D3B23", "F3A261"),
        ("5 Executor / 优先 semantic_query，必要时 SQL", "4A2F24", "E59472"),
        ("6 Reviewer / 审查证据并可触发 replan", "2A3948", "A6B3C2"),
    ]
    current_y = 2.02
    for idx, (title, fill, line) in enumerate(flow_nodes):
        add(
            name=f"Flow{idx+1}",
            x=6.55,
            y=current_y,
            w=5.9,
            h=0.46,
            fill=fill,
            line=line,
            line_width=12700,
            round_rect=True,
            paragraphs=[{"text": title, "font_size": 1150, "color": "FFFFFF", "bold": True, "align": "ctr"}],
            anchor="ctr",
        )
        current_y += 0.54
        if idx < len(flow_nodes) - 1:
            add(
                name=f"Arrow{idx+1}",
                x=9.22,
                y=current_y - 0.06,
                w=0.5,
                h=0.12,
                fill=None,
                line=None,
                is_textbox=True,
                inset_left=0,
                inset_top=0,
                inset_right=0,
                inset_bottom=0,
                paragraphs=[{"text": "↓", "font_size": 1600, "color": "C7D2DB", "bold": True, "align": "ctr"}],
            )

    # Note box
    add(
        name="RelationshipNote",
        x=6.55,
        y=5.42,
        w=5.9,
        h=1.08,
        fill="111C26",
        line="375266",
        line_width=12700,
        round_rect=True,
        paragraphs=[
            {"text": "Key Relationships / 关键关系", "font_size": 1320, "color": "F9FAFB", "bold": True},
            {"text": "• 语义模型 = business contract，不再只是可选 tool", "font_size": 1000, "color": "DDE6ED"},
            {"text": "• Planner 规划业务语义任务，Executor 执行事实取证", "font_size": 1000, "color": "DDE6ED"},
            {"text": "• 数据资产为理解层提供 grounding，Reviewer 保证准确率", "font_size": 1000, "color": "DDE6ED"},
        ],
        anchor="t",
    )

    # Footer badges
    badges = [
        (0.82, "Semantic-first / 语义优先", "163744", "67C5C5"),
        (4.55, "Grounded Planning / 有约束规划", "3E3320", "F3A261"),
        (8.56, "Evidence & Replan / 证据与重规划", "2B3947", "A6B3C2"),
    ]
    for x, text, fill, line in badges:
        add(
            name=text,
            x=x,
            y=7.0,
            w=3.28,
            h=0.34,
            fill=fill,
            line=line,
            line_width=12700,
            round_rect=True,
            paragraphs=[{"text": text, "font_size": 980, "color": "FFFFFF", "bold": True, "align": "ctr"}],
            anchor="ctr",
        )

    sp_tree = "\n".join(shapes)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld name="TDA-TDP Agent Architecture">
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      {sp_tree}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"""


def content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>
  <Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>
  <Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>
"""


def root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def app_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>OpenAI Codex</Application>
  <PresentationFormat>Widescreen</PresentationFormat>
  <Slides>1</Slides>
  <Notes>0</Notes>
  <HiddenSlides>0</HiddenSlides>
  <MMClips>0</MMClips>
  <ScaleCrop>false</ScaleCrop>
  <HeadingPairs>
    <vt:vector size="2" baseType="variant">
      <vt:variant><vt:lpstr>主题</vt:lpstr></vt:variant>
      <vt:variant><vt:i4>1</vt:i4></vt:variant>
    </vt:vector>
  </HeadingPairs>
  <TitlesOfParts>
    <vt:vector size="1" baseType="lpstr">
      <vt:lpstr>TDA-TDP Agent Architecture</vt:lpstr>
    </vt:vector>
  </TitlesOfParts>
  <Company>OpenAI</Company>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0000</AppVersion>
</Properties>
"""


def core_xml() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>TDA-TDP Agent Architecture One Pager</dc:title>
  <dc:creator>OpenAI Codex</dc:creator>
  <cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""


def presentation_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rId1"/>
  </p:sldMasterIdLst>
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId2"/>
  </p:sldIdLst>
  <p:sldSz cx="{SLIDE_CX}" cy="{SLIDE_CY}" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
  <p:defaultTextStyle>
    <a:defPPr/>
    <a:lvl1pPr marL="0" indent="0">
      <a:defRPr sz="1800"/>
    </a:lvl1pPr>
  </p:defaultTextStyle>
</p:presentation>
"""


def presentation_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>
</Relationships>
"""


def slide_master_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld name="Master">
    <p:bg>
      <p:bgPr><a:solidFill><a:srgbClr val="0F1720"/></a:solidFill><a:effectLst/></p:bgPr>
    </p:bg>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst>
    <p:sldLayoutId id="1" r:id="rId1"/>
  </p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle>
      <a:lvl1pPr marL="0" indent="0"><a:defRPr sz="2800" b="1"/></a:lvl1pPr>
    </p:titleStyle>
    <p:bodyStyle>
      <a:lvl1pPr marL="0" indent="0"><a:defRPr sz="1800"/></a:lvl1pPr>
    </p:bodyStyle>
    <p:otherStyle>
      <a:defPPr/>
      <a:lvl1pPr marL="0" indent="0"><a:defRPr sz="1800"/></a:lvl1pPr>
    </p:otherStyle>
  </p:txStyles>
</p:sldMaster>
"""


def slide_master_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>
"""


def slide_layout_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             type="blank" preserve="1">
  <p:cSld name="Blank">
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>
"""


def slide_layout_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"""


def slide_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>
"""


def theme_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="TDA Theme">
  <a:themeElements>
    <a:clrScheme name="TDA Colors">
      <a:dk1><a:srgbClr val="0F1720"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="162635"/></a:dk2>
      <a:lt2><a:srgbClr val="DDE6ED"/></a:lt2>
      <a:accent1><a:srgbClr val="67C5C5"/></a:accent1>
      <a:accent2><a:srgbClr val="F3A261"/></a:accent2>
      <a:accent3><a:srgbClr val="7FA8D6"/></a:accent3>
      <a:accent4><a:srgbClr val="A6B3C2"/></a:accent4>
      <a:accent5><a:srgbClr val="D66A4F"/></a:accent5>
      <a:accent6><a:srgbClr val="8FC3B2"/></a:accent6>
      <a:hlink><a:srgbClr val="5B9BD5"/></a:hlink>
      <a:folHlink><a:srgbClr val="C0504D"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="TDA Fonts">
      <a:majorFont>
        <a:latin typeface="Aptos"/>
        <a:ea typeface="Microsoft YaHei"/>
        <a:cs typeface="Arial"/>
      </a:majorFont>
      <a:minorFont>
        <a:latin typeface="Aptos"/>
        <a:ea typeface="Microsoft YaHei"/>
        <a:cs typeface="Arial"/>
      </a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="TDA Format">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="accent1"/></a:solidFill>
        <a:solidFill><a:schemeClr val="accent2"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="25400" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:ln>
        <a:ln w="38100" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="lt1"/></a:solidFill>
        <a:solidFill><a:schemeClr val="lt2"/></a:solidFill>
        <a:solidFill><a:schemeClr val="dk1"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
  <a:objectDefaults/>
  <a:extraClrSchemeLst/>
</a:theme>
"""


def pres_props_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>
"""


def view_props_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
          xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          lastView="sldView">
  <p:normalViewPr>
    <p:restoredLeft sz="15620"/>
    <p:restoredTop sz="94660"/>
  </p:normalViewPr>
  <p:slideViewPr>
    <p:cSldViewPr snapToGrid="1" snapToObjects="1">
      <p:guideLst/>
    </p:cSldViewPr>
  </p:slideViewPr>
  <p:notesTextViewPr>
    <p:cViewPr varScale="1">
      <p:scale sx="100" sy="100"/>
      <p:origin x="0" y="0"/>
    </p:cViewPr>
  </p:notesTextViewPr>
  <p:gridSpacing cx="72008" cy="72008"/>
</p:viewPr>
"""


def table_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>
"""


def generate_pptx(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml())
        zf.writestr("_rels/.rels", root_rels_xml())
        zf.writestr("docProps/app.xml", app_xml())
        zf.writestr("docProps/core.xml", core_xml())
        zf.writestr("ppt/presentation.xml", presentation_xml())
        zf.writestr("ppt/_rels/presentation.xml.rels", presentation_rels_xml())
        zf.writestr("ppt/presProps.xml", pres_props_xml())
        zf.writestr("ppt/viewProps.xml", view_props_xml())
        zf.writestr("ppt/tableStyles.xml", table_styles_xml())
        zf.writestr("ppt/slideMasters/slideMaster1.xml", slide_master_xml())
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels_xml())
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout_xml())
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", slide_layout_rels_xml())
        zf.writestr("ppt/theme/theme1.xml", theme_xml())
        zf.writestr("ppt/slides/slide1.xml", build_slide_xml())
        zf.writestr("ppt/slides/_rels/slide1.xml.rels", slide_rels_xml())


if __name__ == "__main__":
    target = Path("TDA-Agent-Architecture-OnePager.pptx")
    generate_pptx(target)
    print(target.resolve())
