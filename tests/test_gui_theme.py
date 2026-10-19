import unittest

from branchs.gui_theme import PALETTES


def contrast(first, second):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                  for channel in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class GuiThemeTests(unittest.TestCase):
    def test_text_and_status_colors_remain_readable_in_both_themes(self):
        pairs = (
            ("text", "surface"), ("muted", "surface"), ("text", "input"),
            ("text", "tree"), ("button_text", "button"), ("accent_text", "accent"),
            ("selected_text", "selected"), ("added", "tree"),
            ("deleted", "tree"), ("modified", "tree"),
            ("added", "selected"), ("deleted", "selected"), ("modified", "selected"),
            ("muted", "header"), ("muted", "heading"),
        )
        for theme, colors in PALETTES.items():
            for foreground, background in pairs:
                with self.subTest(theme=theme, foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5)


if __name__ == "__main__":
    unittest.main()
