""" Utilities """
import os

import contextlib
import shutil
from uuid import uuid1


@contextlib.contextmanager
def atomic_open(name, *args, **kwargs):
    """ Atomically open a file for reading/writing """
    basename = os.path.basename(name) + '.tmp.' + uuid1().hex
    # Make sure the tmp file is hidden
    if not basename.startswith('.'):
        basename = '.' + basename
    tmpfile = os.path.join(os.path.dirname(name), basename)
    if os.path.exists(name):
        shutil.copyfile(name, tmpfile)
    with open(tmpfile, *args, **kwargs) as ofile:
        yield ofile
    os.rename(tmpfile, name)
