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
    LOGGER.info("--------------- BIDS --------------")
    LOGGER.info("INFO: Moving files to the BIDS folder...")
    sd_dict = sd_datatype_mapping(XNAT, project, LOGGER)
    data_type_l = ["anat", "func", "fmap", "dwi", "unknown_bids"]
    subj_idx = 1
    sess_idx = 1
    project_scans = XNAT.get_project_scans(project)
    for proj in os.listdir(DIRECTORY):
        if proj == project and os.path.isdir(os.path.join(DIRECTORY, proj)):
            for subj in os.listdir(os.path.join(DIRECTORY, proj)):
                # subj_idx = 1
                LOGGER.info("* Subject %s" % (subj))
                for sess in os.listdir(os.path.join(DIRECTORY, proj, subj)):
                    LOGGER.info(" * Session %s" % (sess))
                    sess_path = os.path.join(DIRECTORY, proj, subj, sess)
                    # sess_idx = 1
                    for scan in os.listdir(sess_path):
                        if scan not in data_type_l:
                            for scan_resources in os.listdir(os.path.join(sess_path, scan)):
                                for scan_file in os.listdir(os.path.join(sess_path, scan, scan_resources)):
                                    if not scan_file.endswith('.json'):
                                        scan_id = scan.split('-x-')[0]
                                        for x in project_scans:
                                            if x['ID'] == scan_id and x['subject_label'] == subj:
                                                scan_type = x['scan_type']
                                        data_type = sd_dict.get(scan_type, "unknown_bids")
                                        if data_type == "unknown_bids":
                                            LOGGER.info(
                                                'ERROR: Scan type %s does not have a BIDS datatype mapping at default and project level. Use BidsMapping Tool' % (
                                                    scan_type))
                                            sys.exit()
                                        if not os.path.exists(BIDS_DIR):
                                            os.mkdir(BIDS_DIR)
                                        bids_sess_path = os.path.join(BIDS_DIR, proj,
                                                                      'sub-' + "{0:0=2d}".format(subj_idx),
                                                                      'ses-' + "{0:0=2d}".format(sess_idx))
                                        if not os.path.exists(os.path.join(bids_sess_path, data_type)):
                                            os.makedirs(os.path.join(bids_sess_path, data_type))

                                        LOGGER.info("\t+Moving scan %s to %s folder" % (scan_file, data_type))
                                        bids_fname = bids_filename(bids_sess_path, data_type, scan, scan_file,
                                                                   XNAT, project, scan_type, LOGGER)
                                        bids_res_path = os.path.join(bids_sess_path, data_type, bids_fname)
                                        # os.rename(os.path.join(bids_sess_path, data_type, scan_file), bids_res_path)
                                        scan_res_path = os.path.join(sess_path, scan, scan_resources, scan_file)
                                        create_json_sidecar(XNAT, scan_resources, sess_path, data_type, scan_file, scan,
                                                            bids_res_path, scan_res_path, scan_type, project, sess,
                                                            subj, LOGGER)
                                        shutil.move(os.path.join(sess_path, scan, scan_resources, scan_file),
                                                    os.path.join(bids_sess_path, data_type))
                                        os.rename(os.path.join(bids_sess_path, data_type, scan_file), bids_res_path)
                                        # bids_fname = bids_filename(bids_sess_path, data_type, scan, scan_file,
                                        #                           XNAT, project, scan_type, LOGGER)
                                        # bids_res_path = os.path.join(bids_sess_path, data_type, bids_fname)
                                        # os.rename(os.path.join(bids_sess_path, data_type, scan_file), bids_res_path)
                                        # create_json_sidecar(XNAT, scan_resources, data_type, scan_file, scan,
                                        #                   bids_res_path, scan_type, project, sess, subj, LOGGER)
                                    else:
                                        os.remove(os.path.join(sess_path, scan, scan_resources, scan_file))
                                        #LOGGER.info("\t\t>Removing XNAT json sidecar %s" % (scan_file))
                            # shutil.rmtree(os.path.join(sess_path, scan))
                            # for root, dirs, files in os.walk(os.path.join(sess_path, scan)):
                            LOGGER.info("\t\t>Removing XNAT resource %s folder" % (scan_resources))
                            os.rmdir(os.path.join(sess_path, scan, scan_resources))
                            os.rmdir(os.path.join(sess_path, scan))
                    sess_idx = sess_idx + 1
                    LOGGER.info("\t>Removing XNAT session %s folder" % (sess))
                    # shutil.rmtree(sess_path)
                    os.rmdir(sess_path)
                subj_idx = subj_idx + 1
                LOGGER.info("\t>Removing XNAT subject %s folder" % (subj))
                os.rmdir(os.path.join(DIRECTORY, proj, subj))
    dataset_description_file(BIDS_DIR, XNAT, project)


