# -*- encoding: utf-8 -*-
"""
Tests for app/services/lyric_index_service.py
lrc -> plain text and the application side multi-hit highlighter.
"""

from app.services.lyric_index_service import build_snippets, to_plain


class TestToPlain:
    def test_strips_time_tags_and_metadata(self):
        raw = (
            '[ti:测试歌曲]\n'
            '[ar:测试歌手]\n'
            '[al:测试专辑]\n'
            '[by:someone]\n'
            '[00:01.00]第一行\n'
            '[00:02.50]第二行\n'
            '\n'
            '[offset:0]\n'
            '[00:05.00]\n'
        )
        assert to_plain(raw) == '第一行\n第二行'

    def test_strips_multiple_tags_on_one_line(self):
        assert to_plain('[00:01.00][00:02.00]重复标签行') == '重复标签行'

    def test_strips_enhanced_a2_tags(self):
        assert to_plain('<00:01.00>增强标签行') == '增强标签行'

    def test_empty_input(self):
        assert to_plain('') == ''


class TestBuildSnippets:
    def test_merges_repeated_hits_in_one_line(self):
        text = '名字 名字 名字'
        snippets = build_snippets(text, ['名字'])

        assert len(snippets) == 1
        snippet = snippets[0]
        assert len(snippet['highlights']) == 3
        for start, end in snippet['highlights']:
            assert snippet['text'][start:end] == '名字'

    def test_highlights_are_relative_to_snippet(self):
        text = '有一种悲伤\n是你的名字停留在我的过往\n无法遗忘'
        snippets = build_snippets(text, ['名字'])

        assert len(snippets) == 1
        start, end = snippets[0]['highlights'][0]
        assert snippets[0]['text'][start:end] == '名字'

    def test_far_apart_hits_produce_separate_snippets(self):
        text = '名字\n' + '无关内容\n' * 20 + '名字'
        snippets = build_snippets(text, ['名字'])

        assert len(snippets) == 2
        for snippet in snippets:
            assert len(snippet['highlights']) == 1
            s, e = snippet['highlights'][0]
            assert snippet['text'][s:e] == '名字'

    def test_limits_snippet_count(self):
        text = ''.join(f'名字\n{"铺垫内容\n" * 20}' for _ in range(5))
        snippets = build_snippets(text, ['名字'], max_snippets=2)
        assert len(snippets) == 2

    def test_no_hit_returns_empty(self):
        assert build_snippets('你的名字', ['宇宙飞船']) == []
        assert build_snippets('', ['名字']) == []
        assert build_snippets('你的名字', []) == []

    def test_multiple_terms_in_one_snippet(self):
        text = '是你的名字停留在我的过往，我无法遗忘'
        snippets = build_snippets(text, ['名字', '遗忘'])

        assert len(snippets) == 1
        highlighted = {snippets[0]['text'][s:e] for s, e in snippets[0]['highlights']}
        assert highlighted == {'名字', '遗忘'}
