from .core import Rect, TextLine, capture_rect, choose_lines


class Recognizer:
    def __init__(self):
        # Imported on a background worker so model initialization never freezes the GUI.
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1,
                               det_limit_type="max", det_limit_side_len=1280)

    def recognize_image(self, image, cursor_x, cursor_y, mode):
        result, _ = self.engine(image)
        lines = []
        for box, text, score in result or []:
            left = int(min(p[0] for p in box))
            top = int(min(p[1] for p in box))
            right = int(max(p[0] for p in box))
            bottom = int(max(p[1] for p in box))
            if (text and " " not in text and sum(c.isascii() and c.isalpha() for c in text)/len(text) > .75
                    and "://" not in text and "www." not in text):
                text = self.restore_latin_spaces(image, left, top, right, bottom, text)
            lines.append(TextLine(text, Rect(left, top, right-left, bottom-top), float(score)))
        return choose_lines(lines, cursor_x, cursor_y, mode)

    def restore_latin_spaces(self, image, left, top, right, bottom, original):
        """Chinese OCR may drop Latin spaces. Re-read words separated by actual pixel gaps."""
        import cv2
        import numpy as np
        crop = image[max(0, top):min(image.shape[0], bottom+1),
                     max(0, left):min(image.shape[1], right+1)]
        if crop.size == 0 or crop.shape[0] < 8:
            return original
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if np.mean(mask) > 127:
            mask = 255-mask
        columns = np.flatnonzero(np.count_nonzero(mask, axis=0) > max(1, crop.shape[0]*.04))
        if len(columns) == 0:
            return original
        threshold = max(4, round(crop.shape[0]*.20))
        breaks = np.flatnonzero(np.diff(columns) > threshold)
        if not len(breaks) or len(breaks) > 50:
            return original
        starts = [int(columns[0])] + [int(columns[i+1]) for i in breaks]
        ends = [int(columns[i])+1 for i in breaks] + [int(columns[-1])+1]
        words = [cv2.copyMakeBorder(crop[:, a:b], 3, 3, 3, 3, cv2.BORDER_REPLICATE)
                 for a, b in zip(starts, ends)]
        results, _ = self.engine.text_rec(words)
        if results and all(value.strip() and confidence > .5 for value, confidence in results):
            return " ".join(value.strip() for value, _ in results)
        return original

    def capture(self, x, y, monitor, settings):
        import mss
        import numpy as np
        region = capture_rect(x, y, settings.capture_width, settings.capture_height, monitor)
        with mss.mss() as screen:
            image = np.asarray(screen.grab({"left": region.x, "top": region.y,
                                           "width": region.width, "height": region.height}))[:, :, :3].copy()
        result = self.recognize_image(image, x-region.x, y-region.y, settings.selection)
        if not result:
            return None
        text, box = result
        return text, Rect(region.x+box.x, region.y+box.y, box.width, box.height)
