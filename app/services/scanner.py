# -*- encoding: utf-8 -*-
'''
@File      :   scanner.py
@Time      :   2026/02/10 20:13:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   scanner with p+c mode
'''


import asyncio
from pathlib import Path
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.state import system_state
from app.core.logger import logger
from app.schemas.filething import ParsedMeta
from app.services.processor import MusicFileProcessor
from app.utils.metadata import read_metadata

SCAN_TASK_COUNT = 50
COMMIT_TASK_COUNT = 100

class Scanner:
    def __init__(self, root_path: Path, is_incremental: bool):
        self.root_path = root_path
        self.is_incremental = is_incremental
        self.queue = asyncio.Queue(maxsize=1000)
        self.batch_size = COMMIT_TASK_COUNT    # db commit batch size

    async def parse_single_file(self, file_path: Path):
        '''
        parse file metadata, put into queue, producer task.
        if error occurs, log and continue with next file.
        update scan progress in system state.
        '''
        try:
            meta = read_metadata(file_path)
            meta.update({"path": str(file_path)})
            # file_fp = compute_file_hash(file_path)
            # meta.update({
            #     "fingerprint": file_fp[0],
            #     "size": file_fp[1],
            #     "mtime": file_fp[2]
            # })
            await self.queue.put(ParsedMeta.model_validate(meta))
        except Exception:
            logger.error(f"Failed to parse metadata for file {file_path}")
            system_state.scan_progress['failed'] += 1
        
    async def count_files(self):
        count = 0
        for file_path in self.root_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
                count += 1
        return count
    
    def iter_files(self):
        for file_path in self.root_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
                yield file_path
    
    async def producer(self):
        '''
        producer: scan folder, parse file, put into queue
        '''
        logger.info("Start scanning files...")
        system_state.scan_progress['total'] = await self.count_files()
        tasks = []
        try:
            for file_path in self.iter_files():
                if system_state.is_scanning_canceled:
                    logger.info("Scan canceled, stopping producer.")
                    break
                task = asyncio.create_task(self.parse_single_file(file_path))
                tasks.append(task)

                if len(tasks) >= SCAN_TASK_COUNT:
                    await asyncio.gather(*tasks)
                    tasks = []
            if tasks:  # wait for all tasks to finish
                await asyncio.gather(*tasks)
        except Exception as e:
            logger.critical(f"Scanner producer crashed: {e}")
            system_state.is_scanning = False
        finally:
            await self.queue.put(None)  # signal end of processing
            logger.info(f"Finished parsing files.")

    async def consumer(self):
        '''
        consumer: process file, save to db, single db writer, avoid db deadlock
        '''
        logger.info("Start processing files...")
        async with AsyncSessionLocal() as db:
            processor = MusicFileProcessor(self.root_path, db)
            while True:
                meta = await self.queue.get()
                if meta is None:
                    await processor.commit_pending_tracks()  # commit remaining tracks  
                    
                    if system_state.is_scanning_canceled:
                        logger.info("Scan canceled, stopping consumer.")
                    else:
                        logger.info("All files processed, consumer task done.")
                    self.queue.task_done()
                    break

                system_state.scan_progress['current_file'] = str(Path(meta.path).relative_to(self.root_path))
                
                if system_state.is_scanning_canceled:
                    # not break immediately, use continue to skip processing and db writing
                    # just skip processing and db writing
                    # let producer finish putting none into queue
                    # avoid blocked producer not able to put None into queue, cause producer keep blocked on full queue
                    self.queue.task_done()
                    continue
                
                try:
                    await processor.process_single_file(meta, self.is_incremental)
                    # check if batch size reached, commit to db
                    if len(processor.pending_tracks) >= self.batch_size:
                        # try-except handled db errors in commit_pending_tracks, if error occurs, log and continue processing next files
                        await processor.commit_pending_tracks()
                except Exception as e:
                    logger.error(f"Error processing file {meta.path}: {e}")
                    system_state.scan_progress['failed'] += 1
                finally:
                    system_state.scan_progress['processed'] += 1
                    self.queue.task_done()

    async def run(self):
        system_state.init_scan_state()
        await asyncio.gather(
            self.producer(), 
            self.consumer()
        )
        if system_state.scan_progress:
            result = f'{system_state.scan_progress['total']} scanned, \
                {system_state.scan_progress['processed']} processed, \
                {system_state.scan_progress['success']} success, \
                {system_state.scan_progress['failed']} failed.'
            logger.info(result)
        system_state.reset_scan_state()
        logger.info("Scan completed.")