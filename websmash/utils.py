#!/usr/bin/env python
"""Utility functions for websmash"""
import os

from flask import request
from os import path

from werkzeug.utils import secure_filename

from websmash import app, get_db
from websmash.models import Job


def generate_confirmation_mail(message):
    """Generate confirmation email message from template"""
    confirmation_template = """We have received your feedback to antiSMASH and will reply to you as soon as possible.
Your message was:

%s
"""
    return confirmation_template % message


def _submit_job(redis_store, job):
    """Submit a new job"""
    redis_store.hmset(u'job:%s' % job.uid, job.get_dict())
    redis_store.lpush('jobs:queued', job.uid)


def _get_checkbox(req, name):
    """Get True/False value for the checkbox of a given name"""
    str_value = req.form.get(name, u'off')
    return str_value == u'on' or str_value == 'true'


def dispatch_job():
    """Internal helper to dispatch a new job"""
    redis_store = get_db()
    taxon = app.config['TAXON']

    kwargs = dict(taxon=taxon)
    kwargs['ncbi'] = request.form.get('ncbi', '').strip()
    kwargs['email'] = request.form.get('email', '').strip()

    kwargs['all_orfs'] = _get_checkbox(request, 'all_orfs')

    kwargs['smcogs'] = _get_checkbox(request, 'smcogs')

    kwargs['clusterblast'] = _get_checkbox(request, 'clusterblast')
    kwargs['knownclusterblast'] = _get_checkbox(request, 'knownclusterblast')
    kwargs['subclusterblast'] = _get_checkbox(request, 'subclusterblast')

    kwargs['fullhmmer'] = _get_checkbox(request, 'fullhmmer')

    kwargs['genefinder'] = request.form.get('genefinder', 'prodigal')
    kwargs['trans_table'] = request.form.get('trans_table', 1, type=int)
    kwargs['gene_length'] = request.form.get('gene_length', 50, type=int)

    kwargs['from_pos'] = request.form.get('from', 0, type=int)
    kwargs['to_pos'] = request.form.get('to', 0, type=int)

    kwargs['inclusive'] = _get_checkbox(request, 'inclusive')
    kwargs['cf_cdsnr'] = request.form.get('cf_cdsnr', 5, type=int)
    kwargs['cf_npfams'] = request.form.get('cf_npfams', 5, type=int)
    kwargs['cf_threshold'] = request.form.get('cf_threshold', 0.6, type=float)

    kwargs['asf'] = _get_checkbox(request, 'asf')
    kwargs['tta'] = _get_checkbox(request, 'tta')
    kwargs['transatpks_da'] = _get_checkbox(request, 'transatpks_da')

    # given that we only support antismash 3 at the moment, hardcode
    # that jobtype.
    kwargs['jobtype'] = 'antismash4'

    job = Job(**kwargs)
    dirname = path.join(app.config['RESULTS_PATH'], job.uid)
    os.mkdir(dirname)

    if kwargs['ncbi'] != '':
        job.download = kwargs['ncbi']
    else:
        upload = request.files['seq']

        if upload is not None:
            filename = secure_filename(upload.filename)
            upload.save(path.join(dirname, filename))
            if not path.exists(path.join(dirname, filename)):
                raise Exception("Could not save file!")
            job.filename = filename
        else:
            raise Exception("Uploading input file failed!")

    _submit_job(redis_store, job)
    return job
