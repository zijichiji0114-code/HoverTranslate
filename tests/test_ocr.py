import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hovertranslate.recognition import Recognizer


def test_real_local_ocr():
    image = Image.new("RGB", (900, 240), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30)
    draw.text((40, 70), "Hello world, this is a hover translation test.", font=font, fill="black")
    recognized = Recognizer().recognize_image(np.array(image)[:, :, ::-1].copy(), 160, 88, "line")
    assert recognized is not None
    text, box = recognized
    assert "hello world" in text.lower()
    assert box.x < 160 < box.right and box.y < 88 < box.bottom
