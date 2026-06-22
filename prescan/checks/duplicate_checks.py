# -*- encoding: utf-8 -*-
'''
@File      :   duplicate_checks.py
@Desc      :   Duplicate track detection
'''


from prescan.checks.base import BaseCheck, Issue, register_check
from prescan.models import InsTrack, ins_track_artists, InsArtist
from sqlalchemy import select, func


@register_check
class DuplicateTitleArtistCheck(BaseCheck):
    name = 'duplicate_title_artist'
    description = '相同标题+艺术家的重复曲目'

    def run(self) -> list[Issue]:
        # subquery: get (title, artist_id) combos with count > 1
        dup_subq = (
            select(
                InsTrack.title,
                ins_track_artists.c.artist_id,
            )
            .join(ins_track_artists, InsTrack.id == ins_track_artists.c.track_id)
            .where(InsTrack.parse_error == False)
            .group_by(InsTrack.title, ins_track_artists.c.artist_id)
            .having(func.count(InsTrack.id) > 1)
            .subquery()
        )

        # find all tracks matching those combos
        tracks = (
            self.session.execute(
                select(InsTrack)
                .join(ins_track_artists, InsTrack.id == ins_track_artists.c.track_id)
                .join(
                    dup_subq,
                    (InsTrack.title == dup_subq.c.title)
                    & (ins_track_artists.c.artist_id == dup_subq.c.artist_id)
                )
                .order_by(InsTrack.title)
            )
            .scalars()
            .all()
        )

        # get artist names for better messages
        artist_map: dict[int, str] = {}
        artist_ids = {
            row.artist_id
            for row in self.session.execute(
                select(ins_track_artists.c.artist_id).where(
                    ins_track_artists.c.track_id.in_([t.id for t in tracks])
                )
            )
        }
        if artist_ids:
            for a in self.session.execute(
                select(InsArtist).where(InsArtist.id.in_(artist_ids))
            ).scalars():
                artist_map[a.id] = a.name

        issues: list[Issue] = []
        for t in tracks:
            # get this track's artist names
            track_artist_ids = [
                row.artist_id
                for row in self.session.execute(
                    select(ins_track_artists.c.artist_id).where(
                        ins_track_artists.c.track_id == t.id
                    )
                )
            ]
            artist_names = ', '.join(artist_map.get(aid, '?') for aid in track_artist_ids)
            issues.append(Issue(
                check_name=self.name, severity='warning', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'疑似重复: "{t.title}" by {artist_names}',
            ))

        return issues
