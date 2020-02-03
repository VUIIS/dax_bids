'''
Tranform XNAT folder to BIDS format

@author: Praitayini Kanakaraj, Electrical Engineering, Vanderbilt University

'''
import os
import re
import sys
import json
import shutil
import nibabel as nib
from xml.etree import cElementTree as ET


def transform_to_bids(XNAT, DIRECTORY, project, BIDS_DIR, LOGGER):
    """
     Method to move the data from XNAT folders to BIDS format (based on datatype) by looping through
     subjects/projects.

     :return: None
     """
    LOGGER.info("Moving files to the BIDS folder")
    sd_dict = sd_datatype_mapping(XNAT, project)
    data_type_l = ["anat", "func", "fmap", "dwi", "unknown_bids"]
    subj_idx = 1
    sess_idx = 1
    for proj in os.listdir(DIRECTORY):
        if proj == project and os.path.isdir(os.path.join(DIRECTORY, proj)):
            for subj in os.listdir(os.path.join(DIRECTORY, proj)):
                #subj_idx = 1
                for sess in os.listdir(os.path.join(DIRECTORY, proj, subj)):
                    sess_path = os.path.join(DIRECTORY, proj, subj, sess)
                    if not os.path.exists(BIDS_DIR):
                        os.mkdir(BIDS_DIR)
                    #sess_idx = 1
                    bids_sess_path = os.path.join(BIDS_DIR, proj, 'sub-'+"{0:0=2d}".format(subj_idx),
                                                  'ses-'+"{0:0=2d}".format(sess_idx))
                    for scan in os.listdir(sess_path):
                        if scan not in data_type_l:
                            for scan_resources in os.listdir(os.path.join(sess_path, scan)):
                                for scan_file in os.listdir(os.path.join(sess_path, scan, scan_resources)):
                                    if not scan_file.endswith('.json'):
                                        scan_type = scan.split('-x-')[1]
                                        #TODO: when unknown_bids --> error
                                        data_type = sd_dict.get(scan_type, "unknown_bids")
                                        if not os.path.exists(os.path.join(bids_sess_path, data_type)):
                                            os.makedirs(os.path.join(bids_sess_path, data_type))
                                        shutil.move(os.path.join(sess_path, scan, scan_resources, scan_file),
                                                    os.path.join(bids_sess_path, data_type))
                                        bids_fname = bids_filename(bids_sess_path, data_type, scan, scan_file, XNAT, project)
                                        bids_res_path = os.path.join(bids_sess_path, data_type, bids_fname)
                                        os.rename(os.path.join(bids_sess_path, data_type, scan_file), bids_res_path)
                                        create_json_sidecar(XNAT, scan_resources, data_type, scan_file, scan,
                                                            bids_res_path, scan_type, project, sess, subj, LOGGER)
                            shutil.rmtree(os.path.join(sess_path, scan))
                    sess_idx = sess_idx + 1
                subj_idx = subj_idx + 1
    dataset_description_file(BIDS_DIR, XNAT, project)

