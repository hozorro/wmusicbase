from pathlib import Path
from typing import Any

def decode_tag_value(raw_value: Any, encoding: int) -> str:
        '''decode raw tag text to utf-8 str, according to encoding'''
        decoded_str = ''
        try:
            if encoding == 0:   # LATIN1
                # encode to bytes and decode to gb18030, transform to utf-8 finally
                if isinstance(raw_value, str):
                    decoded_str = raw_value.encode('latin1', errors='ignore').decode('gb18030', errors='ignore')
                else:
                    decoded_str = bytes(raw_value).decode('gb18030', errors='ignore')
            elif encoding == 1:  # UTF-16
                decoded_str = bytes(raw_value).decode('utf-16', errors='ignore')
            elif encoding == 2:  # UTF-16BE
                decoded_str = bytes(raw_value).decode('utf-16be', errors='ignore')
            elif encoding == 3:  # UTF-8
                decoded_str = bytes(raw_value).decode('utf-8', errors='ignore')
            else:
                decoded_str = str(raw_value, errors='ignore')
        except Exception:
            decoded_str = str(raw_value)
        # strip and transform to utf-8 finally
        return decoded_str.strip().encode('utf-8', errors='ignore').decode('utf-8')

if __name__ == '__main__':
    file_path = r'F:\zwy\Documents\gits\wmusicbase\media\uploads\staging\e8ea67f9-afd5-4eea-b9c3-085778835bac\songs\193f660cdbe3411688fed43c4187a7e9_09. 离别.mp3'
    file_path_1 = r'D:\pdf\07 好朋友的祝福.mp3'
    file_path_2 = r'D:\pdf\70.天使与魔鬼的对话 - 蔡健雅.mp3'

    # from app.utils.metadata import extract_metadata, parse_metadata
    # meta = parse_metadata(Path(file_path_1))
    # print(meta)
    # upgrade_meta_version(Path(file_path_2))

    # from app.utils.audiofile import AudioMeta
    # audio = AudioMeta(file_path_1)
    # audio.update_version(use_apev2=True)
    # print(audio.to_fileinfo())
    
    from mutagen.id3 import ID3, Encoding
    tags = ID3(Path(file_path))
    print(tags)
    # for key in tags:
    #     if hasattr(tags[key], 'text'):
    #         if hasattr(tags[key], 'encoding'):
    #             if isinstance(tags[key].text, list):
    #                 tags[key].text = [decode_tag_value(text, tags[key].encoding) for text in tags[key].text]
    #                 tags[key].encoding = Encoding.UTF8
    #             else:
    #                 tags[key].text = decode_tag_value(tags[key].text, tags[key].encoding)
    #                 tags[key].encoding = Encoding.UTF8
    # print(tags)

    # from mutagen import File as MutagenFile
    # maudio = MutagenFile(file_path_1, easy=True)
    # mbid = maudio.get('musicbrainz_trackid', [''])
    # print(mbid)

    # from app.utils.metadata import download_cover_art
    # content = download_cover_art('2b8ce39a-e68d-4e48-a139-a57282e03f6e')
    # print(content)

    


    


    