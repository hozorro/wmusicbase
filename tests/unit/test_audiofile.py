# -*- encoding: utf-8 -*-
"""
Tests for app/utils/audiofile.py
Focus: AudioMeta 在无标签/非音频文件下的兜底，以及 update_metadata 的按类型保存分支
"""

from unittest.mock import MagicMock, patch

from app.utils.audiofile import AudioMeta


def _make_meta(tmp_path, name='song.mp3'):
    f = tmp_path / name
    f.write_bytes(b'not a real audio file')
    return AudioMeta(str(f))


class TestMetaDataFallback:
    def test_non_audio_file_uses_defaults(self, tmp_path):
        """read_metadata 返回 None 时不抛异常，各字段为空默认值"""
        meta = _make_meta(tmp_path, 'dummy.txt')

        data = meta.meta_data

        assert data['primary']['title'] == ''
        assert data['primary']['artists'] == []
        assert data['primary']['album'] == ''
        assert data['primary']['year'] is None
        assert data['primary']['genres'] == []
        assert data['additional']['albumartist'] == []
        assert data['additional']['cover_art_hash'] is None

    def test_to_fileinfo_returns_empty_models(self, tmp_path):
        meta = _make_meta(tmp_path, 'dummy.txt')

        info = meta.to_fileinfo()

        assert info.path == str(tmp_path / 'dummy.txt')
        assert info.meta_id3 is not None
        assert info.meta_id3.title == ''
        assert info.meta_apev2 is None  # 没有 APEv2 标签
        assert info.meta_additional is not None
        assert info.meta_additional.cover_art_hash is None


class TestUpdateMetadataSave:
    """mp3 需要删除 ID3v1，flac 的 save() 不接受 v1 参数"""

    @patch('app.utils.audiofile.write_metadata')
    @patch('app.utils.audiofile.MutagenFile')
    def test_mp3_drops_id3v1(self, mock_file, mock_write, tmp_path):
        meta = _make_meta(tmp_path)
        meta.file_type = 'mp3'
        tag = MagicMock()
        mock_file.return_value = tag

        with patch.object(meta, 'init_version'):
            meta.update_metadata({'title': 'new'}, del_id3v1=True)

        mock_write.assert_called_once_with(meta.file_path, {'title': 'new'})
        tag.save.assert_called_once_with(meta.file_path, v1=0)

    @patch('app.utils.audiofile.write_metadata')
    @patch('app.utils.audiofile.MutagenFile')
    def test_flac_saves_without_v1(self, mock_file, mock_write, tmp_path):
        meta = _make_meta(tmp_path, 'song.flac')
        meta.file_type = 'flac'
        tag = MagicMock()
        mock_file.return_value = tag

        with patch.object(meta, 'init_version'):
            meta.update_metadata({'title': 'new'}, del_id3v1=True)

        tag.save.assert_called_once_with(meta.file_path)

    @patch('app.utils.audiofile.write_metadata')
    @patch('app.utils.audiofile.MutagenFile')
    def test_no_tag_object_is_ignored(self, mock_file, mock_write, tmp_path):
        meta = _make_meta(tmp_path)
        meta.file_type = 'mp3'
        mock_file.return_value = None

        with patch.object(meta, 'init_version'):
            meta.update_metadata({'title': 'new'}, del_id3v1=True)

        # 不抛异常即可
        assert mock_file.called