def create_json_sidecar(XNAT, scan_resources, data_type, scan_file, scan, bids_res_path, scan_type, project, sess, subj, LOGGER):
    """
    Method to create the json sidecars for NIFTI data
    :return:
    """

    scan_path = '/projects/%s/subjects/%s/experiments/%s/scans/%s' % (project, subj,
                                                                 sess, scan.split('-x-')[0])

    if scan_resources == 'NIFTI' and not data_type == "unknown_bids":
        scan_info = XNAT.select(scan_path)
        res_path = scan_path + '/resources/NIFTI/files'
        res_files = XNAT.select(res_path).get()
        is_json_present = False
        for res in res_files:
            if not res.endswith('.json'):
                continue
            else:
                is_json_present = True
        if data_type != 'func':
            if not is_json_present:
                xnat_prov = {"XNATfilename": scan_file,
                             "XNATProvenance": XNAT.host + scan_info._uri}
            else:
                with open(XNAT.select(os.path.join(res_path, res)).get(), "r") as f:
                    xnat_prov = json.load(f)
                    xnat_detail = {"XNATfilename": scan_file,
                             "XNATProvenance": XNAT.host + scan_info._uri}
                    xnat_prov.update(xnat_detail)

        else:
            tr_dict = sd_tr_mapping(XNAT, project, LOGGER)
            TR_bidsmap = float(tr_dict.get(scan_type))
            tk_dict = sd_tasktype_mapping(XNAT, project)
            task_type = tk_dict.get(scan_type)
            img = nib.load(bids_res_path)
            TR_nifti = float(img.header['pixdim'][4])
            if not is_json_present:
                if TR_nifti == TR_bidsmap:
                    LOGGER.warn('No json. The TR bids mapping (%s) is equal to TR in nifti header (%s) for scan %s in session %s. '
                                'Created json with TR in nifti header'% (TR_bidsmap,TR_nifti,scan.split('-x-')[0],sess))
                    xnat_prov = {"XNATfilename": scan_file,
                                 "XNATProvenance": XNAT.host + scan_info._uri,
                                 "TaskName": task_type,
                                 "RepetitionTime": TR_nifti}
                else:
                    LOGGER.warn('No json. The TR bids mapping (%s) is not equal to TR in nifti header (%s) for scan %s in session %s. '
                                'Creating json with TR in bidsmapping and updating nifti header'
                                % (TR_bidsmap,TR_nifti,scan.split('-x-')[0],sess))
                    xnat_prov = {"XNATfilename": scan_file,
                                 "XNATProvenance": XNAT.host + scan_info._uri,
                                 "TaskName": task_type,
                                 "RepetitionTime": TR_bidsmap}
                    img.header['pixdim'][4] = TR_bidsmap
                    nib.save(img,bids_res_path)
            else:
                with open(XNAT.select(os.path.join(res_path, res)).get(), "r") as f:
                    xnat_prov = json.load(f)
                    TR_json = float(xnat_prov['RepetitionTime'])
                    #check if TR_json == TR_nifti
                    if TR_json != TR_bidsmap:
                        LOGGER.warn('The TR bids mapping (%s) is not equal to TR in json sidecar (%s) for scan %s in session %s. '
                                    'Creating json with TR in bidsmapping and updating nifti header' % (
                                    TR_bidsmap, TR_json, scan.split('-x-')[0], sess))
                        new_TR = {'RepetitionTime': TR_bidsmap,
                                  "XNATfilename": scan_file,
                                  "XNATProvenance": XNAT.host + scan_info._uri}
                        xnat_prov.update(new_TR)
                        img.header['pixdim'][4] = TR_bidsmap
                        nib.save(img, bids_res_path)
                    else:
                        with open(XNAT.select(os.path.join(res_path, res)).get(), "r") as f:
                            xnat_prov = json.load(f)
                            xnat_detail = {"XNATfilename": scan_file,
                                           "XNATProvenance": XNAT.host + scan_info._uri}
                            xnat_prov.update(xnat_detail)
        with open(os.path.join(bids_res_path.split('.')[0] + ".json"), "w+") as f:
            json.dump(xnat_prov, f, indent=2)


def sd_tr_mapping(XNAT, project, LOGGER):
    tr_dict = {}
    if XNAT.select('/data/projects/' + project + '/resources/BIDS_repetition_time_sec').exists():
        for res in XNAT.select('/data/projects/' + project + '/resources/BIDS_repetition_time_sec/files').get():
            if res.endswith('.json'):
                with open(XNAT.select('/data/projects/' + project + '/resources/BIDS_repetition_time_sec/files/' + res).get(),
                          "r+") as f:
                    tr_mapping = json.load(f)
                    tr_dict = tr_mapping[project]
                    tr_dict = {k.strip().replace('/', '_').replace(" ", "").replace(":", '_')
                               : v for k, v in tr_dict.items()}
    else:
        LOGGER.error("ERROR no TR mapping at project level")
        sys.exit()
    return tr_dict

