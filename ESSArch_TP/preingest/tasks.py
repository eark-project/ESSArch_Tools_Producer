from __future__ import absolute_import

import os, shutil, tarfile, zipfile

from django.conf import settings
from django.core import serializers

from lxml import etree

from ESSArch_Core.configuration.models import Path
from ESSArch_Core.WorkflowEngine.dbtask import DBTask
from ESSArch_Core.ip.models import InformationPackage
from ESSArch_Core.WorkflowEngine.models import ProcessStep
from ESSArch_Core.util import (
    get_value_from_path, remove_prefix, win_to_posix
)
from ESSArch_Core import tasks

class PrepareIP(DBTask):
    event_type = 10100

    def run(self, label="", responsible={}, step=None):
        """
        Prepares a new information package

        Args:
            label: The label of the IP to prepare
            responsible: The responsible user of the IP to prepare
            step: The step to connect the IP to

        Returns:
            The id of the created information package
        """


        ip = InformationPackage.objects.create(
            Label=label,
            Responsible=responsible,
            State="Preparing",
            OAIStype="SIP",
        )

        self.taskobj.information_package = ip
        self.taskobj.save()

        if step is not None:
            s = ProcessStep.objects.get(pk=step)
            ip.steps.add(s)

        self.set_progress(100, total=100)

        return ip

    def undo(self, label="", responsible={}, step=None):
        pass

    def event_outcome_success(self, label="", responsible={}, step=None):
        return "Prepared IP with label '%s'" % label


class CreateIPRootDir(DBTask):
    event_type = 10110

    def create_path(self, information_package_id):
        prepare_path = Path.objects.get(
            entity="path_preingest_prepare"
        ).value

        return os.path.join(
            prepare_path,
            unicode(information_package_id)
        )

    def run(self, information_package=None):
        """
        Creates the IP root directory

        Args:
            information_package_id: The id of the information package the
            directory will be created for

        Returns:
            None
        """

        self.taskobj.information_package = information_package
        self.taskobj.save()

        path = self.create_path(str(information_package.pk))
        os.makedirs(path)

        information_package.ObjectPath = path
        information_package.save()

        self.set_progress(100, total=100)
        return information_package

    def undo(self, information_package=None):
        path = self.create_path(information_package.pk)
        shutil.rmtree(path)

    def event_outcome_success(self, information_package=None):
        return "Created root directory for IP '%s'" % information_package.pk

class CreatePhysicalModel(DBTask):
    event_type = 10115

    def run(self, structure={}, root=""):
        """
        Creates the IP physical model based on a logical model.

        Args:
            structure: A dict specifying the logical model.
            root: The root dictionary to be used
        """

        root = os.path.join(settings.BASE_DIR, str(root))

        for content in structure:
            if content.get('type') == 'folder':
                name = content.get('name')
                dirname = os.path.join(root, name)
                os.makedirs(dirname)

                self.run(content.get('children', []), dirname)

        self.set_progress(1, total=1)

    def undo(self, structure={}, root=""):
        root = os.path.join(settings.BASE_DIR, str(root))

        if root:
            shutil.rmtree(root)
            return

        for k, v in structure.iteritems():
            k = str(k)
            dirname = os.path.join(root, k)
            shutil.rmtree(dirname)

    def event_outcome_success(self, structure={}, root=""):
        return "Created physical model for IP '%s'" % self.taskobj.information_package.pk


class CalculateChecksum(tasks.CalculateChecksum):
    event_type = 10210

class IdentifyFileFormat(tasks.IdentifyFileFormat):
    event_type = 10220


class GenerateXML(tasks.GenerateXML):
    event_type = 10230


class AppendEvents(tasks.AppendEvents):
    event_type = 10240


class CopySchemas(tasks.CopySchemas):
    event_type = 10250


class ValidateFileFormat(tasks.ValidateFileFormat):
    event_type = 10260


class ValidateXMLFile(tasks.ValidateXMLFile):
    event_type = 10261


