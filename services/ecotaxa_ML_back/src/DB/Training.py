# -*- coding: utf-8 -*-
# This file is part of Ecotaxa, see license.md in the application root directory for license informations.
# Copyright (C) 2015-2023  Picheral, Colin, Irisson (UPMC-CNRS)
#
# A training is an operation which consists in determining, for each of a set of objects,
# the most likely classifications AKA predictions.
# This object is immutable after all children predictions are added. It reflects _what happened_.
# Only exception to this rule is when predicted objects disappear.
#
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import (
    VARCHAR,
    INTEGER,
    TIMESTAMP,
    JSONB,
)

from .Project import Project
from .User import User
from .helpers.DDL import Column, ForeignKey, Index
from .helpers.ORM import Model
from .helpers.ORM import relationship

TrainingIDT = int
IN_PROGRESS_DATE = datetime.fromtimestamp(0)


class Training(Model):
    __tablename__ = "training"
    # Below, SQLA/Alembic automatically makes column SERIAL, sequence from PG is 'training_training_id_seq'
    training_id: int = Column(INTEGER, primary_key=True)
    # The target project.
    projid: int = Column(
        INTEGER, ForeignKey(Project.projid, ondelete="CASCADE"), nullable=True
    )
    # Who launched or is responsible for the training operation
    training_author: int = Column(INTEGER, ForeignKey(User.id), nullable=False)
    # When it occurred
    training_start: datetime = Column(TIMESTAMP, nullable=False)
    training_end: datetime = Column(TIMESTAMP, nullable=False)
    # The settings used?
    training_path: str = Column(VARCHAR(80), nullable=False)
    # Held-out test split evaluation, when one was requested (@see PredictionReq.test_fraction).
    # Shape: {test_fraction, overall_accuracy, macro_accuracy, train_size, test_size,
    #         per_taxon: [...], excluded_categories: [...]}. Null when no split was evaluated.
    evaluation: Optional[Any] = Column(JSONB, nullable=True)
    # User-chosen name identifying this classifier across retrainings (Prediction jobs only;
    # null for other training-producing flows, e.g. imports). Not unique at the DB level --
    # several rows share a name, one per version -- uniqueness within a project is a UX-layer
    # check, @see PredictionJob.validate_task in ecotaxa_front.
    model_name: Optional[str] = Column(VARCHAR(120), nullable=True)
    # The locked recipe used to produce this version, so a later retrain can replay it verbatim:
    # {source_project_ids, categories, features, learning_limit, use_scn, pre_mapping, test_fraction}.
    config: Optional[Any] = Column(JSONB, nullable=True)
    # Row count of the learning set actually used at this training (independent of whether an
    # evaluation split was done). Used to detect "more data validated since last training".
    learning_set_size: Optional[int] = Column(INTEGER, nullable=True)

    # The relationships are created in Relations.py but the typing here helps the IDE
    author: relationship
    predictions: relationship
    project: relationship

    def __str__(self):
        return "Training #{0} by user {1} on the {2}".format(
            self.training_id, self.training_author, self.training_start
        )


Index(
    "trn_projid_start",
    Training.projid,
    Training.training_start,
    unique=True,
)