def sd_datatype_mapping(XNAT, project):
    """
      Method to map scan type to task type for functional scans

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
                    sd_dict = {k.strip().replace('/', '_').replace(" ", "").replace(":", '_')
                               : v for k, v in sd_dict.items()}
    else:
        scans_list_global = XNAT.get_project_scans('LANDMAN')

        for sd in scans_list_global:
            c = re.search('T1|T2|T1W', sd['scan_type'])
            if not c == None:
                sd_anat = sd['scan_type'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                sd_dict[sd_anat] = "anat"

        for sd in scans_list_global:
            c = re.search('rest|Resting state|Rest', sd['scan_type'], flags=re.IGNORECASE)
            if not c == None:
                sd_func = sd['scan_type'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                sd_dict[sd_func] = "func"

        for sd in scans_list_global:
            c = re.search('dwi|dti', sd['scan_type'], flags=re.IGNORECASE)
            if not c == None:
                sd_dwi = sd['scan_type'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
                sd_dict[sd_dwi] = "dwi"

        for sd in scans_list_global:
            c = re.search('Field|B0', sd['scan_type'], flags=re.IGNORECASE)
            if not c == None:
                sd_fmap = sd['scan_type'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
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
    scan_id = scan.split('-x-')[0]
    st = scan.split('-x-')[1]
    if data_type == "anat":
        bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'T1w' + \
                     '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname

    elif data_type == "func":
        tk_dict = sd_tasktype_mapping(XNAT, project)
        if st in tk_dict.keys():
            task_type = tk_dict[st]
            bids_fname = sub_name + '_' + ses_name + '_task-' + task_type + '_acq-' + scan_id + '_run-01' \
                         + '_' + 'bold' + '.' + ".".join(scan_file.split('.')[1:])
        else:
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'bold' + \
                         '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname
    elif data_type == "dwi":
        if label == "BVEC":
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'dwi' + '.' + 'bvec'

        elif label == "BVAL":
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'dwi' + '.' + 'bval'

        else:
            bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'dwi' + \
                         '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname

    elif data_type == "fmap":
        bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_bold' + \
                     '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname

def sd_tasktype_mapping(XNAT, project):
    """
     Method to map scan type to task type for functional scans

     :return: mapping dict
     """
    tk_dict = {}
    #project = OPTIONS.project
    if XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype').exists():
        for res in XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype/files').get():
            if res.endswith('.json'):
                with open(XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype/files/'
                                      + res).get(), "r+") as f:
                    datatype_mapping = json.load(f)
                    tk_dict = datatype_mapping[project]
                    tk_dict = {k.strip().replace('/', '_').replace(" ", "").replace(":", '_')
                               : v for k, v in tk_dict.items()}

    else:
        scans_list_global = XNAT.get_project_scans('LANDMAN')
        for sd in scans_list_global:
            c = re.search('rest|Resting state|Rest', sd['scan_type'], flags=re.IGNORECASE)
            if not c == None:
                sd_func = sd['scan_type'].strip().replace('/', '_').replace(" ", "").replace(":", '_')
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
    dataset_description['DatasetDOI'] = XNAT.host
    project_info = XNAT.select('/project/' + project).get()
    project_info = ET.fromstring(project_info)
    PI_element = project_info.findall('{http://nrg.wustl.edu/xnat}PI')
    if len(PI_element) > 0:
        dataset_description['Author'] = PI_element[0][1].text, PI_element[0][0].text
    else:
        dataset_description['Author'] = "No Author defined on XNAT"
    dd_file = os.path.join(BIDS_DIR, project)
    if not os.path.exists(dd_file):
        os.makedirs(dd_file)
    with open(os.path.join(dd_file, 'dataset_description.json'), 'w+') as f:
        json.dump(dataset_description, f, indent=2)

