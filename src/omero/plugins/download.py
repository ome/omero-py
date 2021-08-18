#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
   download plugin

   Plugin read by omero.cli.Cli during initialization. The method(s)
   defined here will be added to the Cli class for later use.

   Copyright 2007 - 2014 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

from builtins import str
import sys
import omero
import os
import re
from omero.cli import BaseControl, CLI
from omero.rtypes import unwrap
from omero.gateway import BlitzGateway

HELP = """Download the given file with a specified ID to a target file with
a specified filename.

Examples:

    # Download OriginalFile 2 to local_file
    omero download 2 local_file
    # Download Original File 2 to the stdout
    omero download 2 -

    # Download the OriginalFile linked to FileAnnotation 20 to local_file
    omero download FileAnnotation:20 local_file

    # Download the OriginalFile linked to Image 5
    # Works only with single files imported with OMERO 5.0.0 and above
    omero download Image:5 original_image
"""


class StdOutHandle():
    """
    File handle for writing bytes to std.out in python 2 and python 3
    """
    # https://github.com/pexpect/pexpect/pull/31/files
    @staticmethod
    def write(b):
        # Handle stdout.write for bytes
        try:
            # Try writing bytes... python 2
            return sys.stdout.write(b)
        except TypeError:
            # python 3: If String was expected, convert to String
            return sys.stdout.write(b.decode('ascii', 'replace'))


class DownloadControl(BaseControl):

    def _configure(self, parser):
        parser.add_argument(
            "object", help="Object to download of form <object>:<id>. "
            "OriginalFile is assumed if <object>: is omitted.")
        parser.add_argument(
            "--filename", help="Local filename to be saved to. '-' for stdout")
        parser.set_defaults(func=self.__call__)
        parser.add_login_arguments()

    def __call__(self, args):
        client = self.ctx.conn(args)
        dtype = None
        obj_id = None
        if ":" in args.object:
            dtype, obj_id = args.object.split(":")
        conn = BlitzGateway(client_obj=client)
        conn.SERVICE_OPTS.setOmeroGroup(-1)
        if dtype == "Project":
            self.download_project(conn, self.get_object(conn, dtype, obj_id))
        elif dtype == "Dataset":
            self.download_dataset(conn, self.get_object(conn, dtype, obj_id))
        elif dtype == "Image":
            self.download_image(conn, conn, self.get_object(conn, dtype, obj_id))
        else:
            orig_files = self.get_files(client.sf, args.object)
            if args.filename is not None:
                target_file = str(args.filename)
            else:
                target_file = orig_files[0].name.val
            # only expect single file
            self.download_file(client, orig_files[0], target_file)

    def download_project(self, conn, project):
        # make a directory named as the project
        project_name = project.name
        if not os.path.exists(project_name):
            os.makedirs(project_name)
        for dataset in project.listChildren():
            self.download_dataset(conn, dataset, project_name)

    def download_dataset(self, conn, dataset, directory=None):
        # make a directory named as the dataset
        dir_name = dataset.name
        if directory is not None:
            dir_name = os.path.join(directory, dir_name)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        for image in dataset.listChildren():
            self.download_image(conn, image, dir_name)

    def download_file(self, client, orig_file, target_file):
        perms = orig_file.details.permissions
        name = omero.constants.permissions.BINARYACCESS

        if perms.isRestricted(name):
            self.ctx.die(66, ("Download of OriginalFile:"
                              "%s is restricted") % orig_file.id.val)

        self.ctx.out(f"Downloading file ID: {orig_file.id.val} to {target_file}")
        try:
            if target_file == "-":
                client.download(orig_file, filehandle=StdOutHandle())
                sys.stdout.flush()
            else:
                client.download(orig_file, target_file)
        except omero.ClientError as ce:
            self.ctx.die(67, "ClientError: %s" % ce)
        except omero.ValidationException as ve:
            # Possible, though unlikely after previous check
            self.ctx.die(67, "Unknown ValidationException: %s"
                         % ve.message)
        except omero.ResourceError as re:
            # ID exists in DB, but not on FS
            self.ctx.die(67, "ResourceError: %s" % re.message)

    def download_image(self, conn, image, directory=None):

        self.ctx.out(f"Downloading Image:{image.id}")
        orig_files = self.get_files(conn.c.sf, f"Image:{image.id}")

        for orig_file in orig_files:
            target_file = orig_file.name.val
            if directory is not None:
                target_file = os.path.join(directory, target_file)
            self.download_file(conn.c, orig_file, target_file)

    def get_object(self, conn, dtype, obj_id):
        result = conn.getObject(dtype, obj_id)
        if result is None:
            self.ctx.die(601, f'No {dtype} with input ID: {obj_id}')
        return result

    def get_files(self, session, value):

        query = session.getQueryService()
        if ':' not in value:
            try:
                ofile = query.get("OriginalFile", int(value),
                                  {'omero.group': '-1'})
                return [ofile]
            except ValueError:
                self.ctx.die(601, 'Invalid OriginalFile ID input')
            except omero.ValidationException:
                self.ctx.die(601, 'No OriginalFile with input ID')

        # Assume input is of form OriginalFile:id
        file_id = self.parse_object_id("OriginalFile", value)
        if file_id:
            try:
                ofile = query.get("OriginalFile", file_id,
                                  {'omero.group': '-1'})
                return [ofile]
            except omero.ValidationException:
                self.ctx.die(601, 'No OriginalFile with input ID')

        # Assume input is of form FileAnnotation:id
        fa_id = self.parse_object_id("FileAnnotation", value)
        if fa_id:
            fa = None
            try:
                fa = query.findByQuery((
                    "select fa from FileAnnotation fa "
                    "left outer join fetch fa.file "
                    "where fa.id = :id"),
                    omero.sys.ParametersI().addId(fa_id),
                    {'omero.group': '-1'})
            except omero.ValidationException:
                pass
            if fa is None:
                self.ctx.die(601, 'No FileAnnotation with input ID')
            return [fa.getFile()]

        # Assume input is of form Image:id
        image_id = self.parse_object_id("Image", value)
        params = omero.sys.ParametersI()
        if image_id:
            params.addLong('iid', image_id)
            sql = "select f from Image i" \
                " left outer join i.fileset as fs" \
                " join fs.usedFiles as uf" \
                " join uf.originalFile as f" \
                " where i.id = :iid"
            query_out = query.projection(sql, params, {'omero.group': '-1'})
            if not query_out:
                self.ctx.die(602, 'Input image has no associated Fileset')

            return [unwrap(result)[0] for result in query_out]

        self.ctx.die(601, 'Invalid object input. Use e.g. Image:ID')

    def parse_object_id(self, object_type, value):

        pattern = r'%s:(?P<id>\d+)' % object_type
        pattern = re.compile('^' + pattern + '$')
        m = pattern.match(value)
        if not m:
            return
        return int(m.group('id'))

try:
    register("download", DownloadControl, HELP)
except NameError:
    if __name__ == "__main__":
        cli = CLI()
        cli.register("download", DownloadControl, HELP)
        cli.invoke(sys.argv[1:])
