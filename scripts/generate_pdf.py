import argparse
import os
import re
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib.colors import HexColor

def md_to_html(text):
    # Handle bold (**text**)
    count = 0
    def bold_repl(match):
        nonlocal count
        count += 1
        return "<b>" if count % 2 != 0 else "</b>"
    text = re.sub(r'\*\*', bold_repl, text)
    
    # Handle italic (*text*)
    count_i = 0
    def italic_repl(match):
        nonlocal count_i
        count_i += 1
        return "<i>" if count_i % 2 != 0 else "</i>"
    text = re.sub(r'\*', italic_repl, text)
    
    # Handle links [text](url) -> <a href="url">text</a>
    # If url starts with #, just keep the text to avoid reportlab errors
    def link_repl(match):
        text_part = match.group(1)
        url_part = match.group(2)
        if url_part.startswith('#'):
            return text_part
        return f'<a href="{url_part}" color="blue">{text_part}</a>'
    
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link_repl, text)
    
    return text

from reportlab.platypus import Image, Table, TableStyle
from reportlab.lib import colors

def generate_pdf(input_md, output_pdf):
    input_path = Path(input_md)
    output_path = Path(output_pdf)
    if not input_path.exists():
        print(f"Error: {input_path} not found.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(str(output_path), pagesize=LETTER,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=50)
    
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=HexColor('#0056b3'),
        alignment=TA_CENTER,
        spaceAfter=40
    )
    
    h2_style = ParagraphStyle(
        'H2Style',
        parent=styles['Heading2'],
        fontSize=20,
        textColor=HexColor('#0056b3'),
        spaceBefore=25,
        spaceAfter=15,
        borderPadding=(10, 0, 10, 0),
        borderWidth=0,
        borderColor=colors.white
    )
    
    h3_style = ParagraphStyle(
        'H3Style',
        parent=styles['Heading3'],
        fontSize=16,
        textColor=HexColor('#333'),
        spaceBefore=15,
        spaceAfter=10
    )
    
    body_style = ParagraphStyle(
        'BodyStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=12
    )

    box_style = ParagraphStyle(
        'BoxStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=HexColor('#444'),
        backColor=HexColor('#f8f9fa'),
        borderPadding=15,
        borderWidth=1,
        borderColor=HexColor('#dee2e6'),
        borderRadius=5,
        spaceBefore=20,
        spaceAfter=20
    )

    content = []
    
    with input_path.open('r', encoding='utf-8') as f:
        lines = f.readlines()

    in_list = False
    list_items = []
    in_box = False
    box_lines = []

    for line in lines:
        raw_line = line.strip()
        
        if raw_line.startswith('::: box'):
            in_box = True
            continue
        elif raw_line.startswith(':::') and in_box:
            # Render the box
            box_text = "<br/>".join([md_to_html(l) for l in box_lines])
            content.append(Paragraph(box_text, box_style))
            box_lines = []
            in_box = False
            continue
        
        if in_box:
            box_lines.append(line.rstrip())
            continue

        # Handle Images ![alt](path)
        img_match = re.search(r'!\[.*?\]\((.*?)\)', raw_line)
        if img_match:
            img_path = img_match.group(1)
            # Handle absolute or relative paths
            if not os.path.isabs(img_path):
                # Try relative to docs/
                try_path = str(input_path.parent / img_path)
                if not os.path.exists(try_path):
                    # Try relative to root
                    try_path = img_path
                img_path = try_path
            
            if os.path.exists(img_path):
                try:
                    img = Image(img_path, width=450, height=300, kind='proportional')
                    content.append(img)
                    content.append(Spacer(1, 15))
                    continue
                except:
                    pass

        # Flush list if line is not a list item
        is_list_item = (raw_line.startswith('- ') or raw_line.startswith('* ') or (raw_line and raw_line[0].isdigit() and re.match(r'^\d+\.\s', raw_line)))
        
        if in_list and not is_list_item:
            if list_items:
                content.append(ListFlowable(
                    [ListItem(Paragraph(item, body_style)) for item in list_items],
                    bulletType='bullet',
                    leftIndent=30
                ))
                content.append(Spacer(1, 10))
            list_items = []
            in_list = False

        if not raw_line:
            content.append(Spacer(1, 8))
            continue

        if raw_line.startswith('# '):
            content.append(Paragraph(md_to_html(raw_line[2:]), title_style))
        elif raw_line.startswith('## '):
            content.append(Paragraph(md_to_html(raw_line[3:]), h2_style))
        elif raw_line.startswith('### '):
            content.append(Paragraph(md_to_html(raw_line[4:]), h3_style))
        elif is_list_item:
            in_list = True
            item_text = re.sub(r'^([-*]|\d+\.)\s+', '', raw_line)
            list_items.append(md_to_html(item_text))
        elif raw_line.startswith('---'):
            content.append(Spacer(1, 15))
        else:
            content.append(Paragraph(md_to_html(raw_line), body_style))

    # Final list flush
    if in_list and list_items:
        content.append(ListFlowable(
            [ListItem(Paragraph(item, body_style)) for item in list_items],
            bulletType='bullet',
            leftIndent=30
        ))

    try:
        doc.build(content)
        print(f"Successfully generated {output_path}")
    except Exception as e:
        print(f"Failed to build PDF: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a markdown report file to PDF.")
    parser.add_argument("input_md", help="Path to the markdown source file.")
    parser.add_argument("output_pdf", nargs="?", help="Optional output PDF path.")
    args = parser.parse_args()

    input_path = Path(args.input_md)
    output_path = Path(args.output_pdf) if args.output_pdf else input_path.with_suffix(".pdf")
    generate_pdf(str(input_path), str(output_path))
