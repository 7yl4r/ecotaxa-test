import json
import os

from API_models.filters import ProjectFiltersDict
from API_models.prediction import PredictionReq
from API_operations.helpers.Service import Service
from BO.Job import JobBO
from DB.Job import Job, DBJobStateEnum
from helpers import DateTime

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
from API_operations.GPU_Prediction import GPUPredictForProject


def create_DB_job(session, job_type: str, user_id: int, args: dict) -> int:
    """
    Create a job directly in the DB.
    """
    job = Job()
    job.state = DBJobStateEnum.Pending
    job.progress_msg = JobBO.PENDING_MESSAGE
    job.creation_date = job.updated_on = DateTime.now_time()
    job.type = job_type
    job.owner_id = user_id
    job.params = json.dumps(args)
    job.inside = job.reply = json.dumps({})
    job.messages = json.dumps([])
    session.add(job)
    session.flush([job])
    job_id = job.id
    session.commit()
    return job_id


def test_prediction_job(database):
    features = ["obj.depth_min", "obj.depth_max", "fre.area"]
    req: PredictionReq = PredictionReq(project_id=1, source_project_ids=[2, 3], features=features)
    filters: ProjectFiltersDict = {}
    job = GPUPredictForProject(req, filters)
    with Service() as sce:
        job.job_id = create_DB_job(sce.session, job.JOB_TYPE, 1, job.init_args({}))
    job.do_background()
