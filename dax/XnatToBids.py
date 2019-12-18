'''
Tranform XNAT folder to BIDS format

@author: Praitayini Kanakaraj, Electrical Engineering, Vanderbilt University

'''
import os
import re
import json
import shutil
import nibabel as nib
from xml.etree import cElementTree as ET


def transform_to_bids(XNAT, DIRECTORY, project):
    """
     Method to move the data from XNAT folders to BIDS format by looping through
     subjects/projects

     :return: None
     """
    sd_dict = sd_datatype_mapping(XNAT, project)
    data_type_l = ["anat", "func", "fmap", "dwi", "unknown_bids"]

    subj_idx = 1
    sess_idx = 1
    for proj in os.listdir(DIRECTORY):
        if os.path.isdir(os.path.join(DIRECTORY, proj)):
            for subj in os.listdir(os.path.join(DIRECTORY, proj)):
                #subj_idx = 1
                for sess in os.listdir(os.path.join(DIRECTORY, proj, subj)):
                    sess_path = os.path.join(DIRECTORY, proj, subj, sess)
                    BIDS_DIR = os.path.join(os.getcwd(), 'BIDS')
                    if not os.path.exists(BIDS_DIR):
                        os.mkdir(BIDS_DIR)
                    #sess_idx = 1
                    bids_sess_path = os.path.join(BIDS_DIR, proj, 'sub-'+"{0:0=2d}".format(subj_idx), 'ses-'+"{0:0=2d}".format(sess_idx))
                    for scan in os.listdir(sess_path):
                        if scan not in data_type_l:
                            for scan_resources in os.listdir(os.path.join(sess_path, scan)):
                                for scan_file in os.listdir(os.path.join(sess_path, scan, scan_resources)):
                                    scan_type = scan.split('-x-')[1]
                                    #if "_" in scan_type:
                                    #    scan_type = " ".join(scan_type.split("_"))
                                    data_type = sd_dict.get(scan_type, "unknown_bids")
                                    if not os.path.exists(os.path.join(bids_sess_path, data_type)):
                                        os.makedirs(os.path.join(bids_sess_path, data_type))
                                        shutil.move(os.path.join(sess_path, scan, scan_resources, scan_file),
                                                    os.path.join(bids_sess_path, data_type))
                                        bids_fname = bids_filename(bids_sess_path, data_type, scan, scan_file, XNAT, project)
                                        os.rename(os.path.join(bids_sess_path, data_type, scan_file), os.path.join(bids_sess_path, data_type, bids_fname))
                                        if scan_resources == 'NIFTI' and not data_type == "unknown_bids":
                                            xnat_path = 'URI'
                                            xnat_prov = {"XNATfilename": scan_file,
                                                         "XNATProvenance": xnat_path}
                                            if data_type == 'func':
                                                img = nib.load(os.path.join(bids_sess_path, data_type, bids_fname))
                                                TR = img.header.get_zooms()[3]
                                                xnat_prov = {"XNATfilename": scan_file,
                                                             "XNATProvenance": xnat_path,
                                                             "TaskName": 'task_type',
                                                             "RepetitionTime": float(TR)}
                                            with open(os.path.join(os.path.join(bids_sess_path, data_type, bids_fname).split('.')[0] + ".json"), "w+") as f:
                                                json.dump(xnat_prov, f, indent=2)
                            shutil.rmtree(os.path.join(sess_path, scan))
                    sess_idx = sess_idx + 1
                subj_idx = subj_idx + 1
    dataset_description_file(BIDS_DIR, XNAT, project)

