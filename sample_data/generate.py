"""
Build the sample resume files in this directory.

Run with: python sample_data/generate.py

The generated files are committed, so a fresh clone can run the tests and the
Phase 7 seed command without regenerating anything. This script exists so the
fixtures are reproducible and reviewable rather than opaque binaries.

The PDF is written by hand rather than with a library: the project needs to
*read* PDFs, not write them, and adding reportlab purely to build test
fixtures is not worth the dependency.
"""

import os
import sys

from docx import Document


HERE = os.path.dirname(os.path.abspath(__file__))

# Running this as a script puts sample_data/ on the path, not the project
# root, so the package import below needs the parent directory added.
sys.path.insert(0, os.path.dirname(HERE))

from sample_data import profiles  # noqa: E402

# A 792pt page with text starting at y=750 and 14pt leading fits this many
# lines before running off the bottom.
LINES_PER_PAGE = 50


def _content_stream(lines):
    """The text-drawing operators for a single page."""
    content = "BT\n/F1 11 Tf\n50 750 Td\n14 TL\n"
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        content += f"({escaped}) Tj\nT*\n"
    content += "ET"
    return content.encode("latin-1", "replace")


def build_pdf(lines):
    """
    A minimal PDF with a Helvetica text layer, split across pages as needed.

    Object numbering is: 1 catalog, 2 page tree, then a page object and a
    content object for each page, then the shared font object last.
    """
    pages = [
        lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)
    ] or [[]]

    first_page_obj = 3
    font_obj = first_page_obj + 2 * len(pages)

    kids = " ".join(f"{first_page_obj + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
    ]

    for index, page_lines in enumerate(pages):
        content_obj = first_page_obj + 2 * index + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_obj} 0 R "
                f"/Resources << /Font << /F1 {font_obj} 0 R >> >> >>"
            ).encode()
        )
        stream = _content_stream(page_lines)
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {size} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def build_docx(path, lines):
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(path)

# The long CV used for manual testing. Two pages, so it also exercises the
# multi-page loop in applications/parsing.py.
LONG_RESUME = [
    "Nour Abdelrahman",
    "Senior Software Engineer - Khartoum, Sudan",
    "nour.abdelrahman@example.com | +249 91 555 0142",
    "",
    "SUMMARY",
    "Software engineer with seven years building and operating web systems for",
    "telecom and financial services customers across Sudan and the Gulf. Most of",
    "my work is server-side Python, with enough frontend and infrastructure to",
    "carry a feature from database schema through to production.",
    "",
    "EXPERIENCE",
    "",
    "Senior Software Engineer, Sudatel Telecom - Khartoum (2022 to present)",
    "Designed and built REST APIs with Django and Django REST Framework serving",
    "around forty thousand daily active subscribers on the self-service portal",
    "Rewrote the prepaid billing reconciliation job, cutting its nightly runtime",
    "from just over four hours down to twenty minutes",
    "Modelled the subscription and invoicing schema in PostgreSQL and added the",
    "partial indexes that removed the three slowest queries from the dashboard",
    "Introduced continuous integration with GitHub Actions running the full test",
    "suite and linting on every pull request before merge",
    "Led the migration from a single virtual machine to containerised deployments",
    "with Docker Compose, including the rollback procedure",
    "Mentored three junior engineers through structured code review",
    "",
    "Software Engineer, Bank of Khartoum - Khartoum (2019 to 2022)",
    "Built internal reporting services in Python consumed by the branch network",
    "Wrote the integration layer against a legacy SOAP core banking system and",
    "wrapped it behind a clean HTTP interface the rest of the estate could use",
    "Added automated regression tests around the money transfer flow after a",
    "production incident, raising coverage on that module from 20% to 85%",
    "Ran database maintenance and query tuning on PostgreSQL replicas",
    "",
    "Junior Developer, Freelance - Khartoum (2018 to 2019)",
    "Delivered small business websites and a stock-tracking tool for a pharmacy",
    "Built customer-facing pages with React and a Django backend",
    "",
    "TECHNICAL SKILLS",
    "Languages: Python, JavaScript, SQL, some Go",
    "Frameworks: Django, Django REST Framework, Flask, React",
    "Databases: PostgreSQL, SQLite, Redis for caching",
    "Infrastructure: Docker, GitHub Actions, Nginx, Linux administration",
    "Practices: automated testing, code review, continuous integration, Agile",
    "",
    "EDUCATION",
    "BSc Computer Science, University of Khartoum (2018)",
    "Graduated with honours; final year project was a bus routing application",
    "",
    "LANGUAGES",
    "Arabic - native speaker",
    "English - full professional proficiency",
    "",
    "REFERENCES",
    "Available on request.",
]


def main():
    written = 0

    # One file per sample candidate, in whichever format its filename says.
    for resume in profiles.RESUMES:
        path = os.path.join(HERE, resume.filename)
        if resume.filename.endswith(".pdf"):
            with open(path, "wb") as handle:
                handle.write(build_pdf(resume.lines))
        else:
            build_docx(path, resume.lines)
        print(f"wrote {resume.filename} ({os.path.getsize(path)} bytes)")
        written += 1

    # Kept in both formats: the tests compare PDF and DOCX extraction of the
    # same content, and resume.pdf is what gets handed out for manual testing.
    extras = {
        "backend_developer_cv.docx": profiles.RESUMES[0].lines,
        "resume.pdf": LONG_RESUME,
        "resume.docx": LONG_RESUME,
    }
    for name, lines in extras.items():
        path = os.path.join(HERE, name)
        if name.endswith(".pdf"):
            with open(path, "wb") as handle:
                handle.write(build_pdf(lines))
        else:
            build_docx(path, lines)
        print(f"wrote {name} ({os.path.getsize(path)} bytes)")
        written += 1

    print(f"\n{written} files written to {HERE}")


if __name__ == "__main__":
    main()
