"""
Export conversation to multiple formats (PDF, HTML, Markdown, CSV).
"""
import csv
import logging
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.colors import HexColor
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    log.warning("reportlab not installed. PDF export will not be available.")

try:
    import markdown2
    MARKDOWN2_AVAILABLE = True
except ImportError:
    MARKDOWN2_AVAILABLE = False
    log.warning("markdown2 not installed. HTML export with syntax highlighting will be limited.")


class ConversationExporter:
    """Handles exporting conversations to various formats."""

    def __init__(self, conversation: List[Dict[str, str]], metadata: Dict[str, Any]):
        """
        Initialize the exporter.

        Args:
            conversation: List of conversation messages
            metadata: Dictionary containing conversation metadata
                     (theme, personas, models, etc.)
        """
        self.conversation = conversation
        self.metadata = metadata

    def export_to_markdown(self, filepath: str) -> None:
        """Export conversation to Markdown format."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                # Write header
                f.write(f"# Conversation Log\n\n")
                f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**Theme:** {self.metadata.get('theme', 'N/A')}\n\n")
                f.write(f"**Participants:**\n")
                f.write(f"- {self.metadata.get('persona1', 'N/A')} ({self.metadata.get('model1', 'N/A')})\n")
                f.write(f"- {self.metadata.get('persona2', 'N/A')} ({self.metadata.get('model2', 'N/A')})\n\n")
                f.write(f"**Total Turns:** {len([m for m in self.conversation if m['role'] in ('user', 'assistant')])}\n\n")
                f.write("---\n\n")

                # Write conversation
                for msg in self.conversation:
                    persona = msg.get('persona', 'Unknown')
                    role = msg.get('role', '')
                    content = msg.get('content', '')

                    if role == 'system':
                        f.write(f"> **SYSTEM:** {content}\n\n")
                    elif role == 'narrator':
                        f.write(f"> *[Narrator]* {content}\n\n")
                    else:
                        f.write(f"### {persona}\n\n")
                        f.write(f"{content}\n\n")

            log.info(f"Conversation exported to Markdown: {filepath}")
        except Exception as e:
            log.error(f"Error exporting to Markdown: {e}")
            raise

    def export_to_html(self, filepath: str) -> None:
        """Export conversation to HTML format."""
        try:
            html_content = self._generate_html()

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)

            log.info(f"Conversation exported to HTML: {filepath}")
        except Exception as e:
            log.error(f"Error exporting to HTML: {e}")
            raise

    def _generate_html(self) -> str:
        """Generate HTML content for the conversation."""
        # Build HTML
        html = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            "<title>Conversation Log</title>",
            "<style>",
            "  body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }",
            "  .header { background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }",
            "  .header h1 { margin: 0 0 15px 0; }",
            "  .metadata { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; }",
            "  .metadata-item { background-color: rgba(255,255,255,0.1); padding: 10px; border-radius: 4px; }",
            "  .metadata-label { font-weight: bold; color: #ecf0f1; }",
            "  .conversation { background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
            "  .message { margin-bottom: 20px; padding: 15px; border-radius: 8px; border-left: 4px solid; }",
            "  .message.persona1 { background-color: #e8f5e9; border-color: #4caf50; }",
            "  .message.persona2 { background-color: #e3f2fd; border-color: #2196f3; }",
            "  .message.system { background-color: #fff3e0; border-color: #ff9800; }",
            "  .message.narrator { background-color: #f3e5f5; border-color: #9c27b0; font-style: italic; }",
            "  .message-header { font-weight: bold; margin-bottom: 8px; font-size: 1.1em; }",
            "  .message-content { white-space: pre-wrap; line-height: 1.6; }",
            "  .timestamp { color: #666; font-size: 0.9em; }",
            "</style>",
            "</head>",
            "<body>",
            "<div class='header'>",
            f"  <h1>Conversation Log</h1>",
            "  <div class='metadata'>",
            f"    <div class='metadata-item'><span class='metadata-label'>Date:</span> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
            f"    <div class='metadata-item'><span class='metadata-label'>Theme:</span> {self.metadata.get('theme', 'N/A')}</div>",
            f"    <div class='metadata-item'><span class='metadata-label'>Persona 1:</span> {self.metadata.get('persona1', 'N/A')} ({self.metadata.get('model1', 'N/A')})</div>",
            f"    <div class='metadata-item'><span class='metadata-label'>Persona 2:</span> {self.metadata.get('persona2', 'N/A')} ({self.metadata.get('model2', 'N/A')})</div>",
            f"    <div class='metadata-item'><span class='metadata-label'>Total Turns:</span> {len([m for m in self.conversation if m['role'] in ('user', 'assistant')])}</div>",
            "  </div>",
            "</div>",
            "<div class='conversation'>",
        ]

        # Add messages
        for msg in self.conversation:
            persona = msg.get('persona', 'Unknown')
            role = msg.get('role', '')
            content = msg.get('content', '').replace('<', '&lt;').replace('>', '&gt;')

            # Determine message class
            if role == 'system':
                msg_class = 'system'
                header = 'SYSTEM'
            elif role == 'narrator':
                msg_class = 'narrator'
                header = 'Narrator'
            else:
                # Determine persona class
                if persona == self.metadata.get('persona1'):
                    msg_class = 'persona1'
                else:
                    msg_class = 'persona2'
                header = persona

            html.append(f"  <div class='message {msg_class}'>")
            html.append(f"    <div class='message-header'>{header}</div>")
            html.append(f"    <div class='message-content'>{content}</div>")
            html.append(f"  </div>")

        html.extend([
            "</div>",
            "</body>",
            "</html>"
        ])

        return "\n".join(html)

    def export_to_csv(self, filepath: str) -> None:
        """Export conversation to CSV format."""
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write metadata header
                writer.writerow(['Conversation Metadata'])
                writer.writerow(['Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow(['Theme', self.metadata.get('theme', 'N/A')])
                writer.writerow(['Persona 1', self.metadata.get('persona1', 'N/A')])
                writer.writerow(['Model 1', self.metadata.get('model1', 'N/A')])
                writer.writerow(['Persona 2', self.metadata.get('persona2', 'N/A')])
                writer.writerow(['Model 2', self.metadata.get('model2', 'N/A')])
                writer.writerow([])

                # Write conversation header
                writer.writerow(['Turn', 'Persona', 'Role', 'Content'])

                # Write conversation data
                for idx, msg in enumerate(self.conversation, 1):
                    writer.writerow([
                        idx,
                        msg.get('persona', 'Unknown'),
                        msg.get('role', ''),
                        msg.get('content', '')
                    ])

            log.info(f"Conversation exported to CSV: {filepath}")
        except Exception as e:
            log.error(f"Error exporting to CSV: {e}")
            raise

    def export_to_pdf(self, filepath: str) -> None:
        """Export conversation to PDF format."""
        if not PDF_AVAILABLE:
            raise ImportError("reportlab is required for PDF export. Install with: pip install reportlab")

        try:
            doc = SimpleDocTemplate(
                filepath,
                pagesize=letter,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )

            # Build story
            story = []
            styles = getSampleStyleSheet()

            # Create custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=HexColor('#2c3e50'),
                spaceAfter=30
            )

            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=HexColor('#34495e'),
                spaceAfter=12
            )

            metadata_style = ParagraphStyle(
                'Metadata',
                parent=styles['Normal'],
                fontSize=10,
                textColor=HexColor('#7f8c8d'),
                spaceAfter=6
            )

            persona1_style = ParagraphStyle(
                'Persona1',
                parent=styles['Normal'],
                fontSize=11,
                textColor=HexColor('#27ae60'),
                leftIndent=20,
                spaceAfter=12
            )

            persona2_style = ParagraphStyle(
                'Persona2',
                parent=styles['Normal'],
                fontSize=11,
                textColor=HexColor('#2980b9'),
                leftIndent=20,
                spaceAfter=12
            )

            system_style = ParagraphStyle(
                'System',
                parent=styles['Normal'],
                fontSize=10,
                textColor=HexColor('#e67e22'),
                leftIndent=20,
                spaceAfter=12,
                fontName='Helvetica-Oblique'
            )

            # Add title
            story.append(Paragraph("Conversation Log", title_style))
            story.append(Spacer(1, 12))

            # Add metadata
            story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", metadata_style))
            story.append(Paragraph(f"<b>Theme:</b> {self.metadata.get('theme', 'N/A')}", metadata_style))
            story.append(Paragraph(f"<b>Persona 1:</b> {self.metadata.get('persona1', 'N/A')} ({self.metadata.get('model1', 'N/A')})", metadata_style))
            story.append(Paragraph(f"<b>Persona 2:</b> {self.metadata.get('persona2', 'N/A')} ({self.metadata.get('model2', 'N/A')})", metadata_style))
            story.append(Paragraph(f"<b>Total Turns:</b> {len([m for m in self.conversation if m['role'] in ('user', 'assistant')])}", metadata_style))
            story.append(Spacer(1, 20))

            # Add conversation
            for msg in self.conversation:
                persona = msg.get('persona', 'Unknown')
                role = msg.get('role', '')
                content = msg.get('content', '').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')

                if role == 'system':
                    story.append(Paragraph(f"<b>SYSTEM:</b>", heading_style))
                    story.append(Paragraph(content, system_style))
                elif role == 'narrator':
                    story.append(Paragraph(f"<b>[Narrator]</b>", heading_style))
                    story.append(Paragraph(content, system_style))
                else:
                    story.append(Paragraph(f"<b>{persona}</b>", heading_style))
                    # Choose style based on persona
                    if persona == self.metadata.get('persona1'):
                        style = persona1_style
                    else:
                        style = persona2_style
                    story.append(Paragraph(content, style))

                story.append(Spacer(1, 12))

            # Build PDF
            doc.build(story)
            log.info(f"Conversation exported to PDF: {filepath}")
        except Exception as e:
            log.error(f"Error exporting to PDF: {e}")
            raise


def export_conversation(conversation: List[Dict[str, str]],
                       metadata: Dict[str, Any],
                       filepath: str,
                       format_type: str) -> None:
    """
    Export a conversation to the specified format.

    Args:
        conversation: List of conversation messages
        metadata: Dictionary containing conversation metadata
        filepath: Path where the file should be saved
        format_type: Export format ('txt', 'json', 'md', 'html', 'csv', 'pdf')

    Raises:
        ValueError: If format_type is not supported
        ImportError: If required library for format is not installed
    """
    exporter = ConversationExporter(conversation, metadata)

    format_type = format_type.lower()

    if format_type == 'md' or format_type == 'markdown':
        exporter.export_to_markdown(filepath)
    elif format_type == 'html' or format_type == 'htm':
        exporter.export_to_html(filepath)
    elif format_type == 'csv':
        exporter.export_to_csv(filepath)
    elif format_type == 'pdf':
        exporter.export_to_pdf(filepath)
    else:
        raise ValueError(f"Unsupported export format: {format_type}")
