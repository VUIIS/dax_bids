#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import dax
from dax import bin
from dax import processors
from dax import processor_graph
from dax import processor_parser
from dax import XnatUtils


utility_name = 'XnatAssessorPatch'

description =\
    "Patch existing assessors with inputs, provided that the inputs can unambiguously determined"

def check_arguments(logger, parsed_args):
    if parsed_args.settings is None:
        logger.error("Please provide the location of a DAX yaml settings file")
        return False

    return True




def configure_parser():
    from argparse import ArgumentParser, RawDescriptionHelpFormatter

    argp = ArgumentParser(prog=utility_name, description=description)

    argp.add_argument(dest='settings', default=None,
                      help='DAX settings file')
    argp.add_argument('--host', dest='host', default=None,
                      help='Host for XNAT. Default: using $XNAT_HOST.')
    argp.add_argument('-u', '--username', dest='username', default=None,
                      help='Username for XNAT. Default: using $XNAT_USER.')
    argp.add_argument('-t', '--proctypes', dest='proctypes', default=None,
                      help='Processor proctype list for the assessor types that you want to patch')
    argp.add_argument('-p', '--projects', dest='projects', default=None,
                      help='Project ID(s) on XNAT')
    argp.add_argument('-s', '--subjects', dest='subjects', default=None,
                      help='Optional subject ID(s) on XNAT')
    argp.add_argument('-e', '--sessions', dest='sessions', default=None,
                      help='Optional session ID(s) on XNAT')
    argp.add_argument('-o', '--outputfile', dest='outputfile', default=None,
                       help='Optional output file name and path for logging')
    #TODO: add quality filter argument
    #TODO: add interactive mode

    return argp


def setup_info_logger(logfile=None):
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

    logger = logging.getLogger('dax')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


if __name__ == '__main__':
    dax_settings = dax.DAX_Settings()
    logger = setup_info_logger()
    parser = configure_parser()
    parsed_args = parser.parse_args()
    logger.info('testing logger')

    #argument checks do their own logging
    if not check_arguments(logger, parsed_args):
        exit(-1)

    if not dax_settings.is_cluster_valid(logger):
        exit(-1)

    launcher = bin.read_settings(parsed_args.settings, logger, exe='patch assessors')

    with XnatUtils.get_interface(launcher.xnat_host, launcher.xnat_user,
                                 launcher.xnat_pass) as intf:
        print 'intf=', intf

        print 'launcher process dict=', launcher.project_process_dict

        project_list = set(launcher.project_process_dict.keys())
        if parsed_args.projects:
            for p in project_list:
                if p not in project_list:
                    msg = "project {} is not in the list of projects defined in {} ({})"
                    logger.warning(msg.format(p, parsed_args.settings, project_list))

        for p in project_list:
            project_processors = launcher.project_process_dict.get(p, None)
            if project_processors is None:
                logger.info("Procject '{}' has no processors - skipping")
                continue

            _, _, auto_procs = processors.processors_by_type(project_processors)
            auto_procs = processor_graph.ProcessorGraph.order_processors(auto_procs, logger)
            print 'auto_procs =', auto_procs

            # if parsed_args.sessions is not None:
            #     for s in parsed_args.session:
            #         sess = intf.select('/project/*/subject/*/session/' + s)
            #         print sess
            # else:
            print 'patching project', p
            proj = intf.select_project(p)
            for s in proj.subjects():
                print 'subject:', s.label()
                for e in intf.get_sessions(p, s.label()):
                    if not parsed_args.sessions\
                        or e['label'] in parsed_args.sessions\
                        or e['ID'] in parsed_args.sessions:
                        experiment = XnatUtils.CachedImageSession(intf, p, s.label(), e['label'])
                        for a in auto_procs:
                            a.parse_session(experiment)
                            a.parser.patch_assessors()