class ValidateLogicalPhysicalRepresentation(DBTask):
    event_type = 10262

    """
    Validates the logical and physical representation of objects.

    The comparison checks if the lists contains the same elements (though not
    the order of the elements).

    See http://stackoverflow.com/a/7829388/1523238
    """

    def run(self, ip=None, xmlfile=None):
        objpath = ip.ObjectPath
        xmlrelpath = os.path.relpath(xmlfile, objpath)
        xmlrelpath = remove_prefix(xmlrelpath, "./")

        doc = etree.ElementTree(file=xmlfile)

        root = doc.getroot()

        logical_files = set()
        physical_files = set()

        for elname, props in settings.FILE_ELEMENTS.iteritems():
            for f in doc.xpath('.//*[local-name()="%s"]' % elname):
                filename = get_value_from_path(f, props["path"])

                if filename:
                    filename = remove_prefix(filename, props.get("pathprefix", ""))
                    logical_files.add(filename)

        for root, dirs, files in os.walk(objpath):
            for f in files:
                if f != xmlrelpath:
                    reldir = os.path.relpath(root, objpath)
                    relfile = os.path.join(reldir, f)
                    relfile = win_to_posix(relfile)
                    relfile = remove_prefix(relfile, "./")

                    physical_files.add(relfile)

        assert logical_files == physical_files, "the logical representation differs from the physical"
        self.set_progress(100, total=100)
        return "Success"

    def undo(self, ip=None, xmlfile=None):
        pass

    def event_outcome_success(self, ip=None, xmlfile=None):
        return "Validated logical and physical structure of %s and %s" % (xmlfile, ip.ObjectPath)


class ValidateIntegrity(tasks.ValidateIntegrity):
    event_type = 10263


class CreateTAR(DBTask):
    event_type = 10270

    """
    Creates a TAR file from the specified directory

    Args:
        dirname: The directory to create a TAR from
        tarname: The name of the tar file
    """

    def run(self, dirname=None, tarname=None):
        base_dir = os.path.basename(os.path.normpath(dirname))

        with tarfile.TarFile(tarname, 'w') as new_tar:
            new_tar.add(dirname, base_dir)

        self.set_progress(100, total=100)
        return tarname

    def undo(self, dirname=None, tarname=None):
        pass

    def event_outcome_success(self, dirname=None, tarname=None):
        return "Created %s from %s" % (tarname, dirname)


class CreateZIP(DBTask):
    event_type = 10271

    """
    Creates a ZIP file from the specified directory

    Args:
        dirname: The directory to create a ZIP from
        zipname: The name of the zip file
    """

    def run(self, dirname=None, zipname=None):
        with zipfile.ZipFile(zipname, 'w') as new_zip:
            for root, dirs, files in os.walk(dirname):
                for d in dirs:
                    filepath = os.path.join(root, d)
                    arcname = filepath[len(dirname) + 1:]
                    new_zip.write(filepath, arcname)
                for f in files:
                    filepath = os.path.join(root, f)
                    arcname = filepath[len(dirname) + 1:]
                    new_zip.write(filepath, arcname)

        self.set_progress(100, total=100)
        return zipname

    def undo(self, dirname=None, zipname=None):
        pass

    def event_outcome_success(self, dirname=None, zipname=None):
        return "Created %s from %s" % (zipname, dirname)

class UpdateIPStatus(tasks.UpdateIPStatus):
    event_type = 10280


class SubmitSIP(DBTask):
    event_type = 10300

    def run(self, ip=None):
        srcdir = Path.objects.get(entity="path_preingest_reception").value
        reception = Path.objects.get(entity="path_ingest_reception").value
        container_format = ip.get_container_format()

        src = os.path.join(srcdir, str(ip.pk) + ".%s" % container_format)
        dst = os.path.join(reception, str(ip.pk) + ".%s" % container_format)
        shutil.copyfile(src, dst)

        src = os.path.join(srcdir, str(ip.pk) + ".xml")
        dst = os.path.join(reception, str(ip.pk) + ".xml")
        shutil.copyfile(src, dst)

        event_profile = ip.get_profile('event')
        dst = os.path.join(reception, "%s_event_profile.json" % ip.pk)

        with open(dst, "w") as f:
            json = serializers.serialize('json', [event_profile])
            f.write(json)

        self.set_progress(100, total=100)

    def undo(self, ip=None):
        pass

    def event_outcome_success(self, ip=None):
        return "Submitted %s" % (ip.pk)
