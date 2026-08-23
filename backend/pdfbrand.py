"""One brand mark for every PDF we generate, so invoices, passes and agreements match the site."""
import os

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image

LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")


def logo(height: float = 11 * mm):
    """Returns a reportlab Image at the right aspect ratio, or None if the file is missing."""
    try:
        iw, ih = ImageReader(LOGO_PATH).getSize()
        return Image(LOGO_PATH, width=height * iw / ih, height=height)
    except Exception:
        return None
