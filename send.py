import os
import re
import smtplib
import tempfile
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import cairosvg
import markdown2

from settings import CC, HOST, MESSAGE_FILE, PORT, RECIPIENTS, SENDER


def read_markdown_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def svg_to_png(svg_path, scale=2.0):
    # Create a temporary file for the PNG image
    png_fd, png_path = tempfile.mkstemp(suffix=".png")
    os.close(png_fd)

    # Convert SVG to PNG using cairosvg
    cairosvg.svg2png(url=svg_path, write_to=png_path, scale=scale)

    return png_path


def extract_first_heading(markdown_content):
    # Regular expression to find the first heading in Markdown
    heading_pattern = re.compile(r"^\s*#{1,6}\s+(.*)$", re.MULTILINE)

    # Find the first heading match
    match = heading_pattern.search(markdown_content)

    # Return the heading text or None if not found
    return match.group(1) if match else None


def update_html_paths(html_content, paths):
    # Update HTML content to reference the cid paths instead of image paths
    for source, destination in paths.items():
        html_content = html_content.replace(
            source, "cid:" + os.path.basename(destination)
        )
    return html_content


def construct_message(
    subject,
    markdown_content,
    to_email,
    cc_email,
    image_paths=[],
    custom_styling="",
    html_prefix="",
    html_postfix="",
):
    # Convert Markdown to HTML
    converter = markdown2.Markdown(
        extras=["tables", "fenced-code-blocks", "cuddled-lists", "markdown-in-html"]
    )
    html_content = converter.convert(markdown_content)

    html_content = custom_styling + html_prefix + html_content + html_postfix

    # Create a multipart message
    message = MIMEMultipart()
    message["From"] = SENDER
    message["To"] = ", ".join(to_email)
    message["Cc"] = ", ".join(cc_email)
    message["Subject"] = subject

    # Attach images (PNG or converted from SVG)
    svg_to_png_paths = dict()
    unmodified_paths = dict()
    for image_path in image_paths:
        if image_path.lower().endswith(".svg"):
            # Convert SVG to PNG and attach
            png_path = svg_to_png(image_path)
            svg_to_png_paths[image_path] = png_path
            with open(png_path, "rb") as png_file:
                img_data = png_file.read()
                img = MIMEImage(img_data, name=os.path.basename(png_path))
                img.add_header("Content-ID", f"<{os.path.basename(image_path)}>")
                message.attach(img)
        else:
            # Attach other image formats directly
            with open(image_path, "rb") as image_file:
                img_data = image_file.read()
                img = MIMEImage(img_data, name=os.path.basename(image_path))
                img.add_header("Content-ID", f"<{os.path.basename(image_path)}>")
                message.attach(img)
                unmodified_paths[image_path] = image_path

    # Update HTML content to reference PNG paths
    html_content = update_html_paths(
        html_content, {**svg_to_png_paths, **unmodified_paths}
    )

    # Attach HTML content
    message.attach(MIMEText(html_content, "html"))

    # Clean up temporary PNG files
    for png_path in svg_to_png_paths.values():
        os.remove(png_path)

    return message


def extract_image_urls(markdown_content):
    # Regular expression to find image URLs in Markdown and HTML
    image_pattern = re.compile(
        r'!\[.*?\]\((.*?)\)|<img.*?src=["\'](.*?)["\'].*?>', re.DOTALL
    )

    # Combine matches from both patterns
    return set(
        [
            match.group(1) or match.group(2)
            for match in image_pattern.finditer(markdown_content)
        ]
    )


# Example usage
markdown_file_path = MESSAGE_FILE
markdown_content = read_markdown_file(markdown_file_path)
subject = extract_first_heading(markdown_content)
image_paths = extract_image_urls(markdown_content)

custom_styling = """
    <style>
        table {
            border-collapse: collapse;
        }
        table table tr th, table table tr td {
            border: 1px solid #ddd;;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
    </style>
    """

# For nice rendering in mail client
html_prefix = '<table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse"><tr><td></td><td width="700">'
html_postfix = "</td><td></td></tr></table>"

if subject is None:
    ValueError("Could not extract a subject")


# Construct message
message = construct_message(
    subject,
    markdown_content,
    to_email=RECIPIENTS,
    cc_email=CC,
    image_paths=image_paths,
    custom_styling=custom_styling,
    html_prefix=html_prefix,
    html_postfix=html_postfix,
)

# Connect to the SMTP server and send message
with smtplib.SMTP(HOST, PORT) as server:
    server.sendmail(from_addr=SENDER, to_addrs=RECIPIENTS + CC, msg=message.as_string())