def create_json_sidecar(XNAT, scan_resources, sess_path, data_type, scan_file, scan, bids_res_path, scan_res_path, scan_type,
                        project, sess, subj,
                        LOGGER):
    """
    Method to create the json sidecars for NIFTI data
    :return:
    """

    scan_path = '/projects/%s/subjects/%s/experiments/%s/scans/%s' % (project, subj,
                                                                      sess, scan.split('-x-')[0])

    # Return if not NIFTI and data type is unkonwn_bids
    if scan_resources != 'NIFTI' or data_type == "unknown_bids":
        return

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
        xnat_detail = {"XNATfilename": scan_file,
                       "XNATProvenance": XNAT.host + scan_info._uri}
        if not is_json_present:
            LOGGER.info('\t\t>No json sidecar. Created json sidecar with xnat info.')
            xnat_prov = xnat_detail
        else:
            with open(XNAT.select(os.path.join(res_path, res)).get(), "r") as f:
                LOGGER.info('\t\t>Json sidecar exists. Added xnat info.')
                xnat_prov = json.load(f)
                xnat_prov.update(xnat_detail)
                #for x in os.path.join(sess_path, scan, scan_resources):
                    #if os.path.join(sess_path, scan, scan_resources,x).endswith(".json"):
                        #os.remove(os.path.join(sess_path, scan, scan_resources,x))
    else:
        xnat_prov = func_json_sidecar(XNAT, scan_file, sess_path, scan, bids_res_path, scan_res_path, scan_type, project, sess,
                                      res_path, res,
                                      is_json_present, scan_info, LOGGER)

    with open(os.path.join(bids_res_path.split('.')[0] + ".json"), "w+") as f:
        json.dump(xnat_prov, f, indent=2)


def func_json_sidecar(XNAT, scan_file, sess_path, scan, bids_res_path, scan_res_path, scan_type, project, sess, res_path, res,
                      is_json_present,
                      scan_info, LOGGER):
    xnat_prov = None
    tr_dict = sd_tr_mapping(XNAT, project, bids_res_path, LOGGER)
    TR_bidsmap = tr_dict.get(scan_type)
    if TR_bidsmap == None:
        LOGGER.info('ERROR: Scan type %s does not have a TR mapping. Func folder not created' % scan_type)
        func_folder = os.path.dirname(bids_res_path)
        os.rmdir(func_folder)
        sys.exit()
    TR_bidsmap = round((float(TR_bidsmap)), 3)
    tk_dict = sd_tasktype_mapping(XNAT, project, LOGGER)
    task_type = tk_dict.get(scan_type)
    # img = nib.load(bids_res_path)
    img = nib.load(scan_res_path)
    units = img.header.get_xyzt_units()[1]
    if units != 'sec':
        LOGGER.info('ERROR: the units in nifti header is not secs. Func folder not created')
        func_folder = os.path.dirname(bids_res_path)
        os.rmdir(func_folder)
        sys.exit()
    TR_nifti = round((img.header['pixdim'][4]), 3)
    if not is_json_present:
        xnat_prov = {"XNATfilename": scan_file,
                     "XNATProvenance": XNAT.host + scan_info._uri,
                     "TaskName": task_type}
        if TR_nifti == TR_bidsmap:
            LOGGER.warn(
                '\t\t>No existing json. TR %.3f sec in BIDS mapping and NIFTI header. Using TR %.3f sec in nifti header'
                'for scan %s in session %s. ' % (TR_bidsmap, TR_bidsmap, scan.split('-x-')[0], sess))
            xnat_prov["RepetitionTime"] = TR_nifti
        else:
            LOGGER.warn(
                '\t\t>No existing json. WARNING: The TR is %.3f sec in project level BIDS mapping, which does not match the TR of %.3f sec in NIFTI header.\n '
                '\t\tUPDATING NIFTI HEADER to match BIDS mapping TR %.3f sec for scan %s in session %s.'
                % (TR_bidsmap, TR_nifti, TR_bidsmap, scan.split('-x-')[0], sess))
            xnat_prov["RepetitionTime"] = TR_bidsmap
            img.header['pixdim'][4] = TR_bidsmap
            nib.save(img, bids_res_path)
    else:
        with open(XNAT.select(os.path.join(res_path, res)).get(), "r") as f:
            xnat_prov = json.load(f)
            TR_json = round((xnat_prov['RepetitionTime']), 3)
            xnat_detail = {"XNATfilename": scan_file,
                           "XNATProvenance": XNAT.host + scan_info._uri}
            #for x in os.path.join(sess_path, scan, scan_resources, scan_file):
                #if os.path.join(sess_path, scan, scan_resources, x).endswith(".json"):
                    #os.remove(os.path.join(sess_path, scan, scan_resources, x))
            # check if TR_json == TR_nifti
            if TR_json != TR_bidsmap:
                LOGGER.warn(
                    '\t\t>JSON sidecar exists. WARNING: TR is %.3f sec in project level BIDS mapping, which does not match the TR in JSON sidecar %.3f.\n '
                    '\t\tUPDATING JSON with TR %.3f sec in BIDS mapping and UPDATING NIFTI header for scan %s in session %s.' % (
                        TR_bidsmap, TR_json, TR_bidsmap, scan.split('-x-')[0], sess))
                xnat_detail['RepetitionTime'] = TR_bidsmap
                xnat_prov.update(xnat_detail)
                img.header['pixdim'][4] = TR_bidsmap
                nib.save(img, bids_res_path)
            else:
                LOGGER.warn(
                    '\t\t>JSON sidecar exists. TR is %.3f sec in BIDS mapping and JSON sidecar for scan %s in session %s. '
                    'Created json sidecar with XNAT info' % (TR_bidsmap, scan.split('-x-')[0], sess))
                with open(XNAT.select(os.path.join(res_path, res)).get(), "r") as f:
                    xnat_prov = json.load(f)
                    xnat_prov.update(xnat_detail)

    return xnat_prov


