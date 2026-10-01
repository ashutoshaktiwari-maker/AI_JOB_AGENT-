import os
import fitz  # PyMuPDF


class ResumeParser:
    """
    Parses PDF resumes and extracts plain text.
    """

    @staticmethod
    def extract_text(pdf_path: str) -> str:
        """
        Extract text from a PDF file.

        Args:
            pdf_path (str): Path to the PDF file.

        Returns:
            str: Extracted text from all pages.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not a PDF.
            RuntimeError: If the PDF cannot be read.
        """

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"File not found: {pdf_path}")

        if not pdf_path.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are supported.")

        try:
            text = ""

            with fitz.open(pdf_path) as document:
                for page in document:
                    text += page.get_text()

            return text.strip()

        except Exception as e:
            raise RuntimeError(f"Failed to parse PDF: {e}") from e