# -*- coding: utf-8 -*-
# This file is part of Ecotaxa, see license.md in the application root directory for license informations.
# Copyright (C) 2015-2021  Picheral, Colin, Irisson (UPMC-CNRS)
#
# Predict classification on a project. In details, launch a job which will:
# - If requested by the user and possible, compute DeepFeatures on the source projects
# - Use selected features on source projects to train a Random Forest classifier
# - Use the trained classifier on the target project.
#
# Here is just the job registering part, the rest is in ecotaxa_ML_back project.
#
from pathlib import Path
from typing import cast, List, Optional

from API_models.filters import ProjectFiltersDict
from API_models.prediction import (
    PredictionReq,
    PredictionRsp,
    TrainingHistoryEntry,
    ModelSummary,
)
from BO.Rights import RightsBO, Action
from DB.Project import ProjectIDT
from DB.Training import Training
from DB.User import UserIDT
from FS.MachineLearningModels import SavedModels
from FS.Vault import Vault
from helpers.DynamicLogs import get_logger, LogsSwitcher
# TODO: Move somewhere else
from .helpers.JobService import JobServiceBase, ArgsDict
from .helpers.Service import Service

logger = get_logger(__name__)


class PredictForProject(JobServiceBase):
    """ """

    JOB_TYPE = "Prediction"

    def __init__(self, req: PredictionReq, filters: ProjectFiltersDict):
        super().__init__()
        self.req = req
        self.filters = filters
        self.out_path: Path = Path("")
        self.vault = Vault(self.config.vault_dir())
        self.models_dir = SavedModels(self.config)

    def run(self, current_user_id: UserIDT) -> PredictionRsp:
        """
        Initial creation, do security and consistency checks, then create the job.
        """
        _user, _project = RightsBO.user_wants(
            self.session, current_user_id, Action.ANNOTATE, self.req.project_id
        )
        # TODO: more checks, e.g. deep features models consistency
        # Security OK, create pending job
        self.create_job(self.JOB_TYPE, current_user_id)
        ret = PredictionRsp(job_id=self.job_id)
        return ret

    def init_args(self, args: ArgsDict) -> ArgsDict:
        args["req"] = self.req.dict()
        args["filters"] = self.filters
        return args

    @staticmethod
    def deser_args(json_args: ArgsDict) -> None:
        json_args["req"] = PredictionReq(**json_args["req"])
        json_args["filters"] = cast(ProjectFiltersDict, json_args["filters"])

    def do_background(self) -> None:
        """
        Background part of the job.
        """
        with LogsSwitcher(self):
            self.do_prediction()

    def do_prediction(self) -> None: ...


class PredictionDataService(Service):
    """
    Available models service.
    """

    def get_models(self) -> List[str]:
        return SavedModels(self.config).list()

    # How many past evaluated trainings to hand back for a project's performance history/chart.
    MAX_HISTORY = 50

    def get_training_history(
        self,
        current_user_id: UserIDT,
        project_id: ProjectIDT,
        model_name: Optional[str] = None,
    ) -> List[TrainingHistoryEntry]:
        """
        Past, evaluated, trainings for a project, oldest first -- each one a "version" of
        the project's classifier, identified by when it ran. @see GPUPredictForProject.evaluate_split
        in ecotaxa_ML_back, which is what actually fills Training.evaluation. When model_name
        is given, restrict to that one named model's versions instead of the whole project.
        """
        RightsBO.user_wants(self.session, current_user_id, Action.READ, project_id)
        qry = (
            self.session.query(Training)
            .filter(Training.projid == project_id)
            .filter(Training.evaluation.isnot(None))
        )
        if model_name is not None:
            qry = qry.filter(Training.model_name == model_name)
        rows = qry.order_by(Training.training_start.asc()).limit(self.MAX_HISTORY).all()
        return [
            TrainingHistoryEntry(
                training_id=row.training_id,
                training_start=row.training_start,
                model_name=row.model_name,
                evaluation=row.evaluation,
            )
            for row in rows
        ]

    def get_trained_models(
        self, current_user_id: UserIDT, project_id: ProjectIDT
    ) -> List[ModelSummary]:
        """
        Named models trained for this project, one summary per name (latest version's info
        + a version count), for the wizard's entry page (pick "train new" vs "retrain X").
        """
        RightsBO.user_wants(self.session, current_user_id, Action.READ, project_id)
        rows = (
            self.session.query(Training)
            .filter(Training.projid == project_id)
            .filter(Training.model_name.isnot(None))
            .order_by(Training.training_start.asc())
            .all()
        )
        # Small per-project scale: group in Python rather than a window-function query.
        latest_by_name: dict = {}
        count_by_name: dict = {}
        for row in rows:
            count_by_name[row.model_name] = count_by_name.get(row.model_name, 0) + 1
            latest_by_name[row.model_name] = row  # rows are oldest->newest, last wins
        return [
            ModelSummary(
                name=name,
                training_id=row.training_id,
                training_start=row.training_start,
                version_count=count_by_name[name],
                config=row.config or {},
                learning_set_size=row.learning_set_size,
                evaluation=row.evaluation,
            )
            for name, row in sorted(latest_by_name.items())
        ]
