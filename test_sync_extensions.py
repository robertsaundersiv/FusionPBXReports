#!/usr/bin/env python
from app.celery_app import celery_app

# Send the task
result = celery_app.send_task('app.tasks.sync_extensions')
print(f'Task ID: {result.id}')
print('Task has been queued!')
