# -*- coding: utf-8 -*-
# This file is part of Ecotaxa, see license.md in the application root directory for license informations.
# Copyright (C) 2015-2026  Picheral, Colin, Irisson (UPMC-CNRS)
#
from typing import Dict, List, Optional


class PredictionReq:
    """
    Prediction, AKA Auto Classification, request.
    Received in Web app and stored verbatim in Job params.
    """
    def __init__(self, **kwargs):
        self.project_id: int = kwargs.get("project_id", 0)
        self.source_project_ids: List[int] = kwargs.get("source_project_ids", [])
        self.learning_limit: Optional[int] = kwargs.get("learning_limit")
        self.features: List[str] = kwargs.get("features", [])
        self.categories: List[int] = kwargs.get("categories", [])
        self.use_scn: bool = kwargs.get("use_scn", False)
        self.pre_mapping: Dict[int, int] = kwargs.get("pre_mapping", {})
        self.test_fraction: float = kwargs.get("test_fraction", 0.0)

    def dict(self):
        return self.__dict__