# -*- encoding: utf-8 -*-
"""
Tests for app/utils/color.py
Function: generate_unique_light_color
"""

import re
import random
from app.utils.color import generate_unique_light_color


class TestGenerateUniqueLightColor:
    """Tests for generate_unique_light_color(existing_colors: set, step=16) -> str"""

    def test_empty_set_returns_valid_hex(self):
        color = generate_unique_light_color(set())
        assert re.match(r'^#[0-9a-f]{6}$', color)

    def test_color_not_in_existing(self):
        existing = {'#7f7f7f', '#7f8f9f'}
        color = generate_unique_light_color(existing)
        assert color not in existing

    def test_format_is_hex(self):
        random.seed(42)
        color = generate_unique_light_color(set())
        assert len(color) == 7
        assert color[0] == '#'
        # Verify it's valid hex
        int(color[1:], 16)

    def test_deterministic_with_seed(self):
        random.seed(123)
        c1 = generate_unique_light_color(set())
        random.seed(123)
        c2 = generate_unique_light_color(set())
        assert c1 == c2

    def test_fallback_when_exhausted(self, mocker):
        # Mock random.randint to always return same values, producing '#7f7f7f'
        # With step=16: end=16, start=8. random.randint(8,16) -> 8
        # 8*16-1=127=0x7f. So all calls produce '#7f7f7f'
        mocker.patch('app.utils.color.random.randint', return_value=8)
        existing = {'#7f7f7f'}
        color = generate_unique_light_color(existing, step=16)
        # All 100 attempts generate '#7f7f7f' which is in existing -> fallback
        assert color == '#7f7f7f'
