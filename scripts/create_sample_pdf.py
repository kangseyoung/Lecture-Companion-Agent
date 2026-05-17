"""Create a small sample lecture PDF for testing the pipeline.

The sample PDF has two pages of English technical content:
- What is a multiplexer?
- What is a full adder?
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def create_sample_pdf(output_path: PathLike = "input/sample_lecture.pdf") -> Path:
    """Create a two-page sample lecture PDF and return its path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "ReportLab is required to create the sample PDF. Install it with: "
            "pip install -r requirements.txt"
        ) from exc

    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter

    _draw_page(
        pdf=pdf,
        width=width,
        height=height,
        title="What is a Multiplexer?",
        lines=[
            "A multiplexer, often called a MUX, is a digital circuit that selects one input",
            "from several input signals and forwards the selected input to a single output.",
            "",
            "A select signal controls which input is connected to the output.",
            "For example, a 2-to-1 multiplexer has two data inputs, one select input,",
            "and one output.",
            "",
            "When the select signal is 0, the output follows input 0.",
            "When the select signal is 1, the output follows input 1.",
            "",
            "Multiplexers are useful because they allow many signals to share one path.",
        ],
    )
    pdf.showPage()

    _draw_page(
        pdf=pdf,
        width=width,
        height=height,
        title="What is a Full Adder?",
        lines=[
            "A full adder is a digital circuit that adds three one-bit values.",
            "The three inputs are A, B, and carry-in.",
            "",
            "The circuit produces two outputs: sum and carry-out.",
            "The sum output is the one-bit result of the addition.",
            "The carry-out output is used when the addition produces a value too large",
            "to fit in one bit.",
            "",
            "Full adders are important because they can be connected together",
            "to build circuits that add multi-bit binary numbers.",
        ],
    )
    pdf.showPage()

    pdf.save()
    return path


def _draw_page(pdf, width: float, height: float, title: str, lines: list) -> None:
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(72, height - 72, title)

    pdf.setFont("Helvetica", 13)
    y = height - 120
    for line in lines:
        if not line:
            y -= 14
            continue
        pdf.drawString(72, y, line)
        y -= 20


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a sample lecture PDF for testing.")
    parser.add_argument(
        "--output",
        default="input/sample_lecture.pdf",
        help="Where to save the sample PDF.",
    )
    args = parser.parse_args()

    path = create_sample_pdf(args.output)
    print(path)


if __name__ == "__main__":
    main()
