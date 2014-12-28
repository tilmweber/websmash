from flask import redirect, url_for, request, abort, \
                  render_template, jsonify
from flask.ext.mail import Message
import os
from os import path
from werkzeug import secure_filename
from websmash import app, mail, dl, redis_store
from websmash.utils import generate_confirmation_mail
from websmash.models import Job, Notice

# Supported sec met cluster types. List of descriptions, the clusters
# are specified by a number in antismash.py
sec_met_types = [
    "all",
    "polyketides (type I)",
    "polyketides (type II)",
    "polyketides (type III)",
    "heterocyst glycolipid-like polyketides",
    "nonribosomal peptides",
    "terpenes",
    "lantibiotics",
    "bacteriocins",
    "beta-lactams",
    "aminoglycosides / aminocyclitols",
    "aminocoumarins",
    "siderophores",
    "ectoines",
    "butyrolactones",
    "indoles",
    "nucleosides",
    "phosphoglycolipids",
    "melanins",
    "oligosaccharides",
    "furans",
    "homoserine lactones",
    "thiopeptides",
    "phenazines",
    "others"
]

@app.route('/', methods=['GET', 'POST'])
def new():
    error = None
    results_path = app.config['RESULTS_URL']
    old_email = ''
    try:
        if request.method == 'POST':
            kwargs = {}
            kwargs['ncbi'] = request.form.get('ncbi', '').strip()
            kwargs['email'] = request.form.get('email', '').strip()
            old_email = kwargs['email']
            kwargs['from'] = request.form.get('from', '').strip()
            kwargs['to'] = request.form.get('to', '').strip()
            legacy = request.form.get('legacy', u'off')
            if legacy == u'on':
                raise Exception('Sorry, but running antiSMASH 1 is no longer supported')
            eukaryotic = request.form.get('eukaryotic', u'off')
            inclusive = request.form.get('inclusive', u'off')
            smcogs = request.form.get('smcogs', u'off')
            clusterblast = request.form.get('clusterblast', u'off')
            subclusterblast = request.form.get('subclusterblast', u'off')
            fullblast = request.form.get('fullblast', u'off')
            fullhmmer = request.form.get('fullhmmer', u'off')
            kwargs['trans_table'] = request.form.get('trans_table', 1, type=int)
            kwargs['gene_length'] = request.form.get('gene_length', 50, type=int)
            kwargs['from'] = request.form.get('from', 0, type=int)
            kwargs['to'] = request.form.get('to', 0, type=int)
            i = 1
            clusters = []
            while(i < len(sec_met_types) + 1):
                if request.form.get("cluster_%s" % i, u'off') == u'on':
                    clusters.append(str(i))
                    if i == 1:
                        break
                i += 1
            if len(clusters) == 0:
                error_message  = "No gene cluster types specified. "
                error_message += "Please select the type of secondary "
                error_message += "metabolites to look for."
                raise Exception(error_message)
            kwargs['geneclustertypes'] = ",".join(clusters)

            # given that we only support antismash 2 at the moment, hardcode
            # that jobtype.
            kwargs['jobtype'] = 'antismash2'

            # Use boolean values instead of "on/off" strings
            kwargs['eukaryotic'] = (eukaryotic == u'on')
            kwargs['inclusive'] = (inclusive == u'on')
            kwargs['smcogs'] = (smcogs == u'on')
            kwargs['clusterblast'] = (clusterblast == u'on')
            kwargs['subclusterblast'] = (subclusterblast == u'on')
            kwargs['fullblast'] = (fullblast == u'on')
            kwargs['fullhmm'] = (fullhmmer == u'on')

            job = Job(**kwargs)
            dirname = path.join(app.config['RESULTS_PATH'], job.uid)
            os.mkdir(dirname)
            upload = None

            if kwargs['ncbi'] != '':
                ncbi =  kwargs['ncbi']
                if kwargs['email'] != '':
                    email = kwargs['email']
                else:
                    email = app.config['DEFAULT_MAIL_SENDER']

                url = app.config['NCBI_URL'] % (email, ncbi)
                upload = dl.download(str(url))
                if upload is not None:
                    upload.filename = '%s.gbk' % ncbi
            else:
                upload = request.files['seq']

            if upload is not None:
                filename = secure_filename(upload.filename)
                upload.save(path.join(dirname, filename))
                if not path.exists(path.join(dirname, filename)):
                    raise Exception("Could not save file!")
                job.filename = filename
            else:
                raise Exception("Downloading or uploading input file failed!")

            redis_store.hmset(u'job:%s' % job.uid, job.get_dict())
            redis_store.lpush('jobs:queued', job.uid)
            return redirect(url_for('.display', task_id=job.uid))
    except Exception, e:
        error = unicode(e)
    return render_template('new.html', error=error,
                           old_email=old_email,
                           sec_met_types=sec_met_types,
                           results_path=results_path)

