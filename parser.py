import logging
import six
import time
import json

from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from datetime import datetime
from collections import defaultdict
from fuse import FuseOSError, EIO


class Directory:
    def __init__(self, root, path, session):
        self.root = root
        self.path = path
        self.session = session
        self.log = logging.getLogger("Directory")
        self.log.debug(u"[INIT] Loading directory {}/{}".format(root, path))

    def contents(self):
        """
        Give the contents of the directory
        :return: List of Entities that are in the directory
        :rtype: list
        """
        contents = [(".", True), ("..", True)]

        # Do a request and parse JSON
        response = json.loads((self.session.get(u"{}/{}/".format(self.root, self.path))).text)

        for d in self.retrieve_directories(response):
            name = d.split('/')[-1]
            is_dir = True
            contents.append((name, is_dir))

        if 'files' in response:
            file_arr = response['files']
            for f in file_arr:
                name = f.split('/')[-1]
                is_dir = False
                contents.append((name, is_dir))

        return contents

    def retrieve_directories(self, json):
        """
        Alveo API response contains entries(collections/items/documents) which can be treated as
        directories.

        * 'document_directory' if not empty, contains only one directory - 'document'
        :param self:
        :param json: json contains alveo API response
        :return: string array as directories
        """
        directory_arr = []

        if 'collections' in json:
            directory_arr = json['collections']

        if 'items' in json:
            directory_arr = json['items']

        if 'documents' in json:
            directory_arr = json['documents']

        if 'document_directory' in json:
            directory_arr = json['document_directory']

        return directory_arr


class File:
    def __init__(self, root, path, alveofs, session):
        self.root = root
        self.path = path
        self.session = session
        self.log = logging.getLogger("File")
        self.log.debug(u"[INIT] Loading file {}/{}".format(root, path))
        self.readbuffer = defaultdict(lambda: None)
        self.is_filtered = False

        # print "----- Loading file root[{}], path[{}]".format(root, path)

        # filter file
        if self.filter_path():
            self.is_dir = False
            self.mtime = time.time()
            self.size = 0
            self.is_filtered = True
            return

        # Determine if this is a directory
        parent_dir = "/".join(self.path.split("/")[:-1])
        filename = self.path.split("/")[-1]
        if parent_dir not in alveofs.readdir_cache.keys():
            alveofs.readdir_cache[parent_dir] = Directory(self.root, parent_dir, self.session).contents()

        dirs = [six.text_type(x[0]) for x in alveofs.readdir_cache[parent_dir] if x[1]]
        self.is_dir = (six.text_type(filename) in dirs) or six.text_type(filename) == six.text_type("")

        # Determine file size
        self.url = u"{}/{}{}".format(self.root, self.path, "/" if self.is_dir else "")
        self.r = self.session.head(self.url, allow_redirects=True)
        if self.r.status_code == 200:
            try:
                self.size = int(self.r.headers['Content-Length'])
            except KeyError:
                self.size = 0

            try:
                mtime_string = self.r.headers["Last-Modified"]
                # self.mtime = time.mktime(datetime.strptime(mtime_string, "%a, %d %b %Y %H:%M:%S %Z").timetuple())
                self.mtime = time.time()
            except KeyError:
                self.mtime = time.time()
        else:
            self.log.info(u"[INIT] Non-200 code while getting {}: {}".format(self.url, self.r.status_code))
            self.size = 0

    def read(self, length, offset):
        """
        Reads the file.
        :param length: The length to read
        :param offset: The offset to start at
        :return: The file's bytes
        """
        self.log.debug(u"[READ] Reading file {}/{}".format(self.root, self.path))
        url = u"{}/{}".format(self.root, self.path)

        # Calculate megabyte-section this offset/length is in
        mb_start = (offset // 1024) // 1024
        mb_end = ((offset + length) // 1024) // 1024
        offset_from_mb = (((offset // 1024) % 1024) * 1024) + (offset % 1024)
        self.log.debug(u"Calculated MB_Start {} MB_End {} Offset from MB: {}".format(mb_start, mb_end, offset_from_mb))
        if mb_start == mb_end:
            self.log.debug(u"Readbuffer filled for mb_start? {}".format(self.readbuffer[mb_start] is not None))
            if self.readbuffer[mb_start] is None:
                # Fill buffer for this MB
                bytesRange = u'{}-{}'.format(mb_start * 1024 * 1024, (mb_start * 1024 * 1024) + (1023 * 1024))
                self.log.debug(u"Fetching byte range {}".format(bytesRange))
                headers = {'range': 'bytes=' + bytesRange}
                r = self.session.get(url, headers=headers)
                if r.status_code == 200 or r.status_code == 206:
                    self.readbuffer[mb_start] = r.content
                    # noinspection PyTypeChecker
                    self.log.debug(u"Read {} bytes.".format(len(self.readbuffer[mb_start])))
                else:
                    self.log.info(u"[INIT] Non-200 code while getting {}: {}".format(url, r.status_code))
                    raise FuseOSError(EIO)

            self.log.debug(u"Returning indices {} to {}".format(offset_from_mb, offset_from_mb + length))
            return self.readbuffer[mb_start][offset_from_mb:offset_from_mb + length]
        else:
            self.log.debug(u"Offset/Length spanning multiple MB's. Fetching normally")
            # Spanning multiple MB's, just get it normally
            # Set range
            bytesRange = u'{}-{}'.format(offset, min(self.size, offset + length - 1))
            self.log.debug(u"Fetching byte range {}".format(bytesRange))
            headers = {'range': 'bytes=' + bytesRange}
            r = self.session.get(url, headers=headers)
            if self.r.status_code == 200 or r.status_code == 206:
                return r.content
            else:
                self.log.info(u"[INIT] Non-200 code while getting {}: {}".format(url, r.status_code))
                raise FuseOSError(EIO)

    def attributes(self):
        self.log.debug(u"[ATTR] Attributes of file {}/{}".format(self.root, self.path))
        # print "=====Attributes of file root[{}], path[{}], is_filtered[{}]".format(self.root, self.path, self.is_filtered)

        if not self.is_filtered and self.r.status_code != 200:
            raise FuseOSError(ENOENT)

        mode = (S_IFDIR | 0o777) if self.is_dir else (S_IFREG | 0o666)

        attrs = {
            'st_atime': self.mtime,
            'st_mode': mode,
            'st_mtime': self.mtime,
            'st_size': self.size,
        }

        if self.is_dir:
            attrs['st_nlink'] = 2

        return attrs

    def filter_path(self):
        '''
        To filter unqualified file
        :return:
        False - don't filter, keep processing
        True - filter this file, don't need to further process
        '''
        rlt = False
        name = self.path.split('/')[-1]
        for w in ['.', 'DCIM', 'Gemfile', 'HEAD']:
            if name.startswith(w):
                rlt = True

        # print "=====filter_path: root[{}], path[{}], name[{}], rlt[{}]".format(self.root, self.path, name, rlt)

        return rlt