def sd_datatype_mapping(XNAT, project):
    """
      Method to map series description to task type for functional scans

      :return: mapping dict
    """
    sd_dict = {}
    #if OPTIONS.selectionScan:
        #project = OPTIONS.selectionScan.split('-')[0]
    #else:
    #project = OPTIONS.project
    if XNAT.select('/data/projects/' + project + '/resources/BIDS_datatype').exists():
        for res in XNAT.select('/data/projects/' + project + '/resources/BIDS_datatype/files').get():
            if res.endswith('.json'):
                with open(XNAT.select('/data/projects/' + project + '/resources/BIDS_datatype/files/' + res).get(), "r+") as f:
                    datatype_mapping = json.load(f)
                    sd_dict = datatype_mapping[project]
    else:
        scans_list_global = XNAT.get_project_scans('LANDMAN')

        for sd in scans_list_global:
            c = re.search('T1|T2|T1W', sd['series_description'])
            if not c == None:
                sd_anat = sd['series_description'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                sd_dict[sd_anat] = "anat"

        for sd in scans_list_global:
            c = re.search('rest|Resting state|Rest', sd['series_description'], flags=re.IGNORECASE)
            if not c == None:
                sd_func = sd['series_description'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                sd_dict[sd_func] = "func"

        for sd in scans_list_global:
            c = re.search('dwi|dti', sd['series_description'], flags=re.IGNORECASE)
            if not c == None:
                sd_dwi = sd['series_description'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                sd_dict[sd_dwi] = "dwi"

        for sd in scans_list_global:
            c = re.search('Field|B0', sd['series_description'], flags=re.IGNORECASE)
            if not c == None:
                sd_fmap = sd['series_description'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                sd_dict[sd_fmap] = "fmap"
        with open("global_mapping.json", "w+") as f:
            json.dump(sd_dict, f, indent=2)

    return sd_dict

def bids_filename(bids_sess_path, data_type, scan, scan_file, XNAT, project):
    """
     Method to rename files based on BIDS naming scheme

    :param bids_sess_path: session path for BIDS format
    :param data_type: BIDS datatype (anat or func or dwi or fmap)
    :param scan: scan folder
    :param scan_file: scan file
    :return: string (filename for the scans)
     """
    sub_name = bids_sess_path.split('/')[-2]
    ses_name = bids_sess_path.split('/')[-1]
    scan_id = scan_file.split('-x-')[3].split('.')[0]
    st = scan.split('-x-')[1]
    tk_dict = sd_tasktype_mapping(XNAT, project)
    if data_type == "anat":
        bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'T1w' + '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname

    elif data_type == "func":
        if st in tk_dict.keys():
            task_type = tk_dict[st]
            bids_fname = sub_name + '_' + ses_name + '_task-' + task_type + '_acq-' + scan_id + '_run-01' + '_' + 'bold' + '.' + ".".join(scan_file.split('.')[1:])
        else:
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'bold' + '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname
    elif data_type == "dwi":
        if label == "BVEC":
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'dwi' + '.' + 'bvec'

        elif label == "BVAL":
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'dwi' + '.' + 'bval'

        else:
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'dwi' + '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname

    elif data_type == "fmap":
        bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_bold' + '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname

def sd_tasktype_mapping(XNAT, project):
    """
     Method to map series description to task type for functional scans

     :return: mapping dict
     """
    tk_dict = {}
    #project = OPTIONS.project
    if XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype').exists():
        for res in XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype/files').get():
            if res.endswith('.json'):
                with open(XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype/files/' + res).get(), "r+") as f:
                    datatype_mapping = json.load(f)
                    tk_dict = datatype_mapping[project]
    else:
        scans_list_global = XNAT.get_project_scans('LANDMAN')
        for sd in scans_list_global:
            c = re.search('rest|Resting state|Rest', sd['series_description'], flags=re.IGNORECASE)
            if not c == None:
                sd_func = sd['series_description'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                tk_dict[sd_func] = "rest"
        with open("global_tk_mapping.json", "w+") as f:
            json.dump(tk_dict, f, indent=2)
    return tk_dict

def dataset_description_file(BIDS_DIR, XNAT, project):
    """
    Build BIDS dataset description json file

    :return: None
    """

    BIDSVERSION = "1.0.1"
    dataset_description = dict()
    dataset_description['BIDSVersion'] = BIDSVERSION
    dataset_description['Name'] = project
    dataset_description['DatasetDOI'] = 'xnat' #TODO:HOST
    project_info = XNAT.select('/project/' + project).get()
    project_info = ET.fromstring(project_info)
    PI_element = project_info.findall('{http://nrg.wustl.edu/xnat}PI')
    #dataset_description['Author'] = PI_element[0][1].text, PI_element[0][0].text
    dd_file = os.path.join(BIDS_DIR, project)
    if not os.path.exists(dd_file):
        os.mkdir(dd_file)
    with open(os.path.join(dd_file, 'dataset_description.json'), 'w+') as f:
        json.dump(dataset_description, f, indent=2)