@app.route('/protein', methods=['GET', 'POST'])
def protein():
    error = None
    results_path = app.config['RESULTS_URL']
    old_sequence = ''
    old_email = ''
    if request.method == 'GET':
        return render_template('new.html', error=error,
                               sec_met_types=sec_met_types,
                               old_email=old_email,
                               old_sequence=old_sequence,
                               switch_to='prot',
                               results_path=results_path)

    try:
        kwargs = {}
        kwargs['prot-ncbi'] = request.form.get('prot-ncbi', '').strip()
        kwargs['email'] = request.form.get('email', '').strip()
        old_email = kwargs['email']
        # We always run all sec met types for the protein search
        kwargs['geneclustertypes'] = "1"
        # And we always run antiSMASH2 jobs for this
        kwargs['jobtype'] = 'antismash2'
        # And of course this is protein input
        kwargs['molecule'] = 'prot'

        job = Job(**kwargs)
        dirname = path.join(app.config['RESULTS_PATH'], job.uid)
        os.mkdir(dirname)

        if kwargs['prot-ncbi'] != '':
            ncbi =  kwargs['prot-ncbi']
            if kwargs['email'] != '':
                email = kwargs['email']
            else:
                email = app.config['DEFAULT_MAIL_SENDER']

            url = app.config['NCBI_PROT_URL'] % (email, ncbi)
            upload = dl.download(str(url))

            if upload is not None:
                upload.filename = '%s.fasta' % ncbi
                filename = secure_filename(upload.filename)
                upload.save(path.join(dirname, filename))
                job.filename = filename
            else:
                raise Exception("Downloading or uploading input file failed!")

        else:
            sequence = request.form.get('sequence', '').strip()
            old_sequence = sequence

            if len(sequence) == 0:
                raise Exception("No sequence specified")

            if sequence.count('>') < 1:
                raise Exception("No FASTA headers found")

            if sequence.count('\n') < 1:
                raise Exception("No newline between FASTA header and sequence")

            filename = path.join(dirname, 'protein_input.fa')
            with open(filename, 'w') as handle:
                handle.write(sequence)
            job.filename = 'protein_input.fa'

        redis_store.hmset(u'job:%s' % job.uid, job.get_dict())
        redis_store.lpush('jobs:queued', job.uid)
        return redirect(url_for('.display', task_id=job.uid))

    except Exception, e:
        error = unicode(e)
    return render_template('new.html', error=error,
                           sec_met_types=sec_met_types,
                           old_email=old_email,
                           old_sequence=old_sequence,
                           switch_to='prot',
                           results_path=results_path)

@app.route('/about')
@app.route('/about.html')
def about():
    return render_template('about.html')

@app.route('/help')
@app.route('/help.html')
def help():
    return render_template('help.html')

@app.route('/download')
@app.route('/download.html')
def download():
    return render_template('download.html')

@app.route('/contact', methods=['GET', 'POST'])
@app.route('/contact.html', methods=['GET', 'POST'])
def contact():
    error = None
    email = ''
    message = ''
    try:
        if request.method == 'POST':
            email = request.form.get('email', '')
            message = request.form.get('body', '')
            if email == '':
                raise Exception("Please specify an email address")
            if message == '':
                raise Exception("No message specified. Please specify a message")

            contact_msg = Message(subject='antiSMASH feedback',
                                  recipients=app.config['DEFAULT_RECIPIENTS'],
                                  body=message, sender=email)
            mail.send(contact_msg)
            confirmation_msg = Message(subject='antiSMASH feedback received',
                                       recipients=[email],
                                       body=generate_confirmation_mail(message))
            mail.send(confirmation_msg)

            return render_template('message_sent.html', message=message)
    except Exception, e:
        error = unicode(e)
    return render_template('contact_form.html', error=error, email=email, message=message)

@app.route('/display/<task_id>')
def display(task_id):
    results_path = app.config['RESULTS_URL']
    res = redis_store.hgetall(u'job:%s' % task_id)
    if res == {}:
        abort(404)
    else:
        job = Job(**res)
    return render_template('display.html', job=job, results_path=results_path)

@app.route('/display')
def display_tab():
    return render_template('new.html',
                           sec_met_types=sec_met_types,
                           switch_to='job',
                           results_path=app.config['RESULTS_URL'])

@app.route('/status/<task_id>')
def status(task_id):
    res = redis_store.hgetall(u'job:%s' % task_id)
    if res == {}:
        abort(404)
    job = Job(**res)
    if job.status == 'done':
        result_url = "%s/%s" % (app.config['RESULTS_URL'], job.uid)
        if job.jobtype == 'antismash':
            result_url += "/display.xhtml"
        else:
            result_url += "/index.html"
        res['result_url'] = result_url
    res['short_status'] = job.get_short_status()

    return jsonify(res)


@app.route('/server_status')
def server_status():
    pending = redis_store.llen('jobs:queued')
    running = redis_store.llen('jobs:running')

    if pending + running > 0:
        status = 'working'
    else:
        status = 'idle'
    return jsonify(status=status, queue_length=pending, running=running)

@app.route('/current_notices')
def current_notices():
    "Display current notices"
    rets = redis_store.keys('notice:*')
    notices = [ redis_store.hgetall(n) for n in rets]
    return jsonify(notices=notices)

@app.route('/show_notices')
def show_notices():
    "Show current notices"
    rets = redis_store.keys('notice:*')
    notices = [Notice(**redis_store.hgetall(i)) for i in rets]
    return render_template('notices.html', notices=notices, skip_notices=True)