def sd_tr_mapping(XNAT, project, bids_res_path, LOGGER):
    tr_dict = {}
    if XNAT.select('/data/projects/' + project + '/resources/BIDS_repetition_time_sec').exists():
        for res in XNAT.select('/data/projects/' + project + '/resources/BIDS_repetition_time_sec/files').get():
            if res.endswith('.json'):
                with open(XNAT.select(
                        '/data/projects/' + project + '/resources/BIDS_repetition_time_sec/files/' + res).get(),
                          "r+") as f:
                    tr_mapping = json.load(f)
                    tr_dict = tr_mapping[project]
                    # tr_dict = {k.strip().replace('/', '_').replace(" ", "").replace(":", '_')
                    #: v for k, v in tr_dict.items()}
    else:
        LOGGER.error("ERROR: no TR mapping at project level. Func folder not created")
        func_folder = os.path.dirname(bids_res_path)
        os.rmdir(func_folder)
        sys.exit()
    return tr_dict


def sd_datatype_mapping(XNAT, project, LOGGER):
    """
      Method to map scan type to task type for functional scans

      :return: mapping dict
    """
    sd_dict = {}
    # if OPTIONS.selectionScan:
    # project = OPTIONS.selectionScan.split('-')[0]
    # else:
    # project = OPTIONS.project
    if XNAT.select('/data/projects/' + project + '/resources/BIDS_datatype').exists():
        for res in XNAT.select('/data/projects/' + project + '/resources/BIDS_datatype/files').get():
            if res.endswith('.json'):
                with open(XNAT.select('/data/projects/' + project + '/resources/BIDS_datatype/files/' + res).get(),
                          "r+") as f:
                    datatype_mapping = json.load(f)
                    sd_dict = datatype_mapping[project]
                    # sd_dict = {k.strip().replace('/', '_').replace(" ", "").replace(":", '_')
                    #: v for k, v in sd_dict.items()}
    else:
        LOGGER.info('WARNING: No BIDS datatype mapping in project %s - using default mapping' % (project))
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


def bids_filename(bids_sess_path, data_type, scan, scan_file, XNAT, project, scan_type, LOGGER):
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

    if data_type == "anat":
        bids_fname = sub_name + '_' + ses_name + '_acq-' + scan_id + '_' + 'T1w' + \
                     '.' + ".".join(scan_file.split('.')[1:])
        return bids_fname

    elif data_type == "func":
        tk_dict = sd_tasktype_mapping(XNAT, project, LOGGER)
        task_type = tk_dict.get(scan_type)
        if task_type == None:
            LOGGER.info('ERROR: Scan type %s does not have a BIDS tasktype mapping at default and project level. '
                        'Use BidsMapping tool. Func folder not created' % scan_type)
            func_folder = os.path.join(bids_sess_path, data_type)
            os.rmdir(func_folder)
            sys.exit()

        bids_fname = sub_name + '_' + ses_name + '_task-' + task_type + '_acq-' + scan_id + '_run-01' \
                     + '_' + 'bold' + '.' + ".".join(scan_file.split('.')[1:])

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


def sd_tasktype_mapping(XNAT, project, LOGGER):
    """
     Method to map scan type to task type for functional scans

     :return: mapping dict
     """
    tk_dict = {}
    # project = OPTIONS.project
    if XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype').exists():
        for res in XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype/files').get():
            if res.endswith('.json'):
                with open(XNAT.select('/data/projects/' + project + '/resources/BIDS_tasktype/files/'
                                      + res).get(), "r+") as f:
                    datatype_mapping = json.load(f)
                    tk_dict = datatype_mapping[project]
                    # tk_dict = {k.strip().replace('/', '_').replace(" ", "").replace(":", '_')
                    #: v for k, v in tk_dict.items()}

    else:
        LOGGER.info('WARNING: No BIDS task type mapping in project %s - using default mapping' % (project))
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