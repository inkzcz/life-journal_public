"""Disposable integration-test worker; deliberately terminates at a durable seam."""
import argparse,os
from pathlib import Path
from app.main import app  # Register real metadata without writes.
from app.db import SessionLocal
from app.exchange import jobs
parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);parser.add_argument('--actor',type=int,required=True);parser.add_argument('--revision',type=int,required=True);parser.add_argument('--root',required=True)
args=parser.parse_args()
def terminate(stage):
    if stage=='files_ready':os._exit(73)
jobs.checkpoint=terminate
with SessionLocal() as db:jobs.confirm(db,args.job,args.actor,Path(args.root),args.revision)
raise SystemExit(74)
