# -*- encoding: utf-8 -*-
"""
Tests for app/schemas/track.py
Validator: TrackDetail.extract_names (model_validator mode='before')
"""

from unittest.mock import MagicMock
from app.models.track import Track
from app.schemas.track import TrackDetail


class TestTrackDetailExtractNames:
    """Tests for TrackDetail.extract_names model_validator"""

    def test_from_track_orm(self):
        """Track ORM object -> extract artists/genres names"""
        mock_track = MagicMock(spec=Track)
        mock_track.id = 1
        mock_track.title = 'Test Song'
        mock_track.cover_art_hash = 'abc123'
        mock_track.year = 2023
        mock_track.path = 'Chinese/A-G/Artist/Album/song.mp3'

        artist1 = MagicMock()
        artist1.name = 'Artist A'
        artist2 = MagicMock()
        artist2.name = 'Artist B'
        mock_track.artists = [artist1, artist2]

        genre1 = MagicMock()
        genre1.name = 'Rock'
        mock_track.genres = [genre1]

        result = TrackDetail.model_validate(mock_track)
        assert result.id == 1
        assert result.title == 'Test Song'
        assert result.artists == ['Artist A', 'Artist B']
        assert result.genres == ['Rock']
        assert result.year == 2023

    def test_from_track_empty_relations(self):
        """Track ORM with empty artists/genres"""
        mock_track = MagicMock(spec=Track)
        mock_track.id = 2
        mock_track.title = 'Solo Song'
        mock_track.cover_art_hash = None
        mock_track.year = None
        mock_track.path = 'Chinese/song.mp3'
        mock_track.artists = []
        mock_track.genres = []

        result = TrackDetail.model_validate(mock_track)
        assert result.artists == []
        assert result.genres == []
        assert result.year is None

    def test_from_dict_passthrough(self):
        """Dict input passes through unchanged"""
        data = {
            'id': 3,
            'title': 'Dict Song',
            'cover_art_hash': None,
            'artists': ['Artist X'],
            'genres': ['Pop'],
            'path': 'Foreign/song.mp3',
            'year': 2020,
        }
        result = TrackDetail.model_validate(data)
        assert result.artists == ['Artist X']
        assert result.genres == ['Pop']
