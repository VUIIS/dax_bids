#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Download almost everything you need from Xnat

@author: Benjamin Yvernault, Electrical Engineering, Vanderbilt University

WARNING: very important,--update OPTIONS isn't working completely.
         The last modified resources date can't be access right now on XNAT.
         This OPTIONS will only download the resources that you don't have
         the previous download or the one that where deleted and reuploaded
         since your last upload. If this message appears, it means the
         attributes hasn't been added yet to XNAT.
'''

from __future__ import print_function

from builtins import next
from builtins import str
from builtins import zip

import os
import re
import sys
import csv
import copy
import json
import time
import shutil
import getpass
import logging
import nibabel as nib
from dax import XnatUtils
from dax import XnatToBids
from datetime import datetime
from xml.etree import cElementTree as ET


DEFAULT_REPORT_NAME = 'download_report.csv'
DEFAULT_COMMAND_LINE = 'download_commandLine.txt'
DEFAULT_CSV_LIST = ['object_type', 'project_id', 'subject_label',
                    'session_type', 'session_label', 'as_label', 'as_type',
                    'as_description', 'quality', 'resource', 'fpath']
SCAN_HEADER = ['object_type', 'project_id', 'subject_label', 'session_type',
               'session_label', 'ID', 'type', 'series_description', 'quality',
               'resource', 'fpath']
ASSESSOR_HEADER = ['object_type', 'project_id', 'subject_label',
                   'session_type', 'session_label', 'label', 'proctype',
                   'procstatus', 'qcstatus', 'resource', 'fpath']
DEFAULT_ARGUMENTS = {'status': None, 'withoutS': None, 'session': None,
                     'withoutA': None, 'ignorecsv': False, 'overwrite': False,
                     'subject': None, 'outputfile': None,
                     'selectionScan': None, 'resourcesA': None,
                     'selectionAssessor': None, 'resourcesS': None,
                     'username': None, 'update': False, 'csvfile': None,
                     'host': None, 'qcstatus': None,
                     'assessortype': None, 'scantype': None, 'oneDir': False,
                     'project': None, 'qualities': None, 'directory': None}
DESCRIPTION = """What is the script doing :
   *Download filtered data from XNAT to your local computer using the \
different OPTIONS.

Examples:
   *Download all resources for all scans/assessors in a project:
        Xnatdownload -p PID -d /tmp/downloadPID -s all --rs all -a all --ra all
   *Download NIFTI for T1,fMRI:
        Xnatdownload -p PID -d /tmp/downloadPID -s T1,fMRI --rs NIFTI
   *Download only the outlogs for fMRIQA assessors that failed:
        Xnatdownload -p PID -d /tmp/downloadPID -a fMRIQA --status JOB_FAILED \
--ra OUTLOG
   *Download PDF for assessors that Needs QA:
        Xnatdownload -p PID -d /tmp/downloadPID -a all --qcstatus="Needs QA" \
--ra OUTLOG
   *Download NIFTI for T1 for some sessions :
        Xnatdownload -p PID -d /tmp/downloadPID --sess 109309,189308 -s all \
--rs NIFTI
   *Download same data than previous line but overwrite the data:
        Xnatdownload -p PID -d /tmp/downloadPID --sess 109309,189308 -s all \
--rs NIFTI --overwrite
   *Download data described by a csvfile (follow template) :
        Xnatdownload -d /tmp/downloadPID -c  upload_sheet.csv
"""


def setup_info_logger(name, logfile):
    """
    Using logger for the executables output.
     Setting the information for the logger.

    :param name: Name of the logger
    :param logfile: log file path to write outputs
    :return: logging object
    """
    if logfile:
        handler = logging.FileHandler(logfile, 'w')
    else:
        handler = logging.StreamHandler()

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def get_option_list(option):
    """
    Method to convert option value to a list, None if empty, all if all
    selected

    :param option: string representing the option
    :return: None if empty, 'all' if all selected, list otherwise
    """
    if not option:
        return None
    elif option.lower() == 'all':
        return 'all'
    elif option == 'nan':
        return None
    else:
        return option.split(',')


def get_resources_list(object_dict, resources_list):
    """
    Method to get the list of resources labels

    :param object_dict: dictionary to describe XNAT object parameters
    :param resources_list: list of resources requested from the user
    :return: None if empty, 'all' if all selected, list otherwise
    """
    # Get list of resources' label

    if resources_list == 'all':
        if object_dict.has_key("resources"):
            res_list = object_dict['resources']
        else:
            res_list = []
            resources = XNAT.select('/project/{project}/subject/{subject}/experiment/{experiment}/assessor/{assessor}/resources'.format(project=object_dict['project_id'],
                                                                                                                  subject=object_dict['subject_label'],
                                                                                                                  experiment=object_dict['session_label'],
                                                                                                                  assessor=object_dict['label']))
            for resource in resources:
                res_list.append(resource.label())
    else:
        res_list=resources_list
    return res_list


def write_cmd_file(cmd_file, overwrite):
    """
    Method to write the Xnatdownload command line use in a text file

    :param cmd_file: path for the file
    :param overwrite: overwriting the file or not
    :return: None
    """
    cmdargs = sys.argv
    cmdstr = os.path.abspath(cmdargs[0]) + " " + " ".join(cmdargs[1:])
    # Check the previous cmd_file if one and warning if cmd different:
    if os.path.exists(cmd_file) and not overwrite:
        f = open(cmd_file, 'r')
        previouscmd = f.read().strip()
        f.close()
        if previouscmd != cmdstr:
            LOGGER.info('WARNING: the command line you are running is \
different than the one you ran last time. You might have some data different \
for both command.')
            LOGGER.info(' *previous command: %s' % (previouscmd))
            LOGGER.info(' *current command:  %s' % (cmdstr))
    # Write new cmd
    f = open(cmd_file, 'w')
    f.write(cmdstr + '\n')
    f.close()


def read_txtfile():
    """
    Method to read the text file specifying the data to download

    :return: list of scans downloaded, list of assessors downloaded
    """
    scans_list = list()
    asses_list = list()
    if os.path.exists(OPTIONS.csvfile):
        with open(OPTIONS.csvfile, 'rb') as csvfileread:
            csvreader = csv.reader(csvfileread, delimiter=',')
            for row in csvreader:
                if row[0] == 'scan':
                    scans_list.append(dict(list(zip(SCAN_HEADER, row))))
                elif row[0] == 'assessor':
                    asses_list.append(dict(list(zip(ASSESSOR_HEADER, row))))
        if not OPTIONS.resourcesS:
            OPTIONS.resourcesS = ','.join(set([s['resource']
                                               for s in scans_list]))
            LOGGER.info('WARNING: resources for scan not set. Using resources \
found in csvfile.')
        if not OPTIONS.resourcesA:
            OPTIONS.resourcesA = ','.join(set([a['resource']
                                               for a in asses_list]))
            LOGGER.info('WARNING: resources for assessor not set. Using \
resources found in csvfile.')
    else:
        LOGGER.info('ERROR: file %s not found. Check if the file exists.'
                    % (OPTIONS.csvfile))
    return scans_list, asses_list


def read_report():
    """
    Method to read the previous report from Xnatdownload

    :return: list of scans downloaded, list of assessors downloaded,
             last time Xnatdownload ran, old rows in csv
    """
    scans_dl_dict = dict()
    asses_dl_dict = dict()
    old_rows = list()
    last_dl_date = None
    rp_path = os.path.join(DIRECTORY, DEFAULT_REPORT_NAME)
    if os.path.exists(rp_path):
        with open(rp_path, 'rb') as csvfileread:
            csvreader = csv.reader(csvfileread, delimiter=',')
            # get the last_update
            last_dl_date = int(
                csvreader.next()[0].split('=')[1]
                                   .replace('-', '')
                                   .replace(':', '')
                                   .replace(' ', ''))
            # remove header
            next(csvreader)
            for row in csvreader:
                if row[0] == 'scan':
                    label = '-x-'.join([row[1], row[2], row[4], row[5]])
                    if label in list(scans_dl_dict.keys()):
                        scans_dl_dict[label].append(row[-2])
                    else:
                        scans_dl_dict[label] = [row[-2]]
                    old_rows.append(row)
                elif row[0] == 'assessor':
                    if row[5] in list(asses_dl_dict.keys()):
                        asses_dl_dict[row[5]].append(row[-2])
                    else:
                        asses_dl_dict[row[5]] = [row[-2]]
                    old_rows.append(row)
    LOGGER.info('Reading download_report.csv from previous download: done.')
    return scans_dl_dict, asses_dl_dict, last_dl_date, old_rows


def extract_information():
    """
    Method to extract all the information from XNAT

    :return: list of scans, list of assessors, last time Xnatdownload ran,
             old rows in csv
    """
    scans_list = list()
    asses_list = list()
    old_rows = list()
    last_dl_date = None
    if OPTIONS.csvfile:
        scans_list, asses_list = read_txtfile()
    else:
        # check project_list:
        projects_list = check_projects(get_option_list(OPTIONS.project))
        if not projects_list:
            LOGGER.info('ERROR: You do not have access to the projects ID \
given as a parameter or it does not exist on XNAT.')
            sys.exit()
        # list of scans and assessors for the all the project cat together.
        for project in projects_list:
            if OPTIONS.scantype:
                scans_list.extend(XNAT.get_project_scans(project))
            if OPTIONS.assessortype:
                asses_list.extend(XnatUtils.list_project_assessors(
                    XNAT, project))
         #   if OPTIONS.subject:
          #      scans_list.extend(XNAT.get_project_scans(project))
           #     asses_list.extend(XnatUtils.list_assessors(XNAT, project, get_option_list(OPTIONS.subject), get_option_list(OPTIONS.session)))
        # Read previous report
        scans_dl_dict, asses_dl_dict, last_dl_date, old_rows = read_report()
        if OPTIONS.overwrite:
            last_dl_date = None
        elif OPTIONS.update:
            pass
        else:
            # filter by former download:
            msg = 'filtering scans and assessors from previous download.'
            LOGGER.info(msg)
            scans_list = [x for x in scans_list
                          if need_download(
                              x, scans_dl_dict,
                              get_option_list(OPTIONS.resourcesS))]
            asses_list = [x for x in asses_list
                          if need_download(
                              x, asses_dl_dict,
                              get_option_list(OPTIONS.resourcesA))]
            last_dl_date = None  # We don't update the one downloaded already
    return scans_list, asses_list, last_dl_date, old_rows


def filter_subj_sess(obj_list):
    """Method to filter the objects by subjects/sessions specified by user.

    :param obj_list: list of xnat objects dictionaries to download
                     (scans or assessors)
    :return: filtered list of objects
    """
    # Variables:
    subjects = get_option_list(OPTIONS.subject)
    if subjects == 'all':
        subjects = None
    sessions = get_option_list(OPTIONS.session)
    if sessions == 'all':
        sessions = None
    obj_list_filtered = obj_list
    if subjects:
        print('Filtering the subjects...')
        obj_list_filtered = XnatUtils.filter_list_dicts_regex(
            obj_list_filtered, 'subject_label', subjects,
            full_regex=OPTIONS.full_regex)
    if sessions:
        print('Filtering the sessions...')
        obj_list_filtered = XnatUtils.filter_list_dicts_regex(
            obj_list_filtered, 'session_label', sessions,
            full_regex=OPTIONS.full_regex)
    return obj_list_filtered


def filter_scans(scans_list):
    """Method to filter the list of scans from XNAT with the options.

    :param scans_list: list of scans dictionaries to download
    :return: filtered list of objects
    """
    # Variables:
    scan_types = get_option_list(OPTIONS.scantype)
    without = get_option_list(OPTIONS.withoutS)
    qualities = get_option_list(OPTIONS.qualities)
    if not OPTIONS.csvfile and not scan_types and not without:
        return list()
    if scan_types and scan_types != 'all':
        scans_list = XnatUtils.filter_list_dicts_regex(
            scans_list, 'type', scan_types,
            full_regex=OPTIONS.full_regex)
    if without:
        scans_list = XnatUtils.filter_list_dicts_regex(
            scans_list, 'type', without, nor=True,
            full_regex=OPTIONS.full_regex)
    if qualities and qualities != 'all':
        scans_list = XnatUtils.filter_list_dicts_regex(
            scans_list, 'quality', qualities,
            full_regex=OPTIONS.full_regex)
    if without == 'all':
        return list()
    return scans_list


def filter_assessors(asses_list):
    """Method to filter the list of assessors from XNAT with the options.

    :param asses_list: list of assessors dictionaries to download
    :return: filtered list of objects
    """
    # Variables:
    proc_types = get_option_list(OPTIONS.assessortype)
    without = get_option_list(OPTIONS.withoutA)
    status = get_option_list(OPTIONS.status)
    qcstatus = get_option_list(OPTIONS.qcstatus)
    if not OPTIONS.csvfile and not proc_types and not without:
        # if not csvfile and proctypes and without or not set, then we don't
        # download anything
        return list()
    if proc_types and proc_types != 'all':
        asses_list = XnatUtils.filter_list_dicts_regex(
            asses_list, 'proctype', proc_types,
            full_regex=OPTIONS.full_regex)
    if without:
        asses_list = XnatUtils.filter_list_dicts_regex(
            asses_list, 'proctype', without, nor=True,
            full_regex=OPTIONS.full_regex)
    if status and status != 'all':
        asses_list = XnatUtils.filter_list_dicts_regex(
            asses_list, 'procstatus', status,
            full_regex=OPTIONS.full_regex)
    if qcstatus and qcstatus != 'all':
        asses_list = XnatUtils.filter_list_dicts_regex(
            asses_list, 'qcstatus', qcstatus,
            full_regex=OPTIONS.full_regex)
    if without == 'all':
        return list()
    return asses_list


def extract_obj_one_subject(project, subject, obj_list):
    """
    Method to filter the objects in the list and keep the one for a specific
    subject

    :param project: project ID on XNAT
    :param subject: subject label on XNAT
    :param obj_list: list of xnat objects dictionaries to download
                     (scans/assessors)
    :return: filtered list of objects
    """
    return [x for x in obj_list
            if x['subject_label'] == subject and x['project_id'] == project]


def need_download(object_dict, objects_dl_dict, resources_list):
    """
    Method to confirm that an object need to be download (scan or assessor)

    :param object_dict: dictionary to describe XNAT object parameters
    :param objects_dl_dict: dictionary with all the previous scans/assessors
                            downloaded with their resources
                            keys: label (project-x-subject-x-session-x-scan/
                            asse) value: list of resources
    :param resources_list: list of resources to download for the object in
                           question
    :return: True if data need to be downloaded, False otherwise
    """
    if objects_dl_dict:
        if 'series_description' in list(object_dict.keys()):
            label = '-x-'.join([object_dict['project_id'],
                                object_dict['subject_label'],
                                object_dict['session_label'],
                                object_dict['ID']])
        elif 'proctype' in list(object_dict.keys()):
            label = object_dict['label']
        if label in list(objects_dl_dict.keys()):
            # Checking the resources already downloaded and the resources
            # requested
            res_list = get_resources_list(object_dict, resources_list)
            if set(objects_dl_dict[label]) == set(res_list):
                return False
            else:
                return True
        else:
            return True
    else:
        return True


def get_file_timestamp(filepath):
    """
    Get the file timestamp when it was last modified on the local Station

    :param filepath: path to the file
    :return: timestamp with format %Y%m%d%H%M%S
    """
    date_object = datetime.strptime(time.ctime(os.path.getmtime(filepath)),
                                    '%a %b %d %H:%M:%S %Y')
    return '{:%Y%m%d%H%M%S}'.format(date_object)


def check_projects(projects_list):
    """
    Method to check if the user has access to the project on XNAT

    :param projects_list: list of projects to download from
    :return: list of accessible projects on XNAT
    """
    for project in projects_list:
        project_obj = XNAT.select('/project/{}'.format(project))
        if not project_obj.exists():
            LOGGER.info('WARNING: Project %s does not exist on XNAT. Remove \
this project from the list.' % (project))
            projects_list.remove(project)
        else:
            if not len(XNAT.get_subjects(project)) > 0:
                LOGGER.info("WARNING: You don't access to the project: %s. \
Remove this project from the list." % (project))
                projects_list.remove(project)
    return projects_list


# Extract list of scan/assessors dictionary that will get download
def get_xnat_information():
    """
    Method to extract the list of scans/assessors dictionaries from XNAT
    project

    :return: list project_subject, list of scans, list of assessors,
             last time download, old data downloaded in the report
    """
    LOGGER.info('INFO: Accessing scans/assessors information from XNAT.')
    # Extract information from OPTIONS and the report:
    scans_list, asses_list, last_dl_date, old_rows = extract_information()
    msg = 'Extracting information from Xnat and previous download: done.'
    LOGGER.info(msg)
    # filter by attributes:
    scans_list = filter_scans(scans_list)
    asses_list = filter_assessors(asses_list)
    # filter by subject/session:
    scans_list = filter_subj_sess(scans_list)
    asses_list = filter_subj_sess(asses_list)
    # Extract list of subject to download in order:
    ps_list = list()
    if scans_list:
        ps_list.extend([s['project_id'] + '-x-' + s['subject_label']
                        for s in scans_list])
    if asses_list:
        ps_list.extend([s['project_id'] + '-x-' + s['subject_label']
                        for s in asses_list])
    if OPTIONS.project:
        # Print the number of scans/assessors per Project:
        LOGGER.info('INFO: Number of scans/assessors that needs to be \
download per Project (after filters):')
        LOGGER.info('---------------------------------------------------------\
------')
        LOGGER.info('| %*s | %*s | %*s |' % (-20, 'Project ID',
                                             -15, 'Number of Scans',
                                             -19, 'Number of Assessors'))
        project_list = check_projects(get_option_list(OPTIONS.project))
        for project in project_list:
            LOGGER.info('-----------------------------------------------------\
----------')
            LOGGER.info('| %*s | %*s | %*s |' % (
                -20, project,
                -15, len([s for s in scans_list
                          if s['project_id'] == project]),
                -19, len([a for a in asses_list
                          if a['project_id'] == project])))
        LOGGER.info('---------------------------------------------------------\
------\n')
    return set(ps_list), scans_list, asses_list, last_dl_date, old_rows


def get_scan_path(scan_dict):
    """
    Method to generate the path to download a scan data

    :param scan_dict: dictionary containing the scan information
    :return: path to download the scan data
    """
    if OPTIONS.oneDir:
        scan_path = DIRECTORY
    else:
        if 'type' in scan_dict.keys():
            st = scan_dict['type'].strip().replace('/', '_').replace(" ", "")
        else:
            st = 'UNK'
        scan_label = '%s-x-%s' % (scan_dict['ID'], st)
        if 'series_description' in scan_dict.keys():
            if scan_dict['series_description'] != '':
                sd = scan_dict['series_description'].strip()\
                                                    .replace('/', '_')\
                                                    .replace(" ", "")\
                                                    .replace(":", '_')
                scan_label = '%s-x-%s' % (scan_label, sd)
        scan_path = os.path.join(
            DIRECTORY, scan_dict['project_id'], scan_dict['subject_label'],
            scan_dict['session_label'], scan_label)
    return scan_path


def get_assessor_path(assessor_dict):
    """
    Method to generate the path where to download an assessor data

    :param directory: local download directory for the data
    :param asse_dict: dictionary containing the assessor information
    :return: path to download the assessor data
    """
    if OPTIONS.oneDir:
        proc_path = DIRECTORY
    else:
        proc_path = os.path.join(DIRECTORY, assessor_dict['project_id'],
                                 assessor_dict['subject_label'],
                                 assessor_dict['session_label'],
                                 assessor_dict['label'])
    return proc_path


def download_data_xnat():
    """
    Main Method to download the data for projects by looping
     through the project/subjects

    :return: None
    """
    #tmp_count = 0
    # resources
    scans_res_list = get_option_list(OPTIONS.resourcesS)
    asses_res_list = get_option_list(OPTIONS.resourcesA)
    # Number of subjects
    number = len(PS_LIST)
    # Download:
    LOGGER.info('INFO: Downloading Data for each pair project/subject..')
    for index, ps in enumerate(sorted(PS_LIST)):
        project = ps.split('-x-')[0]
        subject = ps.split('-x-')[1]
        LOGGER.info(' * %s/%s Project/Subject : %s/%s' % (str(index + 1),
                                                          str(number),
                                                          project,
                                                          subject))
        # SCAN
        for scan_dict in extract_obj_one_subject(project, subject, SC_LIST):
            #if tmp_count == 2:
            #    break
            #tmp_count = tmp_count + 1
            if 'type' in scan_dict.keys():
                LOGGER.info('  +session %s -- scan %s -- type: %s' % (
                    scan_dict['session_label'], scan_dict['ID'],
                    scan_dict['type']))
            else:
                LOGGER.info('  +session %s -- scan %s --' % (
                    scan_dict['session_label'], scan_dict['ID']))
            scan_path = get_scan_path(scan_dict)
            if OPTIONS.overwrite and os.path.exists(scan_path):
                shutil.rmtree(scan_path)
            # Create the line for the report
            if CSVWRITER is not None and not OPTIONS.csvfile:
                # deepcopy to start each line from this row
                row = copy.deepcopy(['scan', scan_dict['project_id'],
                                     scan_dict['subject_label'],
                                     scan_dict['session_type'],
                                     scan_dict['session_label'],
                                     scan_dict['ID'],
                                     scan_dict['type'],
                                     scan_dict['series_description'],
                                     scan_dict['quality']])
            else:
                row = None
            download_scan(scan_path, scan_dict, scans_res_list, row, LAST_D)
        # ASSESSOR
        for assessor_dict in extract_obj_one_subject(project, subject, A_LIST):
            LOGGER.info('  +proc %s' % (assessor_dict['label']))
            proc_path = get_assessor_path(assessor_dict)
            if OPTIONS.overwrite and os.path.exists(proc_path):
                shutil.rmtree(proc_path)
            # Create the line for the report
            if CSVWRITER is not None and not OPTIONS.csvfile:
                # deepcopy to start each line from this row
                row = copy.deepcopy(['assessor', assessor_dict['project_id'],
                                     assessor_dict['subject_label'],
                                     assessor_dict['session_type'],
                                     assessor_dict['session_label'],
                                     assessor_dict['label'],
                                     assessor_dict['proctype'],
                                     assessor_dict['procstatus'],
                                     assessor_dict['qcstatus']])
            else:
                row = None
            download_assessor(proc_path, assessor_dict, asses_res_list, row,
                              LAST_D)


def download_scan(directory, scan_dict, resources_list, row, last_dl_date):
    """
    Method to download the data for one specific scan

    :param directory: local download directory for the data
    :param scan_dict: dictionary describing the scan
                      (see XnatUtils.list_assessors)
    :param resources_list: list of resources labels to download
    :param row: row describing downloaded data to add to the report
    :param last_dl_date: time at the last download call
    :return: None
    """
    try:
        scan_obj = XnatUtils.get_full_object(XNAT, scan_dict)
    except KeyError:
        # TODO: BenM/xnatutils refactor/this shouldn't be hit under any
        # circumstances; figure out if it is still needed and, if not, remove
        scan_obj = XNAT.select('/project/{project}/subject/{subject}/experiment/{experiment}/scan/{scan}'. format(project=scan_dict['project_id'],
                                                                                                                  subject=scan_dict['subject_label'],
                                                                                                                  experiment=scan_dict['session_label'],
                                                                                                                  scan=scan_dict['ID']))
    if not scan_obj.exists():
        LOGGER.info('  ->WARNING: No scan with the ID given.')
    else:
        res_list = get_resources_list(scan_dict, resources_list)
        for rname in res_list:
            if rname == 'PARREC':
                dl_path = os.path.join(directory, rname)
                if not os.path.exists(dl_path):
                    os.makedirs(dl_path)
                download_resource(dl_path, scan_obj.resource('PAR'),
                                  'PAR', row, True, 'file', last_dl_date)
                download_resource(dl_path, scan_obj.resource('REC'),
                                  'REC', row, True, 'file', last_dl_date)
            else:
                label = '-x-'.join([scan_dict['project_id'],
                                    scan_dict['subject_label'],
                                    scan_dict['session_label'],
                                    scan_dict['ID'], rname])
                download_resource(directory, scan_obj.resource(rname),
                                  rname, row, OPTIONS.oneDir, label,
                                  last_dl_date)


def download_assessor(directory, assessor_dict, resources_list, row,
                      last_dl_date):
    """
    Method to download the data for one specific assessor

    :param directory: local download directory for the data
    :param assessor_dict: dictionary describing the assessor
                          (see XnatUtils.list_assessors)
    :param resources_list: list of resources labels to download
    :param row: row describing downloaded data to add to the report
    :param last_dl_date: time at the last download call
    :return: None
    """
    assessor_obj = XnatUtils.get_full_object(XNAT, assessor_dict)
    if not assessor_obj.exists():
        LOGGER.info('  ->WARNING: No processor with the label given.')
    else:
        out_reslist = get_resources_list(assessor_dict, resources_list)
        for rname in out_reslist:
            download_resource(directory, assessor_obj.out_resource(rname),
                              rname, row, OPTIONS.oneDir,
                              assessor_dict['label'] + '-x-' + rname,
                              last_dl_date)


def download_resource(directory, res_obj, res_label, row, one_dir, label=None,
                      last_dl_date=None):
    """
    Method to download the data for one specific resource (scan or assessor)

    :param directory: local download directory for the data
    :param res_obj: pyxnat resource Eobject
    :param res_label: resource label on XNAT
    :param row: row describing downloaded data to add to the report
    :param one_dir: download the data in the same directory
    :param label: name for the file or folder downloaded if oneDir=True
    :param last_dl_date: time at the last download call
    :return: None
    """
    row = copy.deepcopy(row)  # NOT KEEPING NEXT CHANGES
    if not res_obj.exists():
        LOGGER.info('   >Resource %s: WARNING -- no resource %s '
                    % (res_label, res_label))
    else:
        if not res_obj.files().get():
            LOGGER.info('   >Resource %s: ERROR -- No files in the resources.'
                        % (res_label))
        else:
            if one_dir:
                one_dir_download(directory, res_obj, res_label, label,
                                 row, last_dl_date)
            else:
                default_download(directory, res_obj, res_label,
                                 row, last_dl_date)


def one_dir_download(directory, res_obj, res_label, label,
                     row, last_dl_date):
    """
    Method to download the data in one directory (renaming the files)

    :param directory: local download directory for the data
    :param res_obj: pyxnat resource Eobject
    :param res_label: resource label on XNAT
    :param label: name for the file or folder downloaded
    :param row: row describing downloaded data to add to the report
    :param last_dl_date: time at the last download call
    :return: None
    """
    # Add Resource label
    _ld_mod = int(XnatUtils.get_resource_lastdate_modified(XNAT, res_obj))
    if row is not None:
        row.append(res_label)
    if len(res_obj.files().get()) > 1:
        res_path = os.path.join(directory, label)
        # Add fpath
        if row is not None:
            row.append(res_path)
        if not os.path.exists(res_path) or \
           (last_dl_date and int(get_file_timestamp(res_path)) < _ld_mod):
            dl_files(res_obj, directory)
            shutil.move(os.path.join(directory, res_label), res_path)
            if CSVWRITER:
                CSVWRITER.writerow(row)
        else:
            LOGGER.info('   >Resource %s: Skipping resource. Up-to-date.'
                        % (res_label))
    else:
        # Add fpath
        res_path = os.path.join(
            directory, label + '__' + res_obj.files().get()[0])
        if row is not None:
            row.append(res_path)
        if not os.path.exists(res_path) or \
           (last_dl_date and int(get_file_timestamp(res_path)) < _ld_mod):
            dl_file(res_obj, res_path)
            if CSVWRITER:
                CSVWRITER.writerow(row)
        else:
            LOGGER.info('   >Resource %s: Skipping resource. Up-to-date.'
                        % (res_label))


def default_download(directory, res_obj, res_label, row, last_dl_date):
    """
    Default download method for a resource (not one_dir_download)

    :param directory: local download directory for the data
    :param xnat: pyxnat.interface object
    :param res_obj: pyxnat resource Eobject
    :param res_label: resource label on XNAT
    :param row: row describing downloaded data to add to the report
    :param last_dl_date: time at the last download call
    :return: None
    """
    res_path = os.path.join(directory, res_label)
    # Add Resource label
    if row is not None:
        row.append(res_label)
        row.append(res_path)
    _ld_mod = int(XnatUtils.get_resource_lastdate_modified(XNAT, res_obj))
    if not os.path.exists(res_path) or \
       (last_dl_date and int(get_file_timestamp(res_path)) < _ld_mod) \
       or not os.listdir(res_path):
        dl_files(res_obj, directory)
        if CSVWRITER and not OPTIONS.csvfile:
            CSVWRITER.writerow(row)
    else:
        LOGGER.info('   >Resource %s: Skipping resource. Up-to-date.'
                    % (res_label))


def dl_files(res_obj, directory):
    """
    Method to download all the files from a resource

    :param res_obj: pyxnat resource Eobject
    :param directory: local download directory for the data
    :return: None
    """
    # TODO: BenM/xnatutils refactor/appears to me a lot of unnecessary fetching / refetching here
    # if more than one file:
    if len(res_obj.files().get()) > 1:
        # create a dir with the resourcename:
        output_dir = os.path.join(directory, res_obj.label())
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        LOGGER.info('   >Resource %s: Downloading all resources as a zip and \
unzipping it...' % (res_obj.label()))
        res_obj.get(output_dir, extract=False)
        # not sure the extract True is working
        zip_path = os.path.join(output_dir, res_obj.label() + '.zip')
        os.system('unzip -o -d "%s" "%s" > /dev/null' % (output_dir, zip_path))
        os.remove(zip_path)
    # if only one, if using download all resources, download it and unzip it
    # if it's a zip
    else:
        LOGGER.info('   >Resource %s: Downloading resource.'
                    % (res_obj.label()))
        res_fname = res_obj.files().get()[0]
        output_dir = os.path.join(directory, res_obj.label())
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        res_obj.file(res_fname).get(os.path.join(output_dir, res_fname))
        if os.path.join(directory, res_fname)[-3:] == 'zip':
            fpath = os.path.join(output_dir, res_fname)
            cmd = 'unzip -o -d "%s" "%s" > /dev/null' % (output_dir, fpath)
            os.system(cmd)
            os.remove(fpath)


def dl_file(res_obj, fpath):
    """
    Method to download one file from a resource

    :param res_obj: pyxnat resource Eobject
    :param fpath: local path for the file to be downloaded
    :return: None
    """
    res_obj.file(res_obj.files()[0].label()).get(fpath)


def download_specific_scan():
    """
    Method to download a scan specified by the user

    :return: None
    """
    if OPTIONS.resourcesS:
        LOGGER.info('Selected Scan: %s' % (OPTIONS.selectionScan))
        # Variables:
        if not OPTIONS.oneDir:
            scan_path = os.path.join(DIRECTORY, OPTIONS.selectionScan)
        else:
            scan_path = DIRECTORY
        scan_resources = get_option_list(OPTIONS.resourcesS)
        qualities = get_option_list(OPTIONS.qualities)
        # Get scan obj dict:
        scan_dict = dict(list(zip(
            ['project_id', 'subject_label', 'session_label', 'ID'],
            OPTIONS.selectionScan.split('-x-'))))
        scan_dict['scan_id'] = scan_dict['ID']
        scan_obj = XnatUtils.get_full_object(XNAT, scan_dict)
        if scan_obj.exists():
            if not qualities or \
               (qualities and scan_obj.attrs.get('quality') in qualities):
                scan_dict['series_description'] = scan_obj.attrs.get(
                    'series_description')
                scan_dict['type'] = scan_obj.attrs.get('type')
                sub_dir = '-x-'.join([scan_dict['project_id'],
                                      scan_dict['subject_label'],
                                      scan_dict['session_label'],
                                      scan_dict['ID']])
                if not OPTIONS.oneDir:
                    scan_path = os.path.join(DIRECTORY, sub_dir)
                download_scan(scan_path, scan_dict, scan_resources,
                              None, last_dl_date=None)
    else:
        LOGGER.info('WARNING: selected scan found but no resource specified')


def download_specific_assessor():
    """
    Method to download a assessor specified by the user

    :return: None
    """
    if OPTIONS.resourcesA:
        LOGGER.info('Selected Processor: %s' % (OPTIONS.selectionAssessor))
        # Variables:
        if not OPTIONS.oneDir:
            assessor_path = os.path.join(DIRECTORY, OPTIONS.selectionAssessor)
        else:
            assessor_path = DIRECTORY
        assessors_resources = get_option_list(OPTIONS.resourcesA)
        status = get_option_list(OPTIONS.status)
        # Get assessor obj dict:
        assessor_dict = dict(list(zip(
            ['project_id', 'subject_label', 'session_label', 'ID'],
            OPTIONS.selectionAssessor.split('-x-')[0:3])))
        assessor_dict['label'] = OPTIONS.selectionAssessor
        assessor_dict['subject_id'] = 'proc:genProcData'
        assessor_obj = XnatUtils.select_assessor(XNAT, assessor_dict['label'])
        if not assessor_obj.exists():
            LOGGER.info('  ->WARNING: No processor with the label given.')
        else:
            if 'FS' == OPTIONS.selectionAssessor.split('-x-')[-1]:
                assessor_dict['xsiType'] = 'fs:fsData'
                jobstatus = assessor_obj.attrs.get('fs:fsData/procstatus')
            else:
                assessor_dict['xsiType'] = 'proc:genProcData'
                jobstatus = assessor_obj.attrs.get(
                    'proc:genProcData/procstatus')
            if not status or (status and jobstatus in status):
                if not OPTIONS.oneDir:
                    assessor_path = os.path.join(DIRECTORY, assessor_dict['label'])
                out_reslist = get_resources_list(
                    assessor_dict, assessors_resources)
                for rname in out_reslist:
                    download_resource(assessor_path,
                                      assessor_obj.out_resource(rname),
                                      rname, None, OPTIONS.oneDir,
                                      assessor_dict['label'] + '-x-' + rname,
                                      last_dl_date=None)
    else:
        warn = 'WARNING: selected assessor found but no resource specified'
        LOGGER.info(warn)

def check_options():
    """
    Method to check the options specified by the user

    :return: True if OPTIONS are fine, False otherwise
    """
    # The OPTIONS :
    if not OPTIONS.directory:
        print('OPTION ERROR: directory not specified. Use option \
-d/--directory.')
        return False
    # can not have select scan and assessor and filetext in one command line
    if OPTIONS.csvfile:
        if not os.path.exists(os.path.abspath(OPTIONS.csvfile)):
            print('OPTION ERROR: -c/--csv OPTIONS detected. csvfile %s not \
found.' % (os.path.abspath(OPTIONS.csvfile)))
            return False
        else:
            print('OPTION WARNING: -c/--csv OPTIONS detected. Reading from \
the csvfile.')
            return True
    if not OPTIONS.selectionScan and \
       not OPTIONS.selectionAssessor and not OPTIONS.csvfile:
        if not OPTIONS.project:
            print('OPTION ERROR: You need to set the OPTIONS -p with the \
projects ID from Xnat.')
            return False
    if OPTIONS.update:
        if not os.path.exists(os.path.abspath(OPTIONS.directory)):
            print('OPTION ERROR: You used the option --continue but the \
directory you selected does not exist.')
            return False
    if OPTIONS.overwrite and OPTIONS.update:
        print("OPTION ERROR: You used the option --overwrite and --update. \
You can't select both in the same call.")
        return False
    # Resources
    if (OPTIONS.selectionScan or OPTIONS.withoutS or OPTIONS.scantype) and \
       not OPTIONS.resourcesS:
        print('OPTION ERROR: No resources types specified for the scans. \
Use --rs.')
        return False
    if not OPTIONS.resourcesA and \
       (OPTIONS.selectionAssessor or OPTIONS.withoutA or OPTIONS.assessortype):
        print('OPTION ERROR: No resources types specified for the assessors. \
Use --ra.')
        return False
    # Types
    if [OPTIONS.withoutS, OPTIONS.withoutA, OPTIONS.assessortype,
        OPTIONS.scantype] == [None, None, None, None] and \
       not OPTIONS.selectionScan and \
       not OPTIONS.selectionAssessor:
        print('OPTION WARNING: No scans/assessors types selected (OPTIONS: \
-s/-a/--WOS/--WOA). Nothing to download.')
        return False
    # can not have withoutS and scantype together
    if OPTIONS.withoutS:
        print('OPTION WARNING: You are using --WOS: all scans types except \
<%s> will be downloaded.' % (OPTIONS.withoutS))
    # can not have withoutA and assessortype together
    if OPTIONS.withoutA:
        print('OPTION WARNING: You are using --WOA: all assessors types \
except <%s> will be downloaded.' % (OPTIONS.withoutA))
    # Check inputs:
    if (not OPTIONS.selectionScan and not OPTIONS.scantype) and \
       OPTIONS.resourcesS:
        print('OPTION ERROR: resources selected for scans but no types \
specified. Use -s or --WOS.')
        return False
    if (not OPTIONS.selectionAssessor and not OPTIONS.assessortype) and \
       OPTIONS.resourcesA:
        print('OPTION ERROR: resources selected for assessors but no types \
specified. Use -a or --WOA.')
        return False
    # BIDS
    if OPTIONS.xnat2bids and not OPTIONS.bids_dir:
        print('OPTION ERROR: BIDS directory not specified. Use option \
--bids_dir.')
        return False
    return True


def main_display():
    """
    Main display of the executables before any process

    :return: None
    """
    print('################################################################')
    print('#                         XNATDOWNLOAD                         #')
    print('#                                                              #')
    print('# Developed by the MASI Lab Vanderbilt University, TN, USA.    #')
    print('# If issues, please start a thread here:                       #')
    print('# https://groups.google.com/forum/#!forum/vuiis-cci            #')
    print('# Usage:                                                       #')
    print('#     Download data from XNAT based on input args              #')
    print('# Parameters :                                                 #')
    if vars(OPTIONS) == DEFAULT_ARGUMENTS:
        print('#     No Arguments given                                     \
  #')
        print('#     See the help bellow or Use "Xnatdownload" -h           \
  #')
        print('##############################################################\
##\n')
        PARSER.print_help()
        sys.exit()
    else:
        if OPTIONS.host:
            print('#     %*s -> %*s#' % (
                -20, 'XNAT Host', -33, get_proper_str(OPTIONS.host)))
        if OPTIONS.username:
            print('#     %*s -> %*s#' % (
                -20, 'XNAT User', -33, get_proper_str(OPTIONS.username)))
        if OPTIONS.directory:
            print('#     %*s -> %*s#' % (
                -20, 'Directory',
                -33, get_proper_str(OPTIONS.directory, True)))
        if OPTIONS.selectionScan:
            print('#     %*s -> %*s#' % (
                -20, 'selected Scan',
                -33, get_proper_str(OPTIONS.selectionScan, True)))
            if OPTIONS.resourcesS:
                print('#     %*s -> %*s#' % (
                    -20, 'Resources Scan',
                    -33, get_proper_str(OPTIONS.resourcesS)))
        elif OPTIONS.selectionAssessor:
            print('#     %*s -> %*s#' % (
                -20, 'selected Process',
                -33, get_proper_str(OPTIONS.selectionAssessor, True)))
            if OPTIONS.resourcesA:
                print('#     %*s -> %*s#' % (
                    -20, 'Resources Process',
                    -33, get_proper_str(OPTIONS.resourcesA)))
        else:
            if OPTIONS.csvfile:
                print('#     %*s -> %*s#' % (
                    -20, 'File csv',
                    -33, get_proper_str(OPTIONS.csvfile, True)))
                if OPTIONS.resourcesS:
                    print('#     %*s -> %*s#' % (
                        -20, 'Resources Scan',
                        -33, get_proper_str(OPTIONS.resourcesS)))
                if OPTIONS.resourcesA:
                    print('#     %*s -> %*s#' % (
                        -20, 'Resources Process',
                        -33, get_proper_str(OPTIONS.resourcesA)))
            elif OPTIONS.project:
                print('#     %*s -> %*s#' % (
                    -20, 'Project(s)', -33, get_proper_str(OPTIONS.project)))
                if OPTIONS.subject:
                    print('#     %*s -> %*s#' % (
                        -20, 'Subject(s)',
                        -33, get_proper_str(OPTIONS.subject)))
                if OPTIONS.session:
                    print('#     %*s -> %*s#' % (
                        -20, 'Session(s)',
                        -33, get_proper_str(OPTIONS.session)))
                if OPTIONS.scantype:
                    print('#     %*s -> %*s#' % (
                        -20, 'Scan types',
                        -33, get_proper_str(OPTIONS.scantype)))
                if OPTIONS.withoutS:
                    print('#     %*s -> %*s#' % (
                        -20, 'Without Scan',
                        -33, get_proper_str(OPTIONS.withoutS)))
                if OPTIONS.resourcesS:
                    print('#     %*s -> %*s#' % (
                        -20, 'Resources Scan',
                        -33, get_proper_str(OPTIONS.resourcesS)))
                if OPTIONS.qualities:
                    print('#     %*s -> %*s#' % (
                        -20, 'Scan Qualities',
                        -33, get_proper_str(OPTIONS.qualities)))
                if OPTIONS.assessortype:
                    print('#     %*s -> %*s#' % (
                        -20, 'Process types',
                        -33, get_proper_str(OPTIONS.assessortype)))
                if OPTIONS.withoutA:
                    print('#     %*s -> %*s#' % (
                        -20, 'Without Process',
                        -33, get_proper_str(OPTIONS.withoutA)))
                if OPTIONS.resourcesA:
                    print('#     %*s -> %*s#' % (
                        -20, 'Resources Process',
                        -33, get_proper_str(OPTIONS.resourcesA)))
                if OPTIONS.status:
                    print('#     %*s -> %*s#' % (
                        -20, 'Job Status',
                        -33, get_proper_str(OPTIONS.status)))
                if OPTIONS.qcstatus:
                    print('#     %*s -> %*s#' % (
                        -20, 'QC Status',
                        -33, get_proper_str(OPTIONS.qcstatus)))
        if OPTIONS.oneDir:
            print('#     %*s -> %*s#' % (-20, 'No sub-dir mode', -33, 'on'))
        if OPTIONS.overwrite:
            print('#     %*s -> %*s#' % (-20, 'Overwrite mode', -33, 'on'))
        if OPTIONS.update:
            print('#     %*s -> %*s#' % (-20, 'Update mode', -33, 'on'))
        if OPTIONS.xnat2bids:
            print('#     %*s -> %*s#' % (-20, 'XNAT to BIDS mode', -33, 'on'))
        if OPTIONS.bids_dir:
            print('#     %*s -> %*s#' % (
                -20, 'BIDS Directory',
                -33, get_proper_str(OPTIONS.bids_dir, True)))
        if OPTIONS.outputfile:
            print('#     %*s -> %*s#' % (
                -20, 'Output file',
                -33, get_proper_str(OPTIONS.outputfile, True)))
        print('##############################################################\
##')
        print("IMPORTANT WARNING FOR ALL USERS: ")
        print("  --update OPTIONS isn't working.")
        print("  The last modified resources date can't be access right now ")
        print("  if XNAT version is less than 1.6.5.")
        print('==============================================================\
=======')


def get_proper_str(str_option, end=False):
    """
    Method to shorten a string into the proper size for display

    :param str_option: string to shorten
    :param end: keep the end of the string visible (default beginning)
    :return: shortened string
    """
    if len(str_option) > 32:
        if end:
            return '...' + str_option[-29:]
        else:
            return str_option[:29] + '...'
    else:
        return str_option


def parse_args():
    """
    Method to parse arguments base on ArgumentParser

    :return: parser object
    """
    from argparse import ArgumentParser, RawDescriptionHelpFormatter
    argp = ArgumentParser(prog='Xnatdownload', description=DESCRIPTION,
                          formatter_class=RawDescriptionHelpFormatter)
    argp.add_argument('--host', dest='host', default=None,
                      help='Host for XNAT. Default: using $XNAT_HOST.')
    argp.add_argument('-u', '--username', dest='username', default=None,
                      help='Username for XNAT. Default: using $XNAT_USER.')
    argp.add_argument("-p", "--project", dest="project", default=None,
                      help="Project(s) ID on Xnat")
    argp.add_argument("-d", "--directory", dest="directory", default=None,
                      help="Directory where the data will be download")
    argp.add_argument("-D", "--oneDirectory", dest="oneDir",
                      action="store_true",
                      help="Data will be downloaded in the same directory. \
No sub-directory.")
    # Download for only one Subject
    argp.add_argument("--subj", dest="subject", default=None,
                      help="filter scans/assessors by their subject label. \
Format: a comma separated string (E.G: --subj VUSTP2,VUSTP3).")
    # Download for only one Subject
    argp.add_argument("--sess", dest="session", default=None,
                      help="filter scans/assessors by their session label. \
Format: a comma separated string (E.G: --sess VUSTP2b,VUSTP3a)")
    # for a specific scantype or specific Assessor
    argp.add_argument("-s", "--scantype", dest="scantype", default=None,
                      help="filter scans by their types (required to download \
scans). Format: a comma separated string (E.G : -s T1,MPRAGE,REST). To \
download all types, set to 'all'.")
    argp.add_argument("-a", "--assessortype", dest="assessortype",
                      default=None,
                      help="filter assessors by their types (required to \
download assessors). Format: a comma separated string (E.G : -a \
fMRIQA,dtiQA_v2,Multi_Atlas). To download all types, set to 'all'.")
    argp.add_argument("--WOS", dest="withoutS", default=None,
                      help="filter scans by their types and removed the one \
with the specified types. Format: a comma separated string (E.G : --WOS \
T1,MPRAGE,REST).")
    argp.add_argument("--WOP", dest="withoutA", default=None,
                      help="filter assessors by their types and removed the \
one with the specified types. Format: a comma separated string (E.G : --WOP \
fMRIQA,dtiQA).")
    # specific attributes
    argp.add_argument("--quality", dest="qualities", default=None,
                      help="filter scans by their quality. Format: a comma \
separated string (E.G: --quality usable,questionable,unusable).")
    argp.add_argument("--status", dest="status", default=None,
                      help="filter assessors by their job status. Format: a \
comma separated string.")
    argp.add_argument("--qcstatus", dest="qcstatus", default=None,
                      help="filter assessors by their quality control status. \
Format: a comma separated string.")
    # Download from the following csvfile
    argp.add_argument("-c", "--csvfile", dest="csvfile", default=None,
                      help="CSV file with the following header: object_type,\
project_id,subject_label,session_type,session_label,as_label. object_type must be 'scan' \
or 'assessor' and as_label the scan ID or assessor label.")
    # specific Resources
    argp.add_argument("--rs", dest="resourcesS", default=None,
                      help="Resources you want to download for scans. \
E.g : --rs NIFTI,PAR,REC.")
    argp.add_argument("--ra", dest="resourcesA", default=None,
                      help="Resources you want to download for assessors. \
E.g : --ra OUTLOG,PDF,PBS.")
    # select only one scan
    argp.add_argument("--selectionS", dest="selectionScan", default=None,
                      help="Download from only one selected scan.By default : \
no selection. E.G : project-x-subject-x-session-x-scan")
    # select only one assessor
    argp.add_argument("--selectionP", dest="selectionAssessor", default=None,
                      help="Download from only one selected processor.By \
default : no selection. E.G : assessor_label")
    # Overwrite
    argp.add_argument("--overwrite", dest="overwrite", action="store_true",
                      help="Overwrite the previous data downloaded with the \
same command.")
    # update
    argp.add_argument("--update", dest="update", action="store_true",
                      help="Update the files from XNAT that have been \
downloaded with the newest version if there is one (not working yet).")
    # Regex
    argp.add_argument("--fullRegex", dest="full_regex", action='store_true',
                      help="Use full regex for filtering data.")
    # Output
    argp.add_argument("-o", "--output", dest="outputfile", default=None,
                      help="Write the display in a file giving to this \
OPTIONS.")
    # Ignore csv
    argp.add_argument("-i", "--ignore", dest="ignorecsv", action='store_true',
                      help="Ignore reading of the csv report file")
    #BIDS
    argp.add_argument("-b", "--bids", dest="xnat2bids", action='store_true',
                      help="Transform to BIDS format after XNAT download")

    argp.add_argument("--bids_dir", dest="bids_dir", default=None,
                      help="Directory to store the bids dataset")
    return argp


if __name__ == '__main__':
    PARSER = parse_args()
    OPTIONS = PARSER.parse_args()
    main_display()
    SHOULD_RUN = check_options()
    LOGGER = setup_info_logger('Xnatdownload', OPTIONS.outputfile)

    if OPTIONS.assessortype and not OPTIONS.resourcesA:
        LOGGER.warn('No resource set for assessor type selected. NO donwload \
for assessors.')
        OPTIONS.assessortype = None
    if OPTIONS.scantype and not OPTIONS.resourcesS:
        LOGGER.warn('No resource set for scan type selected. NO download for \
scans.')
        OPTIONS.scantype = None

    if SHOULD_RUN:
        # Directory:
        DIRECTORY = os.path.abspath(OPTIONS.directory)
        if not os.path.exists(DIRECTORY):
            os.makedirs(DIRECTORY)
        # write the command:
        write_cmd_file(os.path.join(DIRECTORY, DEFAULT_COMMAND_LINE),
                       OPTIONS.overwrite)
        if OPTIONS.host:
            HOST = OPTIONS.host
        else:
            HOST = os.environ['XNAT_HOST']
        if OPTIONS.username:
            MSG = "Please provide the password for user <%s> on xnat(%s):"
            PWD = getpass.getpass(prompt=MSG % (OPTIONS.username, HOST))
        else:
            PWD = None

        MSG = 'INFO: connection to xnat <%s>:' % (HOST)
        LOGGER.info(MSG)
        with XnatUtils.get_interface(host=OPTIONS.host,
                                     user=OPTIONS.username,
                                     pwd=PWD) as XNAT:
            if OPTIONS.selectionScan or OPTIONS.selectionAssessor:
                CSVWRITER = None
                if OPTIONS.selectionScan:
                    download_specific_scan()
                if OPTIONS.selectionAssessor:
                    download_specific_assessor()
            else:
                PS_LIST, SC_LIST, A_LIST, LAST_D, OLD_ROWS = \
                    get_xnat_information()
                # open the report file:
                if not OPTIONS.ignorecsv:
                    rep_path = os.path.join(DIRECTORY, DEFAULT_REPORT_NAME)
                    with open(rep_path, 'wb') as csvfilewrite:
                        CSVWRITER = csv.writer(csvfilewrite, delimiter=',')
                        # Today date
                        msg = 'Last download date = {:%Y-%m-%d %H:%M:%S}'
                        CSVWRITER.writerow([msg.format(datetime.now())])
                        CSVWRITER.writerow(DEFAULT_CSV_LIST)
                        if OPTIONS.overwrite or OPTIONS.update:
                            pass
                        else:
                            for ROW in OLD_ROWS:
                                CSVWRITER.writerow(ROW)
                        download_data_xnat()
                else:
                    CSVWRITER = None
                    download_data_xnat()
        if OPTIONS.xnat2bids:
            project = OPTIONS.project
            BIDS_DIR = OPTIONS.bids_dir
        #TRANFOMR XNAT2BIDS REFACTOR
            XnatToBids.transform_to_bids(XNAT, DIRECTORY, project, BIDS_DIR, LOGGER)

    LOGGER.info('============================================================')
