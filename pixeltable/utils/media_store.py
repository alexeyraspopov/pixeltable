import glob
import os
import re
import uuid
from typing import Optional, List, Tuple, Dict
from pathlib import Path
from collections import defaultdict
from uuid import UUID

from pixeltable.env import Env


class MediaStore:
    """
    Utilities to manage media files stored in Env.media_dir

    Media file names are a composite of: table id, column id, version, uuid:
    the table id/column id/version are redundant but useful for identifying all files for a table
    or all files created for a particular version of a table
    """
    pattern = re.compile(r'([0-9a-fA-F]+)_(\d+)_(\d+)_([0-9a-fA-F]+)')  # tbl_id, col_id, version, uuid

    @classmethod
    def get_path(cls, tbl_id: UUID, col_id: int, version: int, ext: Optional[str] = None) -> Path:
        """Return Path for the target table and column
        ext is appended if non-None.
        """
        id = uuid.uuid4()
        return Env.get().media_dir / f'{tbl_id.hex}_{col_id}_{version}_{id.hex}{ext or ""}'

    @classmethod
    def delete(cls, tbl_id: UUID, version: Optional[int] = None) -> None:
        """Delete all files belonging to tbl_id"""
        assert tbl_id is not None
        if version is not None:
            pattern = f'{tbl_id.hex}_*_{version}_*'
        else:
            pattern = f'{tbl_id.hex}_*'
        paths = glob.glob(str(Env.get().media_dir / pattern))
        for p in paths:
            os.remove(p)

    @classmethod
    def count(cls, tbl_id: UUID) -> int:
        """
        Return number of files for given tbl_id.
        """
        paths = glob.glob(str(Env.get().media_dir / f'{tbl_id.hex}_*'))
        return len(paths)

    @classmethod
    def stats(cls) -> List[Tuple[int, int, int, int]]:
        paths = glob.glob(str(Env.get().media_dir))
        # key: (tbl_id, col_id), value: (num_files, size)
        d: Dict[Tuple[UUID, int], List[int]] = defaultdict(lambda: [0, 0])
        for p in paths:
            matched = re.match(cls.pattern, Path(p).name)
            assert matched is not None
            tbl_id, col_id = UUID(hex=matched[1]), int(matched[2])
            file_info = os.stat(p)
            t = d[(tbl_id, col_id)]
            t[0] += 1
            t[1] += file_info.st_size
        result = [(tbl_id, col_id, num_files, size) for (tbl_id, col_id), (num_files, size) in d.items()]
        result.sort(key=lambda e: e[3], reverse=True)
        return result