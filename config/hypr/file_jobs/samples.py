"""Preview jobs contain sample metadata only; no file operation is performed."""
try:
    from .model import Job
except ImportError:
    from model import Job

OPERATIONS = {'copy': 'Copying files', 'move': 'Moving files',
              'compress': 'Compressing files', 'extract': 'Extracting files'}


def sample(operation='copy', state='running'):
    title = OPERATIONS.get(operation, OPERATIONS['copy'])
    source = '/Preview/Archive.zip' if operation == 'extract' else '/Preview/Project assets'
    destination = '/Preview/Backup.zip' if operation == 'compress' else '/Preview/Backup'
    job = Job('/preview', ':preview', 'Xetal Files · Preview', 3,
              dict(title=title, percent=64, descriptionValue1=source, descriptionValue2=destination,
                   totalBytes=3*1024**3, processedBytes=round(3*1024**3*.64), speed=48*1024**2))
    if state == 'paused': job.update({'suspended': True})
    elif state == 'completed': job.terminate()
    elif state == 'error': job.terminate(2, 'Preview: the destination is not writable.')
    elif state == 'unknown':
        job.data.pop('percent'); job.data.pop('totalBytes')
    return